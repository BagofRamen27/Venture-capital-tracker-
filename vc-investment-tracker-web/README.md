# Startup Investment Tracker

A web app for a small VC team to browse, score and diligence a verified startup research database:
dashboard, searchable directory, startup profiles, investment scorecard, deal pipeline and financial analysis.

It ships with the real research snapshot (20 startups, 25 funding rounds, 144 source claims, IDs `DS-001`..`DS-020`)
and can read the live Google Sheet once you add credentials. Nothing in it is sample or invented data.

## What is in this folder

| Path | What it is |
|---|---|
| `public/index.html`, `public/app.css`, `public/app.js` | The website (plain HTML, CSS and JavaScript, no build step) |
| `public/data/demo-data.json` | The CSV snapshot the site shows until Google Sheets is connected |
| `api/data.js` | Server route that reads the Google Sheet (read-only) and returns the same data shape |
| `api/health.js` | Shows whether Sheets is configured; `/api/health?check=1` runs a real test read |
| `lib/sheets.js` | Google sign-in with a service account and the tab-to-data mapping, by header name |
| `vercel.json` | Vercel settings: serve `public/`, security headers, function timeout |
| `.env.example` | The environment variables, with no values |
| `test/` | Offline tests: the sheet mapping against the real workbook values, read-only scope, no credential leaks |
| `scripts/dev-server.mjs` | Optional local preview (`npm run dev`) |

There are no third-party dependencies. Node 20 or newer runs everything.

## How data loading works

1. The page asks `/api/data` for data.
2. If `SHEET_ID` and `GOOGLE_SERVICE_ACCOUNT_JSON` are set, the server signs in as the service account with the
   `spreadsheets.readonly` scope, reads the six data tabs plus the weights and thresholds in Lists & Settings, and
   returns them. The top bar then says **Google Sheets · read-only**.
3. Otherwise, or if the read fails, the page uses `public/data/demo-data.json` and the top bar says
   **Demo mode · CSV snapshot**. Hover the badge to see why.

The badge only says Google Sheets when a read from the sheet actually succeeded on that page load.
Credentials stay on the server: the browser never receives them, and error messages never include them.

Score and pipeline edits are saved in each person's browser and logged in the Change Requests format
(**Local edits** button, with Copy as CSV). They are not written to the sheet; the integration is read-only by design.

## Put it on GitHub (no coding)

1. Unzip `vc-investment-tracker-web.zip`.
2. On github.com, click **New repository**. Name it (for example `vc-investment-tracker`), choose **Private**, and create it.
3. On the empty repository page, click **uploading an existing file**.
4. Open the unzipped folder, select everything inside it (not the folder itself), and drag it onto the page.
   Some computers hide files whose names start with a dot; `.gitignore` and `.env.example` are optional, so it's fine if they don't upload.
5. Click **Commit changes**.

## Deploy to Vercel (no coding)

1. Sign in at vercel.com with your GitHub account.
2. Click **Add New → Project**, find the repository, and click **Import**.
3. Leave **Framework Preset** as **Other** and leave the build settings empty (`vercel.json` already sets them).
4. Click **Deploy**. After about a minute you get a URL. The site opens in **Demo mode · CSV snapshot**.

Every later commit to GitHub redeploys automatically.

## Connect the Google Sheet (read-only)

Do this when you are ready. Until it is done and tested, the site keeps showing the snapshot.

1. In console.cloud.google.com, create a project (or pick one), then open **APIs & Services → Library** and enable **Google Sheets API**.
2. Open **IAM & Admin → Service Accounts → Create service account**. No roles are needed.
3. Open the new service account → **Keys → Add key → Create new key → JSON**. A key file downloads. Treat it like a password.
4. Open your tracker Google Sheet → **Share**, and add the service account's email (it ends in `iam.gserviceaccount.com`) as a **Viewer**.
5. Copy the sheet ID from its URL: the part between `/d/` and `/edit`.
6. In Vercel, open the project → **Settings → Environment Variables** and add:
   - `SHEET_ID`: the ID from step 5
   - `GOOGLE_SERVICE_ACCOUNT_JSON`: the entire contents of the key file from step 3
   Mark both as **Sensitive**.
7. Open **Deployments**, click the menu on the latest one, and choose **Redeploy**.
8. Test the connection: open `https://<your-site>/api/health?check=1`.
   - `"connection": "ok"` with row counts (20 startups, 25 rounds, 144 claims) means it works, and the site badge switches to **Google Sheets · read-only**.
   - `"connection": "failed"` comes with a plain-language `problem`, for example that the sheet isn't shared with the service account.

The sheet must keep the tracker's tab names (Startup Database, Funding Rounds, Financial Analysis,
Investment Scorecard, Deal Pipeline, Source Verification, Lists & Settings) and the machine column names in row 1.
Columns are read by header name, so reordering columns is safe.

To force the snapshot even with credentials set, add `DATA_SOURCE=demo`.

## Run the checks locally (optional)

```
npm test        # offline tests, no network or credentials needed
npm run dev     # preview at http://localhost:3000
```
