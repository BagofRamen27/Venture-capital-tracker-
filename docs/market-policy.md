# StartupDB Market Refresh Policy & Resilience Specification

This document specifies the operational behavior, data flow, failure-handling semantics, and command-line options for the StartupDB market refresh process in VentureScout.

---

## 1. Overview and Purpose

VentureScout displays recent startup funding events and historical funding rounds sourced from the [StartupDB](https://startupdb.com) public API (`https://startupdb.com/api/v1/startups`) under the **CC BY 4.0** license.

The market refresh mechanism is implemented in:
- Adapter logic: [`vc-investment-tracker-web/src/market.js`](../vc-investment-tracker-web/src/market.js)
- Automation script: [`vc-investment-tracker-web/scripts/update-market.mjs`](../vc-investment-tracker-web/scripts/update-market.mjs)
- Workflow integration: [`.github/workflows/site.yml`](../.github/workflows/site.yml)
- Test verification: [`vc-investment-tracker-web/test/market.test.mjs`](../vc-investment-tracker-web/test/market.test.mjs)

The resulting dataset is written to `vc-investment-tracker-web/public/data/market.json` and consumed client-side by the **Dashboard** and **Financials** views.

---

## 2. Data Flow and Daily Automation

The market data lifecycle follows an automated sequence in GitHub Actions (`.github/workflows/site.yml`):

1. **Snapshot Restoration:**
   The workflow fetches the latest `market.json` from the orphan persistence branch (`discovery-data`) into `public/data/market.json`.
2. **Refresh Execution:**
   The workflow runs `node scripts/update-market.mjs`.
3. **Snapshot Persistence:**
   If the run is an authorized daily scheduled collection (`COLLECT == 'true'`), the updated `market.json` is committed back to the `discovery-data` branch for the next day's run.
4. **Site Deployment:**
   The static distribution is built (`node scripts/build.mjs`) and deployed to GitHub Pages.

---

## 3. Refresh Execution Modes and Outcomes

The adapter entry point, `updateMarketFile()`, evaluates the outcome of the fetch against the state of the existing file on disk:

```text
                     ┌──────────────────────────┐
                     │   fetchMarket() from     │
                     │       StartupDB          │
                     └─────────────┬────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                 Success                       Failure
                    │                             │
       ┌────────────┴───────────┐         ┌───────┴───────────────┐
       │ Safe atomic write      │         │ Check existing disk   │
       │ exitCode: 0            │         │ snapshot              │
       │ status: 'success'      │         └───────┬───────────────┘
       └────────────────────────┘                 │
                      ┌───────────────────────────┼───────────────────────────┐
                      ▼                           ▼                           ▼
            [ Valid Prior Snapshot ]    [ Corrupt Snapshot ]         [ Missing Snapshot ]
                      │                           │                           │
          ┌───────────┴───────────┐     ┌─────────┴─────────────┐   ┌─────────┴─────────────┐
          │ Retain data           │     │ Preserve corrupt file │   │ Exit code: 1          │
          │ Mark stale: true      │     │ Exit code: 1          │   │ status:               │
          │ Record lastError      │     │ status:               │   │   'missing_snapshot'  │
          │ Atomic rewrite        │     │   'corrupt_snapshot'  │   └───────────────────────┘
          └───────────┬───────────┘     └───────────────────────┘
                      │
            ┌─────────┴─────────┐
         Default              Strict
            │                   │
      ┌─────┴──────┐      ┌─────┴──────┐
      │ exitCode: 0│      │ exitCode: 1│
      │ status:    │      │ status:    │
      │ 'degraded' │      │ 'degraded' │
      └────────────┘      └────────────┘
```

### A. Successful Refresh (`status: 'success'`, `exitCode: 0`)
- Pages through the StartupDB API up to `--pages` (default: 4 pages, 50 companies per page).
- Retrieves detailed funding histories for up to `--details` companies (default: 200).
- Normalizes companies and rounds, preserving date precision and source attribution without substituting funding for revenue or valuation.
- Writes the new dataset to disk atomically.
- Returns `exitCode: 0`.

### B. Graceful Degradation / Stale Retention (Default Mode: `status: 'degraded'`, `exitCode: 0`)
When StartupDB is temporarily unreachable (e.g., HTTP 5xx, timeout, or network drop), and a **valid prior snapshot exists**:
- **Preserves Existing Records:** Keeps all previously verified companies and funding histories. Never deletes data or substitutes synthetic sample data.
- **Marks Metadata:** Sets `stale: true`, records `lastError: <message>`, and updates `lastAttemptAt: <ISO timestamp>`.
- **Logs Workflow Warning:** Outputs `::warning::StartupDB refresh failed (<message>); retained previous snapshot marked stale`.
- **Exit Status:** Returns `exitCode: 0` by default.
  *Operational Rationale:* Transient third-party API outages do not abort the daily site publication or bring down the live website.

### C. Strict Mode (`--strict` flag: `status: 'degraded'`, `exitCode: 1`)
When invoked with `--strict`:
- The graceful degradation logic still safely retains the valid prior snapshot and marks it stale on disk.
- However, `updateMarketFile()` returns `exitCode: 1` instead of `0`.
  *Operational Rationale:* Used in CI environments or verification workflows where fresh data acquisition is mandatory and stale fallback is treated as a build failure.

### D. Hard Failure States (`exitCode: 1`)
1. **Missing Snapshot (`status: 'missing_snapshot'`, `exitCode: 1`):**
   If StartupDB is unreachable and no previous `market.json` exists on disk (e.g. initial repository clone), the script cannot construct valid data and fails with exit code `1`.
2. **Corrupt Snapshot (`status: 'corrupt_snapshot'`, `exitCode: 1`):**
   If StartupDB is unreachable and the existing file contains invalid JSON or fails schema validation (`!Array.isArray(data.companies)`), the corrupt file is preserved for diagnostics and the script exits with code `1`.

---

## 4. Atomic Write Safety (`safeWriteJSON`)

To prevent corrupted or partially written files caused by process termination, power loss, or runner preemption:
- `safeWriteJSON()` writes content to a temporary file unique to the process and timestamp (`<filePath>.<pid>.<timestamp>.tmp`).
- Flushes data to disk and atomically renames the temporary file to the destination path (`fs.renameSync`).
- Guarantees that any reader either reads the complete previous snapshot or the complete new snapshot, never a partial state.

---

## 5. Command-Line Reference

The update script can be run locally or in automation via:

```bash
# Standard daily refresh (graceful degradation enabled)
node scripts/update-market.mjs

# Strict mode: fail CI with exit code 1 if upstream refresh fails
node scripts/update-market.mjs --strict

# Custom pagination and detail limits
node scripts/update-market.mjs --pages 2 --details 50

# Custom output file path
node scripts/update-market.mjs --out ./custom/path/market.json
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--pages` | Number | `4` | Maximum number of listing pages (50 items/page) to fetch. |
| `--details` | Number | `200` | Maximum number of company detail endpoints to fetch. |
| `--strict` | Flag | `false` | If set, exits with code `1` on refresh failure even if a valid snapshot is kept. |
| `--out` | String | `public/data/market.json` | Destination path for the generated market JSON. |

---

## 6. Automated Test Coverage

The behavior specified in this document is verified by automated tests in [`vc-investment-tracker-web/test/market.test.mjs`](../vc-investment-tracker-web/test/market.test.mjs):
- `successful complete refresh updates snapshot with fresh data and exit code 0`
- `refresh failure with valid prior snapshot preserves data and marks stale in default mode`
- `refresh failure with valid prior snapshot returns exit code 1 when strict mode is enabled`
- `first-page failure with no prior snapshot fails explicitly with exit code 1`
- `later-page pagination failure does not overwrite complete snapshot with partial data`
- `corrupt snapshot file is not overwritten and fails explicitly with exit code 1`
- `repeated refresh failures update lastAttemptAt and lastError while keeping initial companies`
- `safeWriteJSON ensures atomic writes and cleans up temporary files`
