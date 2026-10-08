# Contributing

1. Open an issue describing the bug or proposed change.
2. Fork the public repository, or create a branch if you have collaborator access.
3. Work inside `vc-investment-tracker-web/`, install with `pnpm install`, and run `pnpm dev` (Node 24+).
4. Run `pnpm test`, `pnpm check`, and `pnpm build`; check affected views on desktop and mobile.
5. Submit a pull request describing the change and how you checked it.

Keep changes focused and preserve existing research IDs and source citations.
For data corrections, include a source URL and explain what changed. Distinguish
verified records from company claims. Never commit keys, private company research,
personal credentials, local environment files, or browser storage exports.

Company details are stored per account. Preserve user isolation and same-origin
write checks. Scorecards and pipeline edits remain browser-local. Do not commit
`.local/`, generated `dist/`, dependency folders, or runtime database records.

Contributions to application code are provided under the repository's MIT license.
