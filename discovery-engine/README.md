# VC Discovery Engine (Phase 1 MVP)

A free, self-hosted research engine for your Venture Capital Tracker. It:

- **discovers startups** from public RSS news feeds, Hacker News (Show HN / Launch HN) and SEC Form D filings
- **extracts** company names, funding amounts, round types and named investors from headlines, using rules you can read
- **deduplicates** repeated articles, syndicated copies and repeated funding announcements
- **labels evidence honestly**: confirmed, company-announced, reported, target, rumour and regulatory filing are never mixed
- **scores** each record for *data confidence* (how well-supported it is) and, separately, a *preliminary investment score* with the evidence and missing items listed
- **writes the website's data files** (`export-site`), which GitHub Actions publishes daily to GitHub Pages
- **serves an optional REST API** (FastAPI) for local research, plus CSV import and export

> Scores are preliminary research indicators built only from public evidence. They are not
> investment recommendations, and no predictive accuracy is claimed.

It does not need any paid API or AI service.

---

## 1. Install (one time)

You need **Python 3.10 or newer**. Check with `python3 --version` (on Windows: `py --version`).

```bash
cd discovery-engine
python3 -m venv .venv                 # creates an isolated Python environment
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                  # Windows: copy .env.example .env
```

Open `.env` in a text editor and set **`VCD_SEC_USER_AGENT`** to your name and email
(for example `Jane Doe jane@example.com`). The SEC requires this for automated access.
Without it, everything except the SEC source still works.

Every later session: `cd discovery-engine` and `source .venv/bin/activate` first.

## 2. First run

```bash
python -m vcdiscovery.cli init-db          # creates data/vc_discovery.db
python -m vcdiscovery.cli import-tracker   # optional: adds the original 20 researched startups
python -m vcdiscovery.cli check-sources    # tests each news/SEC source (saves nothing)
python -m vcdiscovery.cli run              # discovers startups from all enabled sources
python -m vcdiscovery.cli refresh-scores   # computes investment scores
python -m vcdiscovery.cli status           # counts + recent job log
```

## 3. Start the API

```bash
python -m vcdiscovery.cli serve              # http://127.0.0.1:8000
python -m vcdiscovery.cli serve --scheduler  # same, plus the daily/weekly jobs
```

Open **http://127.0.0.1:8000/docs** to see and try every endpoint in your browser.

## 4. Update the website's data

```bash
python -m vcdiscovery.cli export-site      # writes ../vc-investment-tracker-web/public/data/*.json
```

On GitHub this happens automatically every day (`.github/workflows/site.yml`); see the main README for the
one-time setup. Locally, preview the result with `npm run dev` in `vc-investment-tracker-web/`.

---

## Commands

| Command | What it does |
|---|---|
| `init-db` | Create database tables (safe to repeat) |
| `run [--source KEY] [--group news\|funding\|community\|video\|regulatory]` | Run discovery now |
| `enrich [--limit N]` | Fill missing company facts from Wikidata |
| `check-sources [--include-disabled]` | Test every source's URL; nothing is saved |
| `serve [--scheduler] [--port 8000]` | Start the API |
| `schedule` | Run scheduled jobs in this terminal (Ctrl+C stops) |
| `refresh-scores` | Recompute investment scores |
| `import-tracker [PATH]` | Import `vc-investment-tracker-web/examples/original-research.json` |
| `import-csv FILE` | Import companies from CSV (only `name`/`company_name` is required) |
| `export-csv [DIR]` | Write `startups.csv`, `funding_rounds.csv`, `sec_filings.csv` |
| `export-site [DIR]` | Write the website data files (discovery.json, news.json, status.json) |
| `geocode [--max-new 60]` | Look up company cities on OpenStreetMap and write the map's `places.json` |
| `export-hall [DIR]` | Write approved Hall of contributors requests (needs `GITHUB_TOKEN`, `GITHUB_REPOSITORY`) |
| `print-schema [--postgres]` | Print the SQL schema |
| `status` | Record counts and the last 10 jobs |

## API endpoints (summary)

