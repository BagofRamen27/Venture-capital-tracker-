# Codex Implementation Prompt

Copy everything inside the box below into OpenAI Codex. It assumes the `discovery-engine/` folder
from this branch is already in your repository. If it isn't, paste the files from
`discovery-engine/docs/COPY_PASTE_BUNDLE.md` first.

---

```text
You are working in my repository "Venture-capital-tracker-". It contains:
  - vc-investment-tracker-web/  -> my EXISTING dashboard (keep it)
  - discovery-engine/           -> a Python/FastAPI startup-discovery backend that is already written and tested

GOAL
Connect my existing dashboard to the discovery-engine backend so the dashboard shows real database
records (not the static JSON snapshot), and add discovery, research, pipeline and automation features.
Do NOT rebuild the website. Do NOT add any demo, sample, placeholder or hard-coded companies.

STEP 0 - INSPECT FIRST (do not change anything yet)
1. Read the whole repository. Do not assume its structure; confirm it.
2. Identify the frontend framework and build process of vc-investment-tracker-web (I believe it is plain
   HTML/CSS/vanilla JavaScript in dist/ with no build step and a tiny Node static server in
   scripts/serve.mjs, but verify).
3. Read discovery-engine/README.md, discovery-engine/vcdiscovery/api/app.py and
   discovery-engine/vcdiscovery/dashboard_export.py.
4. Write a short plan listing the files you will change and why. Then continue.

STEP 1 - GET THE BACKEND RUNNING
1. cd discovery-engine; create a virtual environment; pip install -r requirements.txt.
2. Run: python -m pytest   (all tests must pass; if any fail, fix the cause, never delete or skip tests).
3. Copy .env.example to .env. Leave VCD_SEC_USER_AGENT as a placeholder for me to fill in; never invent an email.
4. Run: python -m vcdiscovery.cli init-db
        python -m vcdiscovery.cli import-tracker
        python -m vcdiscovery.cli refresh-scores
   and confirm GET http://127.0.0.1:8000/api/health reports 20 startups after starting
   `python -m vcdiscovery.cli serve`.
5. Fix any broken or missing dependencies you find in either project.

STEP 2 - CONNECT THE EXISTING DASHBOARD TO THE DATABASE
1. In dist/app.js the data is loaded with fetch("data/demo-data.json"). Change the loader to:
   - read an API base URL from a single config place (e.g. window.VC_API_BASE set in a small
     dist/config.js, default "http://127.0.0.1:8000"),
   - load GET {API_BASE}/api/dashboard/snapshot (this returns the SAME JSON shape as demo-data.json),
   - if the API is unreachable, fall back to data/demo-data.json and show the existing mode badge
     text "Offline snapshot" so it is obvious the data is not live.
2. Keep every existing view working (Dashboard, Directory, Scorecard, Deal pipeline, Financials, profiles).
3. Text in dist/app.js that hard-codes counts or claims about the data (for example
   "sourced from Reg CF filings, platform listings and YC") must be made accurate for live data
   (derive it from the data or make it neutral).
4. The snapshot uses these extra claim verification statuses; add them to the badge logic in app.js:
   "Verified - corroborated (2+ sources)" -> verified style, label "corroborated";
   "Reported - news (unverified)" -> unverified style; "Analyst-entered" -> plain;
   "Target (not raised)" and "Rumor (unconfirmed)" -> unverified style and NEVER counted as raised.
5. Pipeline stage edits currently go to browser localStorage. When the API is reachable, also send them to
   POST /api/startups/{discovery_id}/status (each snapshot startup row has "discovery_id" and
   "discovery_status"). Map dashboard stages to API statuses:
   Sourced->Discovered, Screening->Under Review, Due Diligence->Due Diligence, IC Review->Due Diligence,
   Committed->Due Diligence, Passed->Rejected, Watchlist->Watchlist.
   If VCD_API_TOKEN is set, send it in the X-API-Key header (read the token from config.js; document it).
6. Add the dashboard's origin (e.g. http://127.0.0.1:3000) to VCD_CORS_ORIGINS in .env.example docs.

STEP 3 - ADD NEW SECTIONS (same visual style as the existing app; reuse its CSS classes)
Add new navigation tabs. Use only the existing endpoints (see /docs on the running API):
A. "Discovery"  - GET /api/startups with filters: industry, funding stage (values from GET /api/filters),
   pipeline status, minimum data confidence, minimum investment score, discovered-after date, search box,
   sort (newest, score, confidence, funding). Show name, industry, stage, discovery date, confidence label,
   investment score + rating, flags (conflicting_funding, possible_duplicate, stale, name_collision).
B. "Research profile" for each discovered company - GET /api/startups/{id}: funding history with evidence
   label per round (show evidence_meaning as a tooltip), named investors (lead marked), founders and
   key_people (label key_people as "Executives listed on SEC filing"), SEC filing links + the Form D
   disclaimer text returned by the API, news history with event tags and tone (show the matched words),
   investment thesis, risks, factor-by-factor score with evidence links, the list of unscorable factors and
   why, confidence breakdown, review history. Allow analyst score overrides
   (POST/DELETE /api/startups/{id}/score-override, note required) and field edits with a source URL
   (PATCH /api/startups/{id}).
C. "Research pipeline" board with the 7 statuses: Discovered, Needs Verification, Under Review, Watchlist,
   Due Diligence, Rejected, Archived (GET /api/pipeline, POST /api/startups/{id}/status).
D. "Automation":
   - "Run Discovery" button -> POST /api/discovery/run (optional source/group selection), then poll
     GET /api/jobs every 5 seconds until the new jobs finish; show results.
   - Source connectivity table from GET /api/sources/status (health, last success, access notes,
     disabled reason).
   - Failed job log (GET /api/jobs?status=failed), last successful update per source.
   - Schedule display (GET /api/schedule).
   - Duplicate review queue: GET /api/duplicates; buttons "Merge (keep A)", "Merge (keep B)",
     "Not a duplicate" -> POST /api/duplicates/{id}/resolve.
   - SEC match review: GET /api/sec/filings?match_status=needs_review; "Link" / "Reject" ->
     POST /api/sec/filings/{id}/match.
   - "Refresh scores" -> POST /api/scores/refresh. Weight editor -> GET/PUT /api/scoring/weights
     (must total 100; show the API's validation error).
   - CSV export links (/api/export/startups.csv, funding_rounds.csv, sec_filings.csv) and CSV upload
     (POST /api/import/startups).
Every score shown must carry the text: "Preliminary research indicator, not an investment recommendation."
Escape all text from the API before inserting it into HTML (the app already has an esc() helper).

STEP 4 - ONE-COMMAND STARTUP
Add a root-level README section (and, if useful, npm scripts or a small shell/PowerShell script) that
starts the API and the dashboard together. Keep `node scripts/serve.mjs` working on its own.

STEP 5 - TEST AND VERIFY
1. python -m pytest in discovery-engine must pass. Add tests for any backend change you make.
2. node --check on every changed JS file.
3. Start both servers and load each tab in a browser (or headless browser); confirm there are no console
   errors, that the 20 imported startups appear with unchanged values, and that the dashboard still works
   when the API is stopped (offline fallback).
4. Do NOT run live discovery against external websites in automated tests. Use the existing fixtures.

STEP 6 - REPORT
Finish with a plain-language report for a non-programmer:
- what you changed (file by file),
- exact commands to start everything,
- what you actually tested and the results (paste test output),
- what you could NOT test and why, especially: live RSS feeds, Hacker News API and SEC EDGAR need
  internet access, and SEC requires VCD_SEC_USER_AGENT with my real name and email;
  `python -m vcdiscovery.cli check-sources` verifies each source on my machine,
- any source you disabled or any problem you found.

RULES
- No paid APIs, no OpenAI/Anthropic keys, no new paid services.
- Never fabricate funding, valuation, revenue, investors or founders. Missing data shows "Not disclosed".
- Never present rumours or targets as raised capital; never present a Form D as a confirmed VC round.
- Do not scrape sites that forbid it, bypass paywalls, CAPTCHAs or rate limits.
- No demo or sample companies anywhere.
- Keep changes minimal and consistent with the existing code style.
```
