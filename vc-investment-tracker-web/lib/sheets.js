// Read-only Google Sheets access for the tracker.
// Signs a service-account JWT with Node's crypto (no third-party packages), asks only for the
// spreadsheets.readonly scope, reads the six data tabs by header name, and returns the same shape
// as public/data/demo-data.json. Credentials never leave the server and never appear in responses.
import crypto from "node:crypto";
import DEFAULT_SETTINGS from "./default-settings.js";

const SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly";
const TOKEN_URL = "https://oauth2.googleapis.com/token";

export const TABS = {
  startups: "Startup Database",
  rounds: "Funding Rounds",
  financials: "Financial Analysis",
  scores: "Investment Scorecard",
  pipeline: "Deal Pipeline",
  claims: "Source Verification",
};
const SETTINGS_WEIGHTS = "'Lists & Settings'!A4:D8";
const SETTINGS_THRESHOLDS = "'Lists & Settings'!A12:B17";
const THRESHOLD_KEYS = ["strong", "promising", "watchlist", "min_evidence_coverage", "financial_coverage", "alert_days"];
const DATE_FIELDS = new Set(["offering_deadline", "deadline_alt_date", "round_close_date", "verification_date", "verified_on",
  "next_action_date", "decision_date", "last_updated", "scored_on"]);
const ID_FIELD = { startups: "startup_id", rounds: "round_id", financials: "startup_id", scores: "startup_id", pipeline: "startup_id", claims: "claim_id" };

/** An error whose message is safe to show to the browser (never contains secrets). */
export class PublicError extends Error {
  constructor(message, status = 502) { super(message); this.public = true; this.status = status; }
}

/** Reads SHEET_ID and the service account from env. Returns null when not configured. */
export function readConfig(env = process.env) {
  const sheetId = (env.SHEET_ID || "").trim();
  let raw = (env.GOOGLE_SERVICE_ACCOUNT_JSON || "").trim();
  if (!sheetId && !raw) return null;
  if (!sheetId) throw new PublicError("SHEET_ID is not set.", 500);
  if (!raw) throw new PublicError("GOOGLE_SERVICE_ACCOUNT_JSON is not set.", 500);
  if (!raw.startsWith("{")) {
    try { raw = Buffer.from(raw, "base64").toString("utf8"); } catch { /* fall through to the JSON error */ }
  }
  let sa;
  try { sa = JSON.parse(raw); } catch { throw new PublicError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON (paste the whole key file).", 500); }
  if (!sa.client_email || !sa.private_key) throw new PublicError("The service account JSON is missing client_email or private_key.", 500);
  if (!/^[A-Za-z0-9_-]{20,}$/.test(sheetId)) throw new PublicError("SHEET_ID does not look like a Google Sheet ID (copy the part of the sheet URL between /d/ and /edit).", 500);
  return { sheetId, clientEmail: sa.client_email, privateKey: String(sa.private_key).replace(/\\n/g, "\n") };
}

let cachedToken = null; // { token, exp, email }
async function accessToken(cfg, fetchImpl) {
  const now = Math.floor(Date.now() / 1000);
  if (cachedToken && cachedToken.email === cfg.clientEmail && cachedToken.exp - 60 > now) return cachedToken.token;
  const b64 = o => Buffer.from(JSON.stringify(o)).toString("base64url");
  const unsigned = b64({ alg: "RS256", typ: "JWT" }) + "." + b64({ iss: cfg.clientEmail, scope: SCOPE, aud: TOKEN_URL, iat: now, exp: now + 3600 });
  let sig;
  try { sig = crypto.createSign("RSA-SHA256").update(unsigned).sign(cfg.privateKey).toString("base64url"); }
  catch { throw new PublicError("The service account private key could not be read.", 500); }
  const r = await fetchImpl(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion: unsigned + "." + sig }).toString(),
  });
  if (!r.ok) throw new PublicError(`Google sign-in for the service account failed (HTTP ${r.status}). Check that the key is current.`);
  const j = await r.json();
  cachedToken = { token: j.access_token, exp: now + (j.expires_in || 3600), email: cfg.clientEmail };
  return j.access_token;
}

