# Venture Capital Tracker

An open-source startup research dashboard with a searchable directory, company
profiles, investment scorecards, a deal pipeline, and financial comparisons.

This edition uses the included research snapshot: 20 startups, 25 funding rounds,
and 144 source claims. The data is preserved from the supplied project and is not
independently verified by this deployment. Google Sheets, Supabase, and Vercel
are not required.

## Run locally

Install Node.js 20 or later. There are no third-party dependencies.

```sh
cd vc-investment-tracker-web
node scripts/serve.mjs
```

Open the printed local address. For a quick syntax check:

```sh
node --check dist/app.js
```

## Discovery engine (backend)

`discovery-engine/` is a free Python/FastAPI research engine that discovers startups from public
news feeds, Hacker News and SEC Form D filings, scores evidence quality and research signals, and
exports data in the format this dashboard reads. See [discovery-engine/README.md](discovery-engine/README.md).
To connect it to this dashboard with OpenAI Codex, use
[discovery-engine/docs/CODEX_PROMPT.md](discovery-engine/docs/CODEX_PROMPT.md).

## Project layout

- `dist/index.html`: page shell and navigation.
- `dist/app.css`: responsive styles.
- `dist/app.js`: calculations, views, scorecards, pipeline, and local edits.
- `dist/data/demo-data.json`: the included research snapshot.
- `scripts/serve.mjs`: optional local preview server.

`dist/` contains the maintained source files; it is not generated build output.
No build step is required. Serve that directory with any static web host.

## Data and edits

Scores, evidence notes, and pipeline edits are saved in the current browser's
local storage. They do not sync between people or devices. Clearing browser data
removes those edits. Use **Local edits → Copy as CSV** to share or back them up.
The website label identifies the imported snapshot rather than implying live data.

## Work with others

Public repository: https://github.com/BagofRamen27/Venture-capital-tracker-

Use issues for bugs and proposed changes, and pull requests for contributions.
See [CONTRIBUTING.md](CONTRIBUTING.md). Repository owners can invite collaborators
through GitHub repository settings; other contributors can fork the repository.

## License and data sources

The application code is available under the [MIT license](LICENSE).
Third-party research, company information, linked sources, and their underlying
rights remain with their respective owners. The code license does not grant
rights to third-party source material. Preserve source links and verification
labels when editing the research data.
