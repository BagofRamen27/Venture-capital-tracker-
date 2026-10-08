# Contributing

1. Open an issue describing the bug or proposed change.
2. Fork the public repository, or create a branch if you have collaborator access.
3. Work inside `vc-investment-tracker-web/` and run `node scripts/serve.mjs`.
4. Run `node --check dist/app.js` and check the affected views on desktop and mobile.
5. Submit a pull request describing the change and how you checked it.

Keep changes focused and preserve existing research IDs and source citations.
For data corrections, include a source URL and explain what changed. Distinguish
verified records from company claims. Never commit keys, private company research,
personal credentials, local environment files, or browser storage exports.

The app currently saves edits only in the current browser. Shared data storage
and authentication require a separate implementation; do not make claims of sync
or multi-user saving until those features are implemented and verified.

Contributions to application code are provided under the repository's MIT license.
