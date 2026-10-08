# VentureScout

An open-source startup research dashboard with online discovery, personal company lists, research profiles, scorecards, a deal pipeline, and financial comparisons.

## Startup sources

- The dashboard reads current StartupDB company/funding records and TechCrunch funding headlines. Search and paginate 50 companies at a time. Funding data is source-reported, not independently verified here. Funding detail preserves source links and source-check dates.
- StartupDB facts are reformatted under CC BY 4.0, with attribution and links. Revenue and valuation are not supplied by this API and are explicitly marked unavailable. Funding raised is not revenue or valuation.
- The original 20-startup dataset is preserved only in `examples/original-research.json`; the website does not load it.
- Discover searches the public [StartupWho directory](https://www.startupwho.com/startups) one page at a time. Search by keyword or industry and use Next for more results. Results are cached for one hour, fetched when requested, and labeled with retrieval time. An outage may show explicitly labeled cached results up to seven days old. Funding stage and verified financials are not supplied by this source.
- Sign in to save discovered companies or add your own. There is no application limit of 20 companies. Saved companies also appear in the research directory, scorecards, and pipeline. Source and hosting service capacity still apply.

Discovery does not crawl the whole internet or automatically save new listings. Market records and news refresh on request, cached for 15 minutes; outages can show labeled cached results for up to 24 hours. No background monitoring or alerts are configured. Crunchbase, PitchBook, and Dealroom are not connected.

## Run locally

Use Node.js 24 or later (preview and tests use built-in SQLite).

```sh
pnpm install
pnpm dev
```

Open http://127.0.0.1:3010. Local sign-in creates a development-only identity; it does not authenticate with ChatGPT. This mock runs only in the local preview server, not the production Worker. Preview data stays in ignored `.local/`.

```sh
pnpm test
pnpm check
pnpm build
```

## Project layout and hosting

- `public/`: maintained HTML, styles, JavaScript, and application configuration.
- `src/worker.js`: server-side discovery and owner-scoped company APIs.
- `src/discovery.js`: StartupWho request normalization and factual listing parser.
- `src/market.js`: StartupDB API adapter and linked TechCrunch headlines.
- `db/schema.ts`, `drizzle/`: schema and generated migrations.
- `scripts/dev.mjs`: local preview with SQLite and development identity.
- `scripts/build.mjs`: builds a Cloudflare-compatible Worker into ignored `dist/`.

The hosted app uses Sites with a D1 binding named `DB` and platform ChatGPT sign-in. Every personal-data query checks the trusted platform user ID; writes also check the request origin. Apply generated migrations before deploying the Worker. Other hosts must provide equivalent trusted authentication, D1, and routing. Never trust a user-supplied identity header on an unprotected standalone server. Google Sheets, Supabase, and Vercel are not required.

## Saved data

Company names, websites, industries, stages, locations, and notes are saved per account in D1. Public visitors can browse online discovery, funding records, and headlines. Scorecard and pipeline edits still use existing browser-local storage and do not sync across devices or people. Use **Local edits → Copy as CSV** to export those changes before clearing browser data. A shared team workspace is not included.

## Contributions and licensing

Use issues and pull requests in [the public repository](https://github.com/BagofRamen27/Venture-capital-tracker-). See [CONTRIBUTING.md](CONTRIBUTING.md). Application code is [MIT licensed](LICENSE). Third-party research and source material retain their owners' rights; the code license does not grant rights to that content. Preserve attribution and source links.
