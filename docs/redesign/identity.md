# Professional redesign: identity and components

PR 2 follows the foundation work merged in #42. Only presentation CSS and review evidence change. No JavaScript, data, storage, routes, logo assets, contributor content or financial formatting code changes.

## Design decisions

- Actual logo pixels include forest `#113C2B`, cream `#FDFBF7` and brass `#D0AE5A`. The theme derives from these rather than introducing an unrelated brand.
- Light: cream background `#F5F1E7`, warm surface `#FFFDF8`, forest text `#142B23`, secondary text `#344B40`, muted text `#53645C`.
- Dark: background `#101C17`, surface `#192B22`, text `#F5F1E7`, secondary text `#C7D3CA`, muted text `#A7BAAC`. Existing system preference and explicit `data-theme` overrides are both supported; no new persistent preference is introduced.
- Brass is used for small decorative borders, not light-background text. Positive, negative, warning, info and neutral tokens are independent of brand tokens. Six data-series tokens use blue/orange/teal/vermilion/purple/slate hues, with brighter dark-theme equivalents; existing charts keep labels and values and now draw from data tokens rather than brand colors. Color is not the only means of identifying a value.
- Controls use 6px corners; cards use 8px. Button variants cover primary, secondary, ghost and destructive, including focus, hover, active and disabled states. Field boundaries and map controls use theme-aware colors.
- About uses the same surfaces and text hierarchy as the research views. Its original logo and all founder content remain; the large watermark, gradients, glass effects, floating animations and hover movement are removed. A cream backing keeps the unchanged hero logo visible in dark mode.
- Existing IBM Plex fonts are retained without the condensed family. No new fonts or dependencies. Font loading uses `display=swap`; the actual transferred font payload was not independently measured.
- Transitions are 180ms and reduced-motion preference disables them.

## Evidence

All twelve navigation sections are included. These are viewport screenshots, not claims that the entire contents of each long page fit in one screen.

| View | Foundation baseline | Final identity |
|---|---|---|
| Light, 1440px | [Before](screenshots/foundations-light-1440.jpg) | [After](screenshots/identity-light-1440.jpg) |
| Dark, 1440px | [Before](screenshots/foundations-dark-1440.jpg) | [After](screenshots/identity-dark-1440.jpg) |
| Light, 390px | [Before](screenshots/foundations-light-390.jpg) | [After](screenshots/identity-light-390.jpg) |
| Dark, 390px | [Before](screenshots/foundations-dark-390.jpg) | [After](screenshots/identity-dark-390.jpg) |
| Light, 768px (Dashboard/Financials) | [Before](screenshots/foundations-light-768.jpg) | [After](screenshots/identity-light-768.jpg) |
| Dark, 768px (Dashboard/Financials) | [Before](screenshots/foundations-dark-768.jpg) | [After](screenshots/identity-dark-768.jpg) |

## Validation and limits

- All **42 existing tests pass** with `node --test`. Syntax checks pass for app.js, market.js, scout.js, map.js and compete.js. `node scripts/build.mjs` passes.
- No page overflow in the 12-section screenshot matrix at 390/1440px in both themes, or Dashboard/Financials at 768px. Additional checks at 320/1280px pass; the full Competitive Analysis editor also fits at 320px. [Width results](width-audit.json).
- Read-only DOM contrast sampling found no text contrast failures across the twelve sections in either theme. It checks rendered text colors against composited ancestor backgrounds, using AA thresholds. This is not a complete accessibility certification and does not test every possible data state, placeholder or image. [Contrast results](contrast-audit.json).
- Keyboard checks: mobile menu opens with Enter, closes with Escape, and selection moves focus to main content; score buttons activate with Enter. Focus rings remain visible. Main navigation, search, profile and pipeline controls were exercised.
- Walkthrough: search for Armadin; open funding details; save it in the isolated local preview; open its profile; set a score; move it to Screening; export and restore a backup. Competitive Analysis opens its full editor on a narrow phone.
- Empty-browser localStorage was identical before/after the redesign. A populated workspace was then rendered with the original CSS and final CSS: all localStorage values remained identical. Backup payloads matched after excluding only `exportedAt`, which the unchanged export function generates on every download. Raw backup files therefore are not byte-identical. [Integrity results](integrity.json).
- Displayed dashboard/card metric strings matched the frozen original snapshot across the screenshot matrix. Armadin's complete funding-detail text also matched exactly, including `$255.5M`, `USD 255,500,000` and undisclosed fields. The sampled source does not contain a negative amount, so negative-number display was not independently exercised. Formatting code is unchanged.
- No captured console warnings or errors during the final walkthrough. Local daily snapshot files and personal test data are not committed.
- **Not verified:** Lighthouse accessibility score >=95, a full screen-reader audit, Safari/iOS, all loading/error combinations, and the font-transfer budget. Those remain review checks; this report does not claim they passed.

## Preview and publication

From `vc-investment-tracker-web`, run `node scripts/dev.mjs`, then open http://127.0.0.1:3010/. Theme follows the operating system. The review screenshots used explicit light/dark attributes in a local-only preview wrapper; that wrapper is not shipped.

This PR targets main after #42. A maintainer must review and merge it before the existing GitHub Pages workflow publishes the second pass. No automatic merge is performed.
