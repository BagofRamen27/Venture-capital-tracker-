# Contributing

1. Open an issue describing the bug or proposed change.
2. Fork the public repository, or create a branch if you have collaborator access.
3. Website: work inside `vc-investment-tracker-web/` and run `npm run dev` (Node 20.11+; no dependencies to install).
   Discovery engine: work inside `discovery-engine/` (Python 3.10+; see its README).
4. Run the tests: `npm test && npm run check && npm run build` in the website folder, and `python -m pytest` in
   `discovery-engine/`. Check affected views on desktop and mobile.
5. Submit a pull request describing the change and how you checked it.

Keep changes focused and preserve source citations. For data corrections, include a source URL and explain what
changed. Distinguish verified records from company claims, and never present rumours or fundraising targets as
money raised. Never commit keys, personal credentials, `.env` files, browser storage exports, or generated data
(`public/data/market.json`, `discovery.json`, `news.json`, `status.json`, `dist/`, `*.db`).

Contributions to application code are provided under the repository's MIT license.
