# VentureScout

Open-source startup discovery, reported funding, news, and personal research lists.
Free to run: a static website on **GitHub Pages**, refreshed once a day by **GitHub Actions**.
No servers, no paid services, no sign-in.

Live site (after the one-time setup below): https://bagoframen27.github.io/Venture-capital-tracker-/

## What's in this repository

| Folder | What it is |
|---|---|
| [`vc-investment-tracker-web/`](vc-investment-tracker-web/README.md) | The website: Discover, My startups, Dashboard, Directory, Scorecard, Deal pipeline, Financials, Data status |
| [`discovery-engine/`](discovery-engine/README.md) | Python engine that finds startups in news feeds, Hacker News and SEC Form D filings, checks the evidence, and scores it |
| `.github/workflows/site.yml` | Daily job: run discovery, refresh StartupDB funding data, publish the website |
| `.github/workflows/tests.yml` | Runs all tests on every push and pull request |

## One-time setup (about 5 minutes)

1. **Turn on GitHub Pages:** repository **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. **Add your SEC contact** (the SEC requires a name and email for automated access):
   **Settings → Secrets and variables → Actions → New repository secret**,
   name `VCD_SEC_USER_AGENT`, value `Your Name your.email@example.com`.
   Without it, everything except SEC Form D data still works.
3. **Run it once now:** **Actions → Update data and publish site → Run workflow**. It takes about 5–10 minutes,
   then the site is live at the address above. After that it updates itself every day at 07:17 UTC.

GitHub pauses scheduled jobs in repositories with no activity for 60 days. If that happens, GitHub emails
you; click **Enable workflow** on the Actions tab.

## How your data is stored

- **Discovered companies, news and funding data** are public-source data, rebuilt daily and published with the site.
  The discovery database is kept between runs on the `discovery-data` branch.
- **My startups, scores and pipeline edits** stay in your own browser. They are private to that browser and
  don't sync between devices. Use **My startups → Back up** to download a copy and **Restore backup** to load it elsewhere.

## License and data sources

Application code: [MIT](LICENSE). StartupDB facts are used under CC BY 4.0 with attribution. News headlines link to
their publishers; only headlines and short summaries are stored. Third-party content keeps its owners' rights.
See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute.
