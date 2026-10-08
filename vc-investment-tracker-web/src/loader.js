/* Data loader for the deployed site. Tries the read-only Google Sheets API first and falls back to the
   bundled CSV snapshot. The top-bar badge says which one is showing, and why. */
(async function load() {
  let detail = "Google Sheets is not connected yet.";
  try {
    const r = await fetch("/api/data", { headers: { accept: "application/json" }, cache: "no-store" });
    const j = await r.json().catch(() => ({}));
    if (r.ok && j.source === "google-sheets" && j.data) {
      boot(j.data, { kind: "sheets", fetchedAt: new Date(j.fetchedAt).toLocaleString() });
      return;
    }
    if (j.error) detail = j.error;
  } catch (e) {
    detail = "The live-data API is not available here.";
  }
  const d = await (await fetch("data/demo-data.json")).json();
  boot(d, { kind: "demo", detail });
})();
