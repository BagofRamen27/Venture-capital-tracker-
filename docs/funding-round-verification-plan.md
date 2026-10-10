# Funding Round Resolution: Gap-Focused Implementation Plan

## 1. Purpose

Improve funding-event resolution without rebuilding functionality already present in VentureScout.

The current discovery engine already includes:

- A `FundingRound` model with event attributes, publisher tracking, conflict flags, and source links.
- `NewsArticle` and `Citation` records that preserve article-level evidence.
- A funding matcher in `vcdiscovery/funding.py` that compares dates, round types, currencies, amounts, and publishers.
- Company duplicate candidates and review events.
- Automated tests for corroboration, conflicting amounts, repeated ingestion, and syndicated articles.

Therefore, this work should extend those mechanisms rather than introduce a second canonical-round system or a parallel review queue.

## 2. Confirmed gaps to address

### A. Missing or uncertain event dates

Do not substitute the current date for an unknown announcement date. Publication date, retrieval date, and funding-event date are distinct concepts. An observation with no reliable event date must not be automatically matched using an invented date.

### B. Conservative match decisions

The matcher currently uses a 60-day event window and a 10% amount tolerance. Keep these rules explicit and tested, but make the outcome explainable. Missing amounts must not count as agreement. Round type and currency compatibility should remain explicit constraints.

A weighted score must not override a material contradiction. When evidence is insufficient, create a separate provisional round or reviewable candidate rather than silently merging records.

### C. Source evidence versus canonical values

Keep article and citation evidence intact when several sources refer to one round. A canonical round's displayed amount, date, and status should be explainable from those observations. Do not replace a conflicting source claim with the last value ingested.

The initial implementation may use the existing `NewsArticle`, `Citation`, `FundingRound`, and publisher fields. Add a dedicated source-claim table only if tests and schema inspection demonstrate that existing relationships cannot preserve the necessary field-level evidence.

### D. Corroboration quality

Repeated publishers, syndicated stories, and articles copying the same press release must not be counted as independent confirmation. Preserve source URLs and publisher attribution; where independence cannot be established, do not upgrade verification status solely from repetition.

### E. Reviewable ambiguity

Reuse existing duplicate-candidate and review mechanisms where appropriate. A reviewer must be able to see the candidate records, source evidence, matching signals, contradictions, and reason for withholding an automatic match. A manual resolution should remain stable across identical re-ingestion.

## 3. Matching contract

Resolve company identity before funding-event identity.

For a funding event, compare:

1. Canonical company ID.
2. Normalized round type.
3. Event date, only when known and reliable.
4. Amount and currency, without treating missing values as agreement.
5. Investor evidence, where available.
6. Source URLs, publisher identity, and existing source-record identifiers.
7. Material contradictions, which constrain or prevent automatic matching.

Possible outcomes:

- **Matched/corroborated:** adequate compatible evidence supports the same event; preserve the incoming source evidence.
- **Conflict/review:** the records may describe the same event, but material values disagree or evidence is insufficient.
- **Distinct/new:** evidence supports a separate event, or no credible match exists.

A numerical match score may rank candidates, but each decision must retain its reason and rule version. Do not add a probabilistic matching dependency in this first implementation.

## 4. Idempotency requirements

- Re-ingesting the same source record must not create another article, citation, or funding round.
- Re-ingesting an unchanged article must not increase the number of independent publishers.
- A changed source record must be re-evaluated without erasing the earlier evidence needed to explain a previous decision.
- Repeated ambiguous observations should update the same review item where a stable key exists.
- Concurrent ingestion must respect existing database constraints and job locks; add uniqueness constraints or transaction handling where tests expose a race.

## 5. Implementation sequence

1. Establish baseline tests against the current `funding.py`, `pipeline.py`, and relevant models.
2. Preserve missing event dates and reject underdetermined automatic matches.
3. Make match outcomes and conflict reasons explicit and deterministic.
4. Ensure article/citation evidence remains attached to a canonical round and conflicting values are not silently overwritten.
5. Improve independent-source/corroboration handling without treating syndication as independent evidence.
6. Reuse the existing review/duplicate mechanisms for ambiguous cases.
7. Add regression tests and verify the generated JSON/API/dashboard contracts still work.

Schema migrations should be coordinated with the separate schema-migration workstream; do not add a new persistence framework as part of this feature.

## 6. Required regression tests

- Same source record ingested twice.
- Same funding round reported by two independent sources.
- Same article or story syndicated across multiple publishers.
- Conflicting amounts for a plausible same-round candidate.
- Missing amount and/or event date.
- Different currencies or incompatible round types.
- Two distinct rounds for one company within the date window.
- Similar company names that resolve to different company IDs.
- Rumour followed by a substantiated report.
- Repeated ingestion after a manual review decision.
- Failed or retried ingestion without partial duplicate records.

Tests should assert both the canonical round count and the preservation of source evidence and conflict state.

## 7. Acceptance criteria

- Identical inputs do not inflate canonical company or funding-round counts.
- Unknown event dates remain unknown.
- Missing amounts are not treated as proof of a match.
- Material conflicts are preserved and reviewable.
- Independent corroboration is distinguished from syndication or repeated reporting.
- Every resolved round remains traceable to its supporting source observations.
- Existing exports, API responses, and static dashboard data remain compatible or are versioned deliberately.
- Tests quantify false merges as a critical failure; uncertain matches are preferable to destructive merges.

## 8. Out of scope

- Replacing the existing investment-scoring model.
- Rebuilding company identity resolution from scratch.
- Introducing a second canonical funding-event database or review queue.
- Predicting valuation or investment returns.
- Purchasing proprietary data or bypassing source access restrictions.
- A full dashboard redesign; this feature only needs the minimum review visibility supported by existing contracts.

## 9. Success measures

Evaluate a manually reviewed sample and track:

- Precision of duplicate matches.
- Missed duplicate rate.
- Incorrectly merged distinct rounds.
- Percentage of rounds with traceable evidence.
- Number and age of unresolved conflicts.
- Re-ingestion stability.
- Reviewer time per ambiguous case.

Prioritize minimizing incorrect merges, even if some true duplicates remain separate until reviewed.

## 10. Delivery note

This document is a gap-focused specification, not an implementation. The codebase already contains much of the matching and evidence infrastructure described above. The implementation PR should change only the rules, provenance links, and tests needed to close the confirmed gaps.