| Area | Endpoint |
|---|---|
| Discovery list (filters: `q, industry, stage, status, min_confidence, min_score, discovered_after, flag, sort`) | `GET /api/startups` |
| Startup profile (rounds, SEC filings, news, signals, citations, score, thesis, risks, history) | `GET /api/startups/{id}` |
| Analyst edit (recorded as a citation) | `PATCH /api/startups/{id}` |
| Research pipeline | `GET /api/pipeline`, `POST /api/startups/{id}/status` |
| Filter values | `GET /api/filters` |
| Funding rounds / news / SEC filings | `GET /api/funding-rounds`, `GET /api/news`, `GET /api/sec/filings` |
| Confirm or reject an SEC match | `POST /api/sec/filings/{id}/match` |
| Duplicate review | `GET /api/duplicates`, `POST /api/duplicates/{id}/resolve` |
| Scoring | `GET/PUT /api/scoring/weights`, `GET/POST /api/startups/{id}/score`, `POST/DELETE /api/startups/{id}/score-override`, `POST /api/scores/refresh` |
| Automation | `POST /api/discovery/run` (the "Run Discovery" button), `GET /api/jobs`, `GET /api/sources/status`, `GET /api/schedule` |
| Import/export | `GET /api/export/*.csv`, `POST /api/import/startups` |

---

## Data sources and permissions

Configured in `config/sources.json`. Set `"enabled": true/false` to switch a source on or off.

| Source | Access | Status |
|---|---|---|
| Hacker News (Algolia HN API) | Free, no key | Enabled |
| Wikidata (official MediaWiki API) | Free, public domain (CC0); identified User-Agent, `maxlag`, one request at a time | Enabled (enrichment) |
| SEC EDGAR Form D (daily index + `primary_doc.xml`) | Free; requires User-Agent with your email; ≤10 req/s (we use ≤4) | Enabled once `VCD_SEC_USER_AGENT` is set |
| TechCrunch (Venture, Startups), Crunchbase News, FinSMEs, EU-Startups, VentureBeat | Public RSS feeds; headline, link and ≤500-char summary only | Enabled |
| PR Newswire (venture capital list) | Public RSS of press releases (labelled *company_announced*) | Enabled |
| Sifted, Business Wire | Feed URL must be confirmed/chosen by you | Disabled |
| Reddit (official Data API, read-only) | Free for non-commercial use; needs a registered "script" app and Reddit's approval | Enabled once `VCD_REDDIT_*` credentials are set |
| YouTube channel feeds (Y Combinator, TechCrunch, a16z, Bloomberg Technology, This Week in Startups, CNBC Television) | Public RSS feeds, no key; title, link and short description only | Enabled |
| YouTube search (official YouTube Data API v3) | Free Google Cloud API key; 4 searches a day (400 of 10,000 free quota units) | Disabled (optional) |
| Product Hunt, YC directory | Need API approval/terms review, or have no public API | Not implemented (Phase 4) |

**Rules the code follows:** it never downloads full articles, never bypasses paywalls, logins,
CAPTCHAs or rate limits, identifies itself, waits between requests, and honours `Retry-After`.
A `401/403` response stops that source and is logged; there is no workaround.

**Verify before relying on a source.** Feed URLs change. This code was tested against recorded
sample responses, not live sites. Run `check-sources` on your own machine and disable any
source that fails. Review each publisher's terms if you plan anything beyond personal research.

---

## How the algorithm decides things

### Evidence labels (funding)
| Label | Meaning | Counted in total funding? |
|---|---|---|
| `regulatory_filing` | SEC Form D. An offering notice, **not** proof of a priced round, valuation or VC participation | No (shown separately) |
| `confirmed` | Company announcement + an independent outlet, or 2+ independent outlets agree (amounts within 10%) | Yes |
| `company_announced` | Press release from the company | Yes |
| `reported` | One news outlet | Yes |
| `target` | "aims to raise", "seeks"… | No |
| `rumor` | "reportedly", "in talks", "sources say"… Repetition never upgrades a rumour | No |
| `community_sourced` | Company facts from Wikidata (website, founded, founders, HQ, industry), never funding | n/a |

Different amounts for the same round within 60 days → both rounds flagged `conflict` and the company flagged `conflicting_funding`.
Different currencies are never converted or summed.

### Duplicate and identity rules
1. Same SEC CIK → same company. 2. Same website domain (never github.com, medium.com, etc.) → same company.
3. Same normalised name ("Acme Robotics, Inc." = "Acme Robotics") → same company, **unless** websites differ
(then two records + a review item). 4. Similar names ("Acme" vs "Acme Robotics") → separate records + a
review item in `GET /api/duplicates`. Fuzzy matches are never merged automatically.
Articles: same cleaned URL = same article. Same headline within 3 days = syndicated copy, which is stored
but does not count as corroboration.

