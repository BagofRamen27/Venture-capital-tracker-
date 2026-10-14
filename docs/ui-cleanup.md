# Sitewide UI cleanup

## Audit and changes

The eleven horizontal tabs competed for space, page headings had conflicting spacing rules, form controls varied by page, and the contributor gallery used much heavier effects than the research views.

| Area | Applied cleanup |
| --- | --- |
| All pages | Shared typography, spacing, surfaces, focus rings, form sizes and button variants. Dark-mode native controls now follow the page theme. |
| Navigation | Research, Workspace and Project groups; desktop sidebar; collapsible mobile menu with current-page label, Escape dismissal and content focus after selection. Every existing route remains available. |
| Discover | Consistent filters, cards, badges, source evidence and error/loading surfaces. |
| My startups | Unified cards and form controls, including URL fields; keyboard-accessible backup upload. |
| Dashboard | Consistent metric hierarchy, tabular numbers, search and company cards. |
| Directory | Shared table/card styling and keyboard-focusable scrolling tables. |
| Map | Search and filters match the other pages, with single-column controls on narrow screens. |
| Scorecard | Consistent scoring buttons, input sizing and table presentation. |
| Deal pipeline | Spaced columns and cards, contained keyboard-scrollable board; removed obsolete Sheets-sync wording. |
| Financials | Consistent funding-history cards, labels and figures. |
| Data status | Readable shared tables with contained horizontal scrolling. |
| Hall of contributors | Portraits and plaques retained with subtle frames; heavy gradients/shadows removed. |
| About | Consistent headings, readable text widths and responsive founder profiles. |

## Design standards

- Existing blue accent and IBM Plex identity retained; no new dependencies or icon libraries.
- Spacing scale: 4, 8, 12, 16, 24, 32px. Cards use 10px corners and subtle borders.
- Desktop controls are at least 40px high; primary phone controls are at least 44px.
- Sidebar begins at 1000px. Below that, all navigation is available in the labelled menu.
- Dense tables and deal stages scroll within their own labelled, focusable regions.
- A skip link moves focus to content without changing the current application route.

## Validation

- All 28 existing website tests pass; JavaScript syntax checks and production build pass.
- All eleven pages were opened at desktop width and 390px phone width, with no page-wide horizontal overflow.
- Checked populated local-only startup save, scorecard and pipeline views, plus the normal loading/empty states. Public source snapshots were downloaded only for local preview and are not committed.
- No console errors during the page walkthrough. Dark appearance was visually inspected; light palette was reviewed in CSS. This is not a full screen-reader or cross-browser certification.

## Scope and remaining work

Changed `public/index.html`, `public/app.css` and navigation/accessibility presentation in `public/app.js`. Financial calculations, scoring rules, data connections and persisted-data formats are unchanged. Existing financial-data accuracy issues are outside this cleanup. Future validation should include Safari/iOS and a screen-reader walkthrough. Publishing requires merging the UI branch into main so the existing GitHub Pages workflow deploys it.
