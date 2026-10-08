# VC Discovery Engine (Phase 1 MVP)

A free, self-hosted research engine for your Venture Capital Tracker. It:

- **discovers startups** from public RSS news feeds, Hacker News (Show HN / Launch HN) and SEC Form D filings
- **extracts** company names, funding amounts, round types and named investors from headlines, using rules you can read
- **deduplicates** repeated articles, syndicated copies and repeated funding announcements
- **labels evidence honestly**: confirmed, company-announced, reported, target, rumour and regulatory filing are never mixed
- **scores** each record for *data confidence* (how well-supported it is) and, separately, a *preliminary investment score* with the evidence and missing items listed
- **serves a REST API** (FastAPI) that your existing dashboard can call
- **exports** a JSON file in the exact format your current dashboard already reads, plus CSV import and export

> Scores are preliminary research indicators built only from public evidence. They are not
> investment recommendations, and no predictive accuracy is claimed.

It does not need OpenAI, Anthropic or any other paid API.

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
python -m vcdiscovery.cli import-tracker   # copies your dashboard's 20 researched startups into the database
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

## 4. Show the data in your existing dashboard (no code changes)

```bash
python -m vcdiscovery.cli export-snapshot ../vc-investment-tracker-web/dist/data/demo-data.json
```

This rewrites the file your dashboard already loads, using database records. Your 20 imported startups come
back with every original field unchanged; newly discovered companies are added with the same columns.
Back up the original file first if you want to keep it: `cp ../vc-investment-tracker-web/dist/data/demo-data.json demo-data.backup.json`.
The live way (dashboard reads `GET /api/dashboard/snapshot` directly) is part of the Codex prompt in `docs/CODEX_PROMPT.md`.

---

## Commands

| Command | What it does |
|---|---|
| `init-db` | Create database tables (safe to repeat) |
| `run [--source KEY] [--group news\|funding\|community\|regulatory]` | Run discovery now |
| `check-sources [--include-disabled]` | Test every source's URL; nothing is saved |
| `serve [--scheduler] [--port 8000]` | Start the API |
| `schedule` | Run scheduled jobs in this terminal (Ctrl+C stops) |
| `refresh-scores` | Recompute investment scores |
| `import-tracker [PATH]` | Import the dashboard's `demo-data.json` |
| `import-csv FILE` | Import companies from CSV (only `name`/`company_name` is required) |
| `export-csv [DIR]` | Write `startups.csv`, `funding_rounds.csv`, `sec_filings.csv` |
| `export-snapshot FILE` | Write dashboard-compatible JSON |
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
| Import/export | `GET /api/export/*.csv`, `POST /api/import/startups`, `GET /api/dashboard/snapshot` |

---

## Data sources and permissions

Configured in `config/sources.json`. Set `"enabled": true/false` to switch a source on or off.

| Source | Access | Status |
|---|---|---|
| Hacker News (Algolia HN API) | Free, no key | Enabled |
| SEC EDGAR Form D (daily index + `primary_doc.xml`) | Free; requires User-Agent with your email; ≤10 req/s (we use ≤4) | Enabled once `VCD_SEC_USER_AGENT` is set |
| TechCrunch (Venture, Startups), Crunchbase News, FinSMEs, EU-Startups, VentureBeat | Public RSS feeds; headline, link and ≤500-char summary only | Enabled |
| PR Newswire (venture capital list) | Public RSS of press releases (labelled *company_announced*) | Enabled |
| Sifted, Business Wire | Feed URL must be confirmed/chosen by you | Disabled |
| Product Hunt, Reddit, YC directory | Need API approval/terms review, or have no public API | Not implemented (Phase 4) |

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

Different amounts for the same round within 60 days → both rounds flagged `conflict` and the company flagged `conflicting_funding`.
Different currencies are never converted or summed.

### Duplicate and identity rules
1. Same SEC CIK → same company. 2. Same website domain (never github.com, medium.com, etc.) → same company.
3. Same normalised name ("Acme Robotics, Inc." = "Acme Robotics") → same company, **unless** websites differ
(then two records + a review item). 4. Similar names ("Acme" vs "Acme Robotics") → separate records + a
review item in `GET /api/duplicates`. Fuzzy matches are never merged automatically.
Articles: same cleaned URL = same article. Same headline within 3 days = syndicated copy, which is stored
but does not count as corroboration.

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
58 tests run offline against recorded sample responses in `tests/fixtures/`. They cover parsing,
extraction, deduplication, rumour handling, conflict flags, SEC matching, failure isolation, scoring rules,
the API, CSV round-trips, and a check that the dashboard's own data round-trips unchanged.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Activate the environment (`source .venv/bin/activate`) and run commands from the `discovery-engine` folder |
| SEC source "skipped" | Set `VCD_SEC_USER_AGENT=Your Name you@email.com` in `.env` |
| A source shows `failed` | Run `check-sources`; if the feed moved, update its URL in `config/sources.json` or disable it |
| HTTP 403 from a source | The site refused automated access. Disable that source; do not try to bypass it |
| Dashboard can't reach the API (CORS error) | Add your dashboard's address to `VCD_CORS_ORIGINS` and restart `serve` |
| `401 Missing or wrong X-API-Key` | You set `VCD_API_TOKEN`; send it as the `X-API-Key` header or clear it |
| Port 8000 already in use | `serve --port 8001` |
| Want a fresh start | Stop the server and delete `data/vc_discovery.db` |

## Known limitations (honest list)

- Extraction reads headlines with rules; unusual wording is missed (returns nothing rather than guessing).
- Company websites are only known from Hacker News links, CSV or manual edits; news headlines don't include them.
- Form D matching to news companies uses exact names; anything fuzzy goes to manual review.
- The market factor is a proxy for investor activity, not a market-size estimate.
- Not yet: GDELT, SBIR/USAspending grants, Reddit, Product Hunt, investor-relationship maps (Phases 2–4).