### Wikidata enrichment
`enrich` looks up companies (newest first, 60 per run) on Wikidata and fills **only empty** fields: website,
founding year, founders, headquarters, country, industry and description. A Wikidata item is accepted only if
its official website matches the company's known website, or, when no website is known, if it is the only
company-like item with exactly that name. Each filled field is cited as `community_sourced` with a link to the
item. Matched companies are not looked up again; unmatched ones are re-checked after 30 days.

### Reddit
With credentials set, each run reads the newest posts in r/startups, r/SaaS, r/venturecapital, r/SideProject,
r/ycombinator and r/EntrepreneurRideAlong (list in `config/sources.json`). Posts below 5 points, NSFW and removed
posts are skipped. Only the title, link, score, comment count and subreddit are stored (no post text, no
usernames). Posts link to companies you already track (by website link or exact name) and count towards community
attention; Reddit never creates new companies. Posts stored in the last 60 days are re-checked each run and
deleted from the database if they were deleted or removed on Reddit.

**Setup:** sign in to Reddit, accept the Data API Terms (request access if Reddit asks), create a **script** app
at https://www.reddit.com/prefs/apps, then set `VCD_REDDIT_CLIENT_ID`, `VCD_REDDIT_CLIENT_SECRET` and
`VCD_REDDIT_USERNAME` in `.env` (locally) or the `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` and `REDDIT_USERNAME`
repository secrets (GitHub). Until then the Data status page shows Reddit as "needs configuration".

### YouTube
Two parts, both free:

* **Channel feeds** (no key): each chosen channel's public RSS feed (list in `config/sources.json`). Video
  titles are read like news headlines: "Acme raises $10M Series A" from TechCrunch's channel can create a company
  and a `reported` funding round, cited as a `video` source. The publisher is the channel owner, so a TechCrunch
  video and a TechCrunch article never count as two independent sources.
* **Search** (free API key): the YouTube Data API searches for the phrases in `config/sources.json` (videos from
  the last 48 hours). Results can come from any uploader, so, like Reddit, they only link to companies you already
  track and never create new ones.

Videos are never downloaded and captions are never read; only the title, link, channel and a short description
are stored. Search results are deleted after 30 days, as the YouTube Developer Policies require.

