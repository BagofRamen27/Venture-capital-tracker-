# Feature Proposal: Funding Round Verification & Deduplication

## 1. Objective

Improve the reliability of VentureScout by identifying duplicate funding announcements, preserving source evidence, and flagging conflicting information for review.

**Problem:** Multiple articles may report the same funding round. Without deduplication, the tracker risks recording duplicate rounds or inconsistent funding amounts.

**Goal:** Maintain one canonical record per funding event while preserving all supporting sources.

## 2. Proposed Features

### A. Funding Round Matching

Compare incoming records using:
- Canonical company identity and website/domain
- Funding round type
- Announcement date and, where available, closing date
- Reported amount and currency
- Lead and participating investors

Missing fields should reduce match confidence rather than be treated as agreement.

### B. Duplicate Detection

- Identify likely duplicate announcements.
- Assign a transparent match-confidence score.
- Explain the fields that contributed to a match.
- Flag ambiguous cases for review.
- Do not automatically merge records when material fields conflict.

### C. Source Provenance

Preserve the source URL, publisher, publication date, reported amount and currency, round type, and relevant evidence for each announcement.

Distinguish company-confirmed information from investor announcements, media reporting, regulatory filings, and unverified claims.

### D. Verification Status

Use explicit statuses such as:
- **Verified:** sufficient evidence supports the event under documented rules.
- **Needs review:** conflicting or incomplete evidence requires inspection.
- **Unverified:** the claim has not yet been checked adequately.

Avoid implying that a source is independently verified merely because it is available.

## 3. Implementation Approach

1. Inspect the existing discovery engine, funding data model, database schema, and export path.
2. Define a canonical funding-event record and source-evidence structure compatible with the current architecture.
3. Implement conservative matching using normalized company identity, round type, dates, amounts/currencies, and investors.
4. Add conflict detection for inconsistent amounts, currencies, dates, and round types.
5. Integrate matching into ingestion without discarding original source records.
6. Add unit tests and update documentation.
7. Expose verification status in the website only after the backend data contract is agreed.

## 4. Acceptance Criteria

- Multiple articles about the same round can be associated with one canonical funding event.
- All source records remain accessible after matching.
- Conflicting amounts or currencies trigger review rather than silent overwriting.
- Distinct rounds for the same company remain separate.
- Missing values do not automatically count as matches.
- Matching decisions are deterministic and testable.
- Existing ingestion, exports, and website functionality continue to work.
- Tests cover duplicates, conflicting reports, missing fields, and distinct rounds.

## 5. Out of Scope for the Initial Release

- Automated valuation estimation.
- Predicting investment returns.
- Purchasing proprietary financial datasets.
- Fully automated resolution of ambiguous funding events.
- Replacing the existing investment-scoring model.

## 6. Success Metrics

Evaluate the feature against a manually reviewed sample of funding announcements. Track:
- Duplicate-detection precision.
- Missed-duplicate rate.
- Incorrectly merged distinct rounds.
- Percentage of records with traceable sources.
- Number of conflicting records flagged for review.
- Reviewer time required per ambiguous match.

The priority is to minimize incorrect merges, even if some duplicates require manual review.

## 7. Delivery Plan

**Phase 1:** Inspect architecture and establish baseline tests.

**Phase 2:** Implement matching, source preservation, and conflict detection.

**Phase 3:** Add test coverage and integrate with data exports.

**Phase 4:** Add a minimal verification interface and document limitations.

## 8. Pull Request Strategy

This document proposes the feature and acceptance criteria; it does not implement the deduplication logic. After the approach is reviewed, implementation should be delivered in a separate focused PR with tests.

Suggested implementation sequence:
1. Backend matching and source preservation.
2. Export/data-contract updates.
3. Minimal interface for reviewing potential duplicates.
