// GET /api/health — is Google Sheets configured? GET /api/health?check=1 also runs a real read and
// reports row counts per tab. Use it to test the connection after adding the environment variables.
import { readConfig, fetchAppData, counts } from "../lib/sheets.js";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const out = { ok: true, sheetIdSet: !!process.env.SHEET_ID, serviceAccountSet: !!process.env.GOOGLE_SERVICE_ACCOUNT_JSON, dataSource: process.env.DATA_SOURCE || "auto" };
  let cfg;
  try { cfg = readConfig(); } catch (e) { return res.status(200).json({ ...out, configured: false, problem: e.public ? e.message : "Configuration error." }); }
  out.configured = !!cfg;
  const q = new URL(req.url, "http://x").searchParams;
  if (!cfg || q.get("check") !== "1") return res.status(200).json(out);
  try {
    const data = await fetchAppData(cfg);
    return res.status(200).json({ ...out, connection: "ok", checkedAt: new Date().toISOString(), counts: counts(data) });
  } catch (e) {
    return res.status(200).json({ ...out, connection: "failed", problem: e.public ? e.message : "Could not read the Google Sheet." });
  }
}
