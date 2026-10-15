# Professional redesign: foundations

Approved phase 0 direction, implemented on the existing static frontend. This first PR changes typography, spacing and navigation sizing only; palette and theme changes belong to the second PR.

- Retained IBM Plex Sans for continuity and dense-view readability; removed the condensed family download. Sora and Manrope are not added. Only existing Sans 400/500/600 and Mono 400/500 are requested, with `display=swap`.
- Shared type tokens: 12/14/16/20/24/32px. App headings stop at 32px; heading tracking is zero. Financial numbers retain their existing display strings with tabular alignment.
- Shared spacing tokens: 4/8/12/16/24/32/48px. Structural sidebar width and control hit targets are separate layout dimensions.
- Existing grouped navigation, selected marker, mobile menu and keyboard behavior retained. Navigation labels are now 14px. About and Competitive Analysis grids can shrink within narrow screens.
- Existing logo files, content, JavaScript, data sources, calculations and storage code are unchanged. The current application has 12 navigation sections, all included.

## Screenshot comparisons

Contact sheets include every section at phone and desktop sizes, plus Dashboard and Financials at tablet size. Each tile is an actual viewport capture; long pages continue below the captured viewport.

| View | Before | Foundations |
|---|---|---|
| Light desktop, 1440px | [Before](screenshots/before-light-1440.jpg) | [After](screenshots/foundations-light-1440.jpg) |
| Dark desktop, 1440px | [Before](screenshots/before-dark-1440.jpg) | [After](screenshots/foundations-dark-1440.jpg) |
| Light phone, 390px | [Before](screenshots/before-light-390.jpg) | [After](screenshots/foundations-light-390.jpg) |
| Dark phone, 390px | [Before](screenshots/before-dark-390.jpg) | [After](screenshots/foundations-dark-390.jpg) |
| Light tablet, 768px | [Before](screenshots/before-light-768.jpg) | [After](screenshots/foundations-light-768.jpg) |
| Dark tablet, 768px | [Before](screenshots/before-dark-768.jpg) | [After](screenshots/foundations-dark-768.jpg) |

## Validation

- All 42 existing Node tests pass; syntax checks of app, market, scout, map and compete pass; static production build passes.
- All 12 sections at 390/1440px in both themes and Dashboard/Financials at 768px: no page-wide overflow.
- Rendered metrics compared against a frozen copy of the public daily snapshot. No formatting/calculation implementation changed.
- Local preview data downloads and build outputs are ignored and are not included in this PR.
- Complete accessibility, populated workspace flows, 320/1280px and final identity validation are recorded with PR 2. This pass intentionally retains existing colors, including existing contrast limitations.

Preview locally: `cd vc-investment-tracker-web`, then `node scripts/dev.mjs` (port 3010). Run checks with `node --test`, `node --check public/app.js`, and `node scripts/build.mjs`. GitHub Pages will not change until the PRs are merged by a maintainer.