**Setup for search (optional, off by default):** set `"enabled": true` for `youtube_search` in
`config/sources.json`, then in [Google Cloud Console](https://console.cloud.google.com/) create a project, enable
**YouTube Data API v3**, create an **API key** (restrict it to that API), then set `VCD_YOUTUBE_API_KEY` in `.env`
or the `YOUTUBE_API_KEY` repository secret. No billing account is needed.

### Map locations
`geocode` looks up the city each company record states (discovered companies: the city from SEC filings or
Wikidata; StartupDB companies: their listed location) on [OpenStreetMap Nominatim](https://nominatim.org/) and writes
`places.json` for the website's **Map** tab. Nothing is guessed: a company without a stated city, or whose location
only names a state or country, is not placed. Each place is looked up once and cached in the `geocode_cache` table
(places not found are retried after 90 days); new lookups are capped at 60 per run, one per second, as Nominatim's
usage policy requires. Pins mark the city, not a street address. Locations © OpenStreetMap contributors (ODbL).

The map itself uses [Leaflet](https://leafletjs.com/) and Leaflet.markercluster, bundled in
`vc-investment-tracker-web/public/vendor/leaflet/` (BSD-2 and MIT licences included), with OpenStreetMap tiles.

### Data-confidence score (0–100)
Identity (website, SEC CIK) + best source type + independent publishers + freshness + key fields filled −
conflicts − rumour-only funding − unresolved duplicate. The breakdown is stored with each record.
High ≥ 70, Medium ≥ 45, Low < 45.

### Investment score (0–100)
| Factor | Weight | Automatic rule (summary) |
|---|---:|---|
| Market Opportunity | 20% | Proxy: recent funding activity in the same industry (needs ≥20 events in the database) |
| Business Traction | 20% | Launch / customer / partnership news, disclosed revenue |
| Funding & Investor Validation | 15% | Best funding evidence + named lead/other investors |
| Product Differentiation | 15% | **Analyst only.** Unscorable until you add an override |
| Team & Founder Evidence | 10% | Named founders / Form D executives, accelerator; capped at 70 |
| Growth Momentum | 10% | Distinct events (one per type per week) in 90 days + HN attention |
| Financial Evidence | 10% | Disclosed revenue or Form D sold/offered ratio |

Unscorable factors are excluded and listed, never guessed. Coverage < 50% → rating "Insufficient
evidence". Pre-revenue companies are not penalised. Ten articles about one event count once.
Change weights in `config/scoring.json` or with `PUT /api/scoring/weights`; add analyst
overrides with `POST /api/startups/{id}/score-override`. Overrides survive refreshes.

### News classification
Keyword rules tag events (funding, product launch, partnership, customer adoption, leadership change,
layoffs, regulatory, acquisition, legal, grant, accelerator, shutdown) and tone. Every label stores
the words that triggered it, and tone is never used as investment quality.

---

## Scheduling

**For the public website, scheduling is already handled by GitHub Actions** (daily, free, nothing to keep running;
see `.github/workflows/site.yml`). The options below are only for running the engine on your own computer.

`serve --scheduler` or `schedule` runs (UTC): news 06:00 daily, funding 06:30 daily, SEC 07:00
daily, Hacker News every 6 h, scores Monday 08:00. A database lock stops the same job from running
twice at once. If one source is down, it is logged as failed and the others still run.

The scheduler only runs while your computer and that terminal are on. For always-on scheduling for free,
use your operating system's scheduler instead:
- macOS/Linux `crontab -e`: `0 7 * * * cd /path/to/discovery-engine && .venv/bin/python -m vcdiscovery.cli run`
- Windows Task Scheduler: action `C:\path\to\discovery-engine\.venv\Scripts\python.exe`, arguments `-m vcdiscovery.cli run`, start in `C:\path\to\discovery-engine`

## Database

SQLite file at `data/vc_discovery.db`. Tables: startups, funding_rounds, investors, round_investors,
news_articles, article_mentions, sec_filings, discovery_signals, citations, investment_scores,
score_overrides, review_events, duplicate_candidates, job_runs, job_locks, app_settings.
The full SQL is in `docs/schema.sql` (regenerate with `print-schema`).

**Back up** by copying the `.db` file while the server is stopped.

**Moving to PostgreSQL / Supabase later:** install `psycopg[binary]`, set
`VCD_DATABASE_URL=postgresql+psycopg://…`, run `init-db`, then move data with
`export-csv` → `import-csv` (or a tool like `pgloader`). If you change models after you have real data,
add [Alembic](https://alembic.sqlalchemy.org) migrations (`alembic init migrations`, point `target_metadata` at
`vcdiscovery.db.Base.metadata`). `init-db` only creates missing tables; it does not alter existing ones.

## CSV import format

Only `name` (or `company_name`) is required. Recognised columns: `external_id` (or `startup_id`), `website`,
`industry` (or `sector`), `sub_industry`, `description`, `hq_city`, `hq_state`, `hq_country`,
`founded_year`, `funding_stage`, `business_model`, `founders`, `investors`, `valuation_amount`,
`valuation_basis`, `revenue_amount`, `revenue_basis`, `review_status`, `source_url`.
Rows match existing records by id → external_id → website domain → exact name, so re-importing updates
records instead of duplicating them. Financial figures you import are stored as *analyst_entered* with your `source_url`.

## Tests

```bash
python -m pytest
```
59 tests run offline against recorded sample responses in `tests/fixtures/`. They cover parsing,
extraction, deduplication, rumour handling, conflict flags, SEC matching, failure isolation, scoring rules,
the API, CSV round-trips, and the website data export.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Activate the environment (`source .venv/bin/activate`) and run commands from the `discovery-engine` folder |
| SEC source "skipped" | Set `VCD_SEC_USER_AGENT=Your Name you@email.com` in `.env` |
| A source shows `failed` | Run `check-sources`; if the feed moved, update its URL in `config/sources.json` or disable it |
| HTTP 403 from a source | The site refused automated access. Disable that source; do not try to bypass it |
| Browser can't reach the local API (CORS error) | Add the page's address to `VCD_CORS_ORIGINS` and restart `serve` |
| `401 Missing or wrong X-API-Key` | You set `VCD_API_TOKEN`; send it as the `X-API-Key` header or clear it |
| Port 8000 already in use | `serve --port 8001` |
| Want a fresh start | Stop the server and delete `data/vc_discovery.db` |

## Known limitations (honest list)

- Extraction reads headlines with rules; unusual wording is missed (returns nothing rather than guessing).
- Company websites are only known from Hacker News links, CSV or manual edits; news headlines don't include them.
- Form D matching to news companies uses exact names; anything fuzzy goes to manual review.
- The market factor is a proxy for investor activity, not a market-size estimate.
- Not yet: GDELT, SBIR/USAspending grants, Product Hunt, investor-relationship maps (Phases 2–4).
