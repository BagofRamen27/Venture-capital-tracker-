# VentureScout website

A static website (HTML, CSS and plain JavaScript, no build tools or dependencies) published on GitHub Pages.
Data files are generated once a day by `.github/workflows/site.yml`; see the [main README](../README.md) for setup.

## Sections

- **Discover**: companies found automatically by the [discovery engine](../discovery-engine/README.md) in startup news,
  press releases, Hacker News launches and SEC Form D filings. Each company shows funding evidence labels
  (SEC filing, corroborated, company-announced, single-source report, target, rumour), a data-confidence rating,
  a preliminary investment score with the evidence behind each factor, risks, news and source citations.
- **My startups**: your own list. Add companies by hand or with **Track**. Saved in this browser only; use
  **Back up** / **Restore backup** to keep or move it.
- **Dashboard / Financials**: recently funded companies and funding histories from
  [StartupDB](https://startupdb.com) (CC BY 4.0), plus classified funding headlines.
- **Directory, Scorecard, Deal pipeline**: research tools for your saved companies (edits stay in this browser;
  **Local edits → Copy as CSV** exports them).
- **Data status**: when the data last updated, each source's health, recent runs, and a link to run the update now.

Missing information is shown as "Not disclosed"; nothing is filled in with sample or estimated values.
Funding raised is never presented as valuation or revenue.

## Run locally

Requires Node.js 20.11 or later. No `npm install` needed.

```sh
npm run dev            # http://127.0.0.1:3010
npm test               # unit tests
npm run check          # syntax check
npm run build          # static site in dist/
npm run update-market  # download today's StartupDB data into public/data/market.json
```

To see discovered companies locally, run the discovery engine and write its data files:

```sh
cd ../discovery-engine
python -m vcdiscovery.cli run
python -m vcdiscovery.cli refresh-scores
python -m vcdiscovery.cli export-site     # writes ../vc-investment-tracker-web/public/data/*.json
```

Without those files the site still works and shows "Not available yet" for the affected sections.

## Project layout

- `public/`: the website (`index.html`, `app.css`, `app.js`, `scout.js`, `market.js`, `data/config.json`).
- `public/data/*.json` (generated, not committed): `market.json`, `discovery.json`, `news.json`, `status.json`.
- `src/market.js`: StartupDB adapter used by the daily update.
- `scripts/`: `dev.mjs` (local preview), `build.mjs` (static build), `update-market.mjs` (daily StartupDB download).
- `test/`: Node tests.
- `examples/original-research.json`: the original 20-startup research file (not loaded by the site; can be
  imported into the discovery engine with `python -m vcdiscovery.cli import-tracker`).

## License

Application code is [MIT licensed](LICENSE). Third-party research and source material keep their owners' rights.
Preserve attribution and source links.
