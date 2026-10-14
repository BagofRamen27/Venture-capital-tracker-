### Summary

<!-- Provide a concise 1-3 sentence summary of what this pull request does and why. -->

### Related Issue

<!-- Link the relevant issue here. Use 'Fixes #<number>' for issues resolved by this PR, or 'Relates to #<number>'. -->
Fixes #

### Type of Change

- [ ] Bug fix (non-breaking fix that resolves an issue)
- [ ] Security fix (vulnerability remediation)
- [ ] New feature (non-breaking feature addition)
- [ ] Documentation (updates to README, docs, or community files)
- [ ] Refactoring / Code quality (no functional change)

### Component(s) Affected

- [ ] Discovery Engine (`discovery-engine/`)
- [ ] Web Application (`vc-investment-tracker-web/`)
- [ ] Workflows & Automation (`.github/workflows/`)
- [ ] Documentation (`docs/`, root Markdown)

### Verification & Testing

<!-- Detail the testing performed to verify this change. -->

- [ ] **Discovery Engine Tests:** `cd discovery-engine && python -m pytest` (if Python code was touched)
- [ ] **Web Application Tests:** `cd vc-investment-tracker-web && node --test` (if web code was touched)
- [ ] **Web Syntax Check:** `cd vc-investment-tracker-web && npm run check` (if web code was touched)
- [ ] **Manual / Browser Testing:** Verified locally on desktop/mobile viewports

### Contributor Checklist

- [ ] My branch is created from and rebased on the latest `upstream/main`.
- [ ] I have not committed any credentials, API keys, passwords, or `.env` files.
- [ ] I have not committed generated data files (`market.json`, `discovery.json`, `news.json`, `status.json`, `dist/`, or `*.db`).
- [ ] Existing tests and backward compatibility are preserved.
- [ ] Relevant documentation has been added or updated if behavior changed.