function cellText(v, field) {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") {
    if (DATE_FIELDS.has(field) && v > 20000 && v < 80000) { // Sheets date serial
      return new Date(Date.UTC(1899, 11, 30) + v * 864e5).toISOString().slice(0, 10);
    }
    return String(Number(v.toPrecision(15)));
  }
  if (typeof v === "boolean") return v ? "TRUE" : "FALSE";
  const s = String(v);
  if (DATE_FIELDS.has(field)) {
    const m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/); // US-formatted date cell
    if (m) return `${m[3]}-${m[1].padStart(2, "0")}-${m[2].padStart(2, "0")}`;
  }
  return s;
}

/** Turns a values grid (row 1 = machine column names) into objects keyed by header name. */
export function rowsFromValues(values, tabName, idField) {
  if (!values || !values.length) throw new PublicError(`The "${tabName}" tab is empty or missing.`);
  const header = values[0].map(h => String(h ?? "").trim());
  if (!header.includes(idField)) throw new PublicError(`The "${tabName}" tab has no "${idField}" column in row 1.`);
  return values.slice(1)
    .filter(r => r && r.some(v => v !== "" && v !== null && v !== undefined))
    .map(r => Object.fromEntries(header.filter(Boolean).map(h => [h, cellText(r[header.indexOf(h)], h)])))
    .filter(o => o[idField]);
}

function settingsFrom(weightsVals, thresholdVals) {
  const s = JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
  for (const row of weightsVals || []) {
    const key = String(row[3] ?? "").trim(), w = Number(row[1]);
    if (key in s.weights && Number.isFinite(w) && w >= 0) s.weights[key] = w;
  }
  (thresholdVals || []).forEach((row, i) => {
    const v = Number(row[1]);
    if (THRESHOLD_KEYS[i] && Number.isFinite(v)) s.thresholds[THRESHOLD_KEYS[i]] = v;
  });
  return s;
}

/** Maps a values:batchGet response to the app's data shape. Exported for tests. */
export function toAppData(batch) {
  const ranges = batch.valueRanges || [];
  const tabs = Object.keys(TABS);
  if (ranges.length < tabs.length) throw new PublicError("The Google Sheet response was incomplete.");
  const t = {};
  tabs.forEach((k, i) => { t[k] = rowsFromValues(ranges[i].values, TABS[k], ID_FIELD[k]); });
  const fin = Object.fromEntries(t.financials.map(r => [r.startup_id, r]));
  const startups = t.startups.map(s => {
    const f = fin[s.startup_id] || {};
    const merged = { ...s };
    for (const [k, v] of Object.entries(f)) {
      if (k === "notes") merged.financial_notes = v;
      else if (!(k in merged)) merged[k] = v;
    }
    return merged;
  });
  if (!startups.length) throw new PublicError('The "Startup Database" tab has no startups.');
  return {
    settings: settingsFrom(ranges[tabs.length]?.values, ranges[tabs.length + 1]?.values),
    startups,
    rounds: t.rounds,
    claims: t.claims,
    pipeline: t.pipeline,
    scores: t.scores,
  };
}

/** Reads every tab the app needs in one batchGet call. */
export async function fetchAppData(cfg, fetchImpl = fetch) {
  const token = await accessToken(cfg, fetchImpl);
  const params = new URLSearchParams();
  for (const name of Object.values(TABS)) params.append("ranges", `'${name}'`);
  params.append("ranges", SETTINGS_WEIGHTS);
  params.append("ranges", SETTINGS_THRESHOLDS);
  params.set("valueRenderOption", "UNFORMATTED_VALUE");
  params.set("dateTimeRenderOption", "FORMATTED_STRING");
  params.set("majorDimension", "ROWS");
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(cfg.sheetId)}/values:batchGet?${params}`;
  const r = await fetchImpl(url, { headers: { authorization: `Bearer ${token}` } });
  if (r.status === 403) throw new PublicError("The service account cannot open this sheet. Share the sheet with the service account email as a Viewer.");
  if (r.status === 404) throw new PublicError("No Google Sheet was found for SHEET_ID.");
  if (r.status === 400) throw new PublicError("Google Sheets rejected the request. Check that all six tab names match the tracker workbook.");
  if (!r.ok) throw new PublicError(`Google Sheets returned HTTP ${r.status}.`);
  return toAppData(await r.json());
}

export function counts(data) {
  return { startups: data.startups.length, rounds: data.rounds.length, claims: data.claims.length, pipeline: data.pipeline.length, scores: data.scores.length };
}
