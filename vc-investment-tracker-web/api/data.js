// GET /api/data — the tracker's data from Google Sheets (read-only), or {source: "demo"} telling the page to use the
// bundled snapshot (source: "demo"). Responses never include credentials.
import { readConfig, fetchAppData, counts } from "../lib/sheets.js";

export default async function handler(req, res) {
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.setHeader("Allow", "GET, HEAD");
    return res.status(405).json({ error: "Method not allowed." });
  }
  res.setHeader("Cache-Control", "no-store");
  if ((process.env.DATA_SOURCE || "").toLowerCase() === "demo") {
    return res.status(200).json({ source: "demo", error: "Live data is switched off (DATA_SOURCE=demo)." });
  }
  let cfg;
  try { cfg = readConfig(); } catch (e) { return res.status(500).json({ source: "demo", error: e.public ? e.message : "Server configuration error." }); }
  if (!cfg) return res.status(200).json({ source: "demo", error: "Google Sheets is not connected yet (SHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON are not set)." });
  try {
    const data = await fetchAppData(cfg);
    res.setHeader("Cache-Control", "public, s-maxage=60, stale-while-revalidate=300");
    return res.status(200).json({ source: "google-sheets", fetchedAt: new Date().toISOString(), counts: counts(data), data });
  } catch (e) {
    console.error("[api/data]", e && e.message);
    return res.status(e.public ? (e.status || 502) : 502).json({ source: "demo", error: e.public ? e.message : "Could not read the Google Sheet." });
  }
}
