// Checks the Google Sheets mapping against the real tracker workbook (fixture exported from
// vc_investment_tracker.xlsx in the Sheets API shape) and the bundled CSV snapshot. No network.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import crypto from "node:crypto";
import { toAppData, readConfig, fetchAppData } from "../lib/sheets.js";
import dataHandler from "../api/data.js";

const fixture = JSON.parse(fs.readFileSync(new URL("./fixtures/sheets-batchget.json", import.meta.url)));
const demo = JSON.parse(fs.readFileSync(new URL("../public/data/demo-data.json", import.meta.url)));

test("sheet tabs map to the same records and IDs as the CSV snapshot", () => {
  const d = toAppData(fixture);
  assert.equal(d.startups.length, 20);
  assert.equal(d.rounds.length, 25);
  assert.equal(d.claims.length, 144);
  assert.deepEqual(d.startups.map(s => s.startup_id), demo.startups.map(s => s.startup_id));
  assert.deepEqual(d.rounds.map(r => r.round_id), demo.rounds.map(r => r.round_id));
  assert.deepEqual(d.claims.map(c => c.claim_id), demo.claims.map(c => c.claim_id));
});

test("field values the app reads match the snapshot", () => {
  const d = toAppData(fixture);
  const cmp = (a, b, label) => {
    for (const [i, row] of b.entries()) for (const [k, v] of Object.entries(row)) {
      if (!(k in a[i])) continue;
      assert.equal(a[i][k], v, `${label} ${row[Object.keys(row)[0]]}.${k}`);
    }
  };
  cmp(d.rounds, demo.rounds, "round");
  cmp(d.claims, demo.claims, "claim");
  cmp(d.pipeline, demo.pipeline, "pipeline");
  cmp(d.scores, demo.scores, "score");
  const keys = ["company_name", "sector", "fundraising_status", "verification_confidence", "latest_fy_revenue_usd", "latest_fy_revenue_status", "current_arr_usd", "long_term_debt_usd", "revenue_stage", "missing_fields"];
  for (const [i, s] of demo.startups.entries()) for (const k of keys) assert.equal(d.startups[i][k], s[k], `${s.startup_id}.${k}`);
});

test("weights and thresholds come from Lists & Settings", () => {
  const d = toAppData(fixture);
  assert.deepEqual(d.settings.weights, { market: 25, traction: 25, team: 20, moat: 15, financials: 15 });
  assert.equal(d.settings.thresholds.alert_days, 30);
  assert.equal(d.settings.thresholds.min_evidence_coverage, 0.6);
});

test("not configured: no env means null, partial env is a clear error", () => {
  assert.equal(readConfig({}), null);
  assert.throws(() => readConfig({ SHEET_ID: "x".repeat(30) }), /GOOGLE_SERVICE_ACCOUNT_JSON is not set/);
  assert.throws(() => readConfig({ SHEET_ID: "x".repeat(30), GOOGLE_SERVICE_ACCOUNT_JSON: "{bad" }), /not valid JSON/);
});

function fakeEnv() {
  const { privateKey } = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 });
  const pem = privateKey.export({ type: "pkcs8", format: "pem" });
  return { SHEET_ID: "TEST_SHEET_ID_0123456789abcdef", GOOGLE_SERVICE_ACCOUNT_JSON: JSON.stringify({ client_email: "reader@test.iam.gserviceaccount.com", private_key: pem }), pem };
}

test("uses the read-only scope and returns mapped data through a mocked Google API", async () => {
  const env = fakeEnv();
  const calls = [];
  const fakeFetch = async (url, opts = {}) => {
    calls.push({ url: String(url), opts });
    if (String(url).startsWith("https://oauth2.googleapis.com/token")) {
      const assertion = new URLSearchParams(opts.body).get("assertion");
      const claims = JSON.parse(Buffer.from(assertion.split(".")[1], "base64url").toString());
      assert.equal(claims.scope, "https://www.googleapis.com/auth/spreadsheets.readonly");
      return new Response(JSON.stringify({ access_token: "tok", expires_in: 3600 }), { status: 200 });
    }
    assert.match(String(url), /values:batchGet/);
    assert.equal(opts.headers.authorization, "Bearer tok");
    return new Response(JSON.stringify(fixture), { status: 200 });
  };
  const d = await fetchAppData(readConfig(env), fakeFetch);
  assert.equal(d.startups.length, 20);
  assert.ok(calls.every(c => c.opts.method !== "PUT" && !/:batchUpdate|:append|:clear/.test(c.url)), "only reads");
});

test("API never leaks credentials and reports 'not connected' honestly", async () => {
  const saved = { ...process.env };
  delete process.env.SHEET_ID; delete process.env.GOOGLE_SERVICE_ACCOUNT_JSON; delete process.env.DATA_SOURCE;
  const run = async () => { let status, body; const res = { setHeader() {}, status(c) { status = c; return res; }, json(o) { body = o; return res; } }; await dataHandler({ method: "GET", url: "/api/data" }, res); return { status, body }; };
  const a = await run();
  assert.equal(a.status, 200);
  assert.equal(a.body.source, "demo");
  assert.match(a.body.error, /not connected/);
  const env = fakeEnv();
  process.env.SHEET_ID = env.SHEET_ID; process.env.GOOGLE_SERVICE_ACCOUNT_JSON = env.GOOGLE_SERVICE_ACCOUNT_JSON;
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response("denied", { status: 401 });
  const b = await run();
  globalThis.fetch = realFetch;
  Object.assign(process.env, saved);
  assert.equal(b.status, 502);
  const text = JSON.stringify(b.body);
  assert.ok(!text.includes("PRIVATE KEY") && !text.includes(env.SHEET_ID) && !text.includes("reader@"), text);
});
