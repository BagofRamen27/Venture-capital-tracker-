# VentureScout — Competitive & Disruption Analysis Engine

> **Implementation specification / build prompt for Claude or Codex**
>
> Repository: https://github.com/BagofRamen27/Venture-capital-tracker-
>
> Website: https://bagoframen27.github.io/Venture-capital-tracker-/
>
> Status: Proposed feature. This document instructs implementation; it does **not** claim the feature is already live.

## 1. Mission

Build a fully integrated **Competitive & Disruption Analysis** research tool inside VentureScout. The user selects or enters a startup and its industry; the tool identifies and compares relevant established businesses, adjacent competitors, and substitutes, then produces an evidence-backed assessment of:

1. **Competitive strength:** Can the startup win customers and defend a sustainable position against current rivals?
2. **Disruption potential:** Could the startup's model reshape industry economics, reach underserved/nonconsuming customers, or undermine an incumbent's current business model?
3. **Incumbent vulnerability:** Which individual incumbents are most exposed, why, and how could they respond?
4. **Investment significance:** What must be true for the thesis to work, what could falsify it, and what evidence is missing?

**Important distinction:** “Competitive,” “disruptive,” “destructive,” and “likely to succeed” are not synonymous. Use **disruption** for a structural change to a market or business model; use **destructive competition** only as a clearly defined impact scenario (e.g., margin erosion or customer displacement), not as a claim that an incumbent will collapse. An innovative startup need not satisfy Christensen's specific disruptive-innovation framework.

## 2. Repository and architecture constraints

Read the current repository, README, contribution and security documentation, architecture guide, tests, and existing research pages **before making changes**. According to the public README inspected October 15, 2026, VentureScout currently uses:

- `vc-investment-tracker-web/`: static vanilla JavaScript/CSS frontend, GitHub Pages, local browser storage for private user data.
- `discovery-engine/`: scheduled Python discovery/research engine.
- `.github/workflows/site.yml`: scheduled refresh and static JSON publication.
- Existing Discover, My startups, Dashboard, Directory, Scorecard, Deal pipeline, Financials and Data status capabilities.

**Preserve these foundations.** Do not introduce required user accounts, paid API keys, a paid backend, or remote storage of personal research. Integrate with existing startup profiles, navigation, data status, scoring, and import/export features. Prefer static generated research snapshots plus interactive client-side comparisons; optional local/development-only research services must be clearly separated from publicly deployed functionality.

Do not assume filenames, DOM patterns, schemas, or routes beyond those actually found in the repo. Match the project's actual patterns and conventions. Never break existing user records or saved-data formats.

## 3. User flow and interface

Add a navigation destination named **Competitive Analysis** under Research, consistent with the site's current navigation design and mobile menu.

### Startup selection

- Search the existing VentureScout startup directory or enter a startup name and website manually.
- Select industry, geography, customer segment, business model, and stage; prefill known information but allow edits.
- Choose comparison type: **Established leaders**, **Direct startup rivals**, **Indirect substitutes**, or **Custom competitors**.
- Default to 3–5 competitors, each validated as a distinct company and relevant product/business unit. Permit adding/removing competitors manually.
- Show company-matching ambiguity before analysis (e.g., similarly named firms) and prevent false competitor matches.
- Make it possible to perform a meaningful manual analysis even if online discovery returns no results.

### Results screen

Create a cohesive, responsive layout with these sections:

1. **Executive verdict** — factual startup summary, key differentiation, best evidence, biggest threat, a cautious one-paragraph assessment, last-researched timestamp.
2. **Two separate headline metrics** — Competitive Strength (0–100) and Disruption Potential (0–100), each with methodology, confidence level, and evidence coverage.
3. **Side-by-side comparison table** — one startup vs. selected incumbents; sortable metrics with explicit units, reporting period, source, and missing-data markers.
4. **Competitive positioning map** — user-selectable X/Y metrics, such as price vs. capabilities or accessibility vs. switching costs. Label qualitative/proxy placements and never pretend such positions are observed numeric measurements.
5. **Industry structure** — Porter Five Forces, market barriers, structural profitability, and likely competitive response.
6. **Competitive moats** — defensibility of startup and incumbents with evidence-based strengths and weaknesses.
7. **Disruption pathways** — new-market, low-end, sustaining, or unclear, with supporting and contradicting evidence.
8. **Incumbent threat matrix** — pairwise startup-versus-incumbent exposure and likely defenses.
9. **Scenarios** — optimistic, base, pessimistic with transparent assumptions and sensitivity controls.
10. **Research dossier** — citations, supporting facts, counterevidence, methodology, uncertainties, export options.

Support mobile layouts, accessibility, keyboard navigation, readable charts/tables, empty/loading/error states, and existing site styling. No cluttered dashboard of arbitrary meters.

## 4. Core research frameworks

### A. Competitiveness — Porter's Five Forces

Assess these at the **industry/segment level**, not as direct measurements of startup quality:

| Force | Research questions |
|---|---|
| Rivalry | How concentrated is the market? What drives price or feature competition? |
| New entrants | What capital, compliance, distribution, network, or technical barriers exist? |
| Supplier power | Are inputs concentrated or proprietary? Is the startup dependent on platforms? |
| Buyer power | Can customers switch easily? Are contracts concentrated? |
| Substitutes | Can customers achieve the same job through a different product or workflow? |

Return qualitative ratings with citations and explain how each factor affects the startup. Do not turn Five Forces into a standalone assertion of probability of success.

### B. Christensen disruption diagnostic

Evaluate observable evidence for:

- Does the startup initially serve **overserved low-end customers** or **previous nonconsumers**?
- Is its offer meaningfully cheaper, simpler, or more accessible on dimensions those customers value?
- Is it initially worse on some conventional performance dimensions but good enough for the target segment?
- Can technology/operations and economics plausibly allow it to move upmarket?
- Is the business model sustainable at that initial segment?
- Is the incumbent **structurally disincentivized** to respond early (margin, channel, customer, organizational conflict)?

Classification: `low_end_disruption`, `new_market_disruption`, `sustaining_innovation`, `other_structural_innovation`, or `insufficient_evidence`. Distinguish theoretical pathway from observed disruption. Avoid labeling any AI company, fast-growing startup, or cheaper product automatically “disruptive.”

### C. Competitive advantages and moats

Examine cost position, differentiation, intellectual property, proprietary data, distribution access, network effects, switching costs, brand, regulatory approvals, capital access, vertical integration, and execution. Analyze incumbent defenses with the same framework. Require evidence for each claimed advantage; patents or funding alone do not prove a moat.

### D. Investment diligence

Inspect market sizing (TAM/SAM/SOM only when defensibly sourced), customer adoption, traction, retention, revenue, gross margin, burn/runway if supplied, sales efficiency if available, pricing, unit economics, concentration risks, regulatory burden, and dependency on dominant vendors. **Never infer private-company revenue, valuation, margins, or market share from a generic article or funding amount.** Missing private-company data remain unknown.

## 5. Transparent scoring methodology (proposed, not empirically validated)

Return scores only if sufficiently evidenced; otherwise display **Insufficient data** with diagnostic subfactors and evidence gaps. Every factor is rated 0–5 with a citation-backed rationale; compute weighted averages deterministically in code, not in generative prose.

### Competitive Strength Score (0–100)

| Dimension | Weight |
|---|---:|
| Product differentiation and customer value | 20% |
| Adoption/traction and evidence of demand | 20% |
| Unit economics/business-model viability | 15% |
| Defensibility/moats | 20% |
| Distribution and go-to-market | 15% |
| Ability to execute under regulatory/capital constraints | 10% |

### Disruption Potential Score (0–100)

| Dimension | Weight |
|---|---:|
| Underserved/nonconsuming entry segment | 20% |
| Access/affordability/convenience shift | 20% |
| Structural business-model advantage | 20% |
| Plausible upmarket / adjacent-market progression | 15% |
| Incumbent response disincentives | 15% |
| Evidence of expanding adoption / substitution | 10% |

**Formula:** `score = 100 * SUM(weight_i * rating_i / 5)` where weights sum to 1. When factors are unavailable, do **not** silently score them as zero. Define minimum coverage: at least 70% of total factor weight observed **and** at least four independently supported factors; otherwise withhold overall numeric score. For adequate coverage, normalize over observed weights and display coverage prominently, including that the conditional score is not directly comparable to a fully observed company. Flag scores driven by self-reported claims. Confidence (`low`, `medium`, `high`) is separate from score and based on recency, source independence, observed coverage, corroboration, and conflicts; do not present these heuristic scores as investment probabilities.

Enable an explanation panel showing factor, raw rating, weight, factual evidence, source, analyst override, and recalculation. Preserve both original values and any user edits.

## 6. Pairwise incumbent exposure matrix

For each startup–incumbent pair, evaluate:

- Customer/segment overlap; exact business unit or product line exposed.
- Relative price and distribution advantages.
- Switching friction and customer procurement cycle.
- Profit pool cannibalization / incumbent incentive to defend or ignore segment.
- Scale, bundling, subsidization, acquisition, replication, and regulatory response capacity.
- Exposure timing: near term (0–2 years), medium term (3–5 years).

Output a **qualitative** `low / moderate / high / unknown` exposure category with evidence and an explicit counterargument. Avoid fabricated revenue-at-risk figures. If the user supplies a verified revenue base and explicit assumptions, allow a clearly marked **scenario estimate**, not a forecast of fact.

## 7. Side-by-side comparison fields

| Dimension | Startup | Incumbent A | Incumbent B | Data handling |
|---|---|---|---|---|
| Core use case | Evidence | Evidence | Evidence | Same user/job definition |
| Target buyers | Segment | Segment | Segment | Distinguish buyer from user |
| Entry pricing | Verified rate | Verified rate | Verified rate | Currency, unit, billing period, date |
| Product availability | Geography | Geography | Geography | Source/date |
| Capabilities | Features | Features | Features | Comparable scope |
| Revenue/growth | Actual or unknown | Actual or unknown | Actual or unknown | Fiscal period + unit |
| Profitability/margins | Actual or unknown | Actual or unknown | Actual or unknown | Avoid apples/oranges |
| Share/adoption | Actual or unknown | Actual or unknown | Actual or unknown | Denominator and source |
| Moat | Evidence | Evidence | Evidence | Do not score hype |
| Regulatory constraints | Evidence | Evidence | Evidence | Jurisdiction specific |
| Switching costs | Evidence | Evidence | Evidence | Segment specific |

Use `Unknown`, `Not comparable`, and `Estimated` as distinct states. Do not imply private/startup data are disclosed when they are not.

## 8. Sources and data pipeline

Prefer primary, free, accessible sources:

- Company websites: products, pricing, official announcements (self-reported; label as such).
- SEC EDGAR `data.sec.gov`: U.S. public-company filings, XBRL company facts, disclosures; adhere to SEC fair-access policies and required user agent.
- Existing VentureScout feeds, SEC Form D and curated discovery engine: news/funding **leads**, not verified revenue.
- Government/public statistics and regulatory agency pages for industry and market structure.
- Patent records (e.g., USPTO public resources) when useful and legally accessible.
- Public investor presentations, earnings calls, annual reports, and credible sector research when reuse permits.

Build a source registry with `url`, `title`, `publisher`, `published_at`, `retrieved_at`, `evidence_type`, `is_primary`, `is_self_reported`, `confidence`, and field-specific evidence notes. Deduplicate sources and company identifiers, record unit and financial period, and flag contradictory information. Respect robots rules, terms, licenses, and rate limits; no unlicensed scraping, bypass of paywalls, or exposure of API keys in GitHub Pages. Public site should work with prebuilt snapshots and manual entry if no live research endpoint is available.

**Research process:** resolve entities → build a candidate competitor set → validate product and segment overlap → collect sources → normalize data → cross-check claims → compute deterministic factors → draft evidence-backed narrative → show counterevidence and coverage → save/export. Mark researched date and stale fields. Never fabricate URLs, citations, peer metrics, or results.

## 9. Data structures (illustrative contract; adapt to repository schemas)

```json
{
  "analysis_id": "example-analysis-001",
  "schema_version": 1,
  "startup_id": "existing-startup-id-or-local-id",
  "startup_name": "Example Startup",
  "industry": "Example industry",
  "segment": "Example buyer segment",
  "geography": "US",
  "competitors": [
    {"id": "company-a", "name": "Example Incumbent", "comparison_role": "incumbent", "business_unit": "Relevant division"}
  ],
  "scores": {
    "competitive_strength": {"score": null, "coverage": 0, "confidence": "low", "factors": []},
    "disruption_potential": {"score": null, "coverage": 0, "confidence": "low", "factors": []}
  },
  "disruption_type": "insufficient_evidence",
  "incumbent_exposures": [],
  "comparisons": [],
  "scenarios": [],
  "claims": [],
  "sources": [],
  "researched_at": null,
  "user_overrides": []
}
```

Store the links between structured claims, source IDs, extracted values, and generated conclusions. Escape/sanitize all displayed remote text and user input. Provide migration/compatibility checks for existing stored records. Keep private user-entered notes and analyses in client storage and existing backup/restore functionality; publish only properly licensed public research snapshots.

## 10. Visual components

Implement using existing UI utilities and minimal dependencies:

- Two separate scoring gauges with factor-level explanation and evidence coverage.
- Comparator table with source popovers, filters, missing-value distinctions, and accessible mobile card alternatives.
- Positioning scatterplot with documented axes, adjustable parameters, and qualitative indicators when metrics are proxies.
- Five Forces display showing sector-level competitive pressure.
- Incumbent exposure grid with explainable categories, not unsupported numerical precision.
- Scenario controls: competitor price cuts, startup adoption, gross margin assumptions, market growth, regulatory friction. Show model assumptions and sensitivity; never invent empirical probabilities.
- Evidence timeline marking actual source/event dates.
- Export a research report as Markdown and JSON; CSV for comparison tables, compatible with existing export conventions.

Provide a **Compare another competitor** action; allow a saved analysis to be reopened. The tool must remain useful even with no AI key and no network connectivity after static bundles load.

## 11. Scenario modeling

Provide three **user-adjustable hypothetical** scenarios over 3–5 years:

1. **Upside:** attractive segment entry, rapid product improvement, incumbent response delayed.
2. **Base:** measured adoption, strong incumbent defense, constrained distribution.
3. **Downside:** low retention, high acquisition costs, pricing/bundling response, regulatory constraints.

If using a quantitative market-share/revenue model, label it as a simulation. Require users to supply or approve assumptions for reachable market, adoption, price, churn/retention, and starting base. Display the formula, time horizon, constraints, and sensitivity; do not imply forecasts from sparse data are reliable. If inputs are incomplete, show narrative scenarios rather than generating fake numbers.

## 12. AI-generated research (optional enhancement)

If a compatible secure inference service becomes available, support an optional, user-initiated research synthesis layer; **no secret keys in client JavaScript or public build artifacts**. AI should summarize structured sourced facts and competing theses, not generate canonical numbers or citations. Separate direct observations, reasonable inference, speculation, and missing evidence.

Required report headings:

- Executive summary and investment question
- Startup and target market
- Incumbent and substitute identification
- Direct comparison and positioning
- Competitive strengths and weaknesses
- Disruption classification and theory-based rationale
- Incumbent reaction and vulnerability
- Market structure and Five Forces
- Catalysts, kill criteria, diligence questions
- Scenario outcomes and sensitivities
- Conflicting evidence, confidence and data gaps
- Source list with retrieved dates

Every material claim must link to structured evidence or be explicitly labeled hypothesis. Include a bear case that could invalidate the bullish thesis.

## 13. Implementation sequence

### Phase 0 — Repo inspection and scoped design

- Inspect current project structure, routing, styling, data loader, scores, storage, test scripts and build pipeline.
- Document the actual integration points and any mismatches against this specification.
- Identify sources and data that can be reused; do not duplicate the current Scorecard logic unnecessarily.

### Phase 1 — Working offline-capable MVP

- Add a new Competitive Analysis page accessible from Research navigation.
- Startup select/manual entry; manual incumbent selection with editable company records.
- Pairwise comparison table, sourced qualitative evidence, separate scores with transparent factors.
- Import/save/reopen/export via existing local storage and backups.
- Seed with clearly labeled **synthetic fixture data** for tests/demo only; never represent examples as real research.

### Phase 2 — Public data enrichment

- Extend scheduled Python discovery job with company/peer lookup, legal public-source enrichment, source registry, data quality checks, snapshots.
- Maintain budget-free GitHub Actions/GitHub Pages deployment; avoid huge payloads and respect source rate limits.
- Add date/citation/coverage/staleness indicators, graceful failure paths.

### Phase 3 — Advanced comparative research

- Add Five Forces, disruption classification, moat map, exposure matrix and sourced commentary.
- Add model-driven scenario sensitivities and advanced charts.
- Optional AI synthesis only where secure infrastructure exists.

Deliver each phase as manageable reviewable changes, not an unreviewable redesign. Preserve all existing features and financial calculations.

## 14. Tests, governance and acceptance criteria

Required tests:

- Score weights sum to 100%, correctly compute values and respect missing-data thresholds.
- Evidence coverage and confidence can differ from score.
- Entity resolution avoids same-name wrong-company matches and parent vs subsidiary confusion.
- Unavailable facts are not silently replaced by zero or estimated results.
- Pricing and financial metrics respect units, currencies and fiscal periods.
- Score changes immediately reflect transparent user overrides.
- No unsupported narrative claims without links to evidence or hypothesis flags.
- Source conflicts and stale data are visible.
- User data survives reload, and backup/restore remains compatible.
- Exports preserve assumptions, source links, timestamp and score methodology.
- No leakage of private notes or secrets into static data or client bundle.
- Existing app routes, calculations and saved records remain intact.
- Desktop/mobile/responsive UI, keyboard access and readable tables work.
- Existing `npm test`, `npm run check`, `npm run build`, Python tests and CI pass (adjust only based on actual repo commands).

**Definition of done:** A researcher can open an existing startup profile, compare it with at least 3 named incumbents using known or manually entered evidence, see honest scores or an insufficient-data state, inspect every underlying claim and risk, save and export the work, and use the rest of VentureScout unchanged.

## 15. Instructions for the coding agent

**Your role:** Senior full-stack engineer, venture capital research analyst and product designer.

1. Audit this repository first. Do not rewrite the application or assume the current branch is identical to the README.
2. Implement this feature **inside the existing VentureScout website**, not as a standalone website or separate demo.
3. Maintain its existing free, open-source, static-first architecture and UX language.
4. Create a clear PR with a concise architecture note, changed files, documented scoring assumptions, limitations, screenshots or meaningful UI checks, and test results.
5. Research and analysis must be cautious, cited, reproducible and resistant to hallucination.
6. Prefer a small fully functional MVP over partially implemented features or decorative mockups.
7. If an external data provider or AI service is unavailable, keep a manual/offline workflow functional and document the limitation. Do not fake integration success.

## 16. Research references

These sources inform the conceptual model; they do not validate the proposed scoring weights:

- Harvard Business School, Institute for Strategy & Competitiveness — *The Five Forces*: https://www.isc.hbs.edu/strategy/business-strategy/Pages/the-five-forces.aspx
- Christensen Institute — *Disruptive Innovation Theory*: https://www.christenseninstitute.org/theory/disruptive-innovation/
- Christensen Institute — *No, disruption isn't a strategy*: https://www.christenseninstitute.org/blog/no-disruption-isnt-a-strategy/
- SEC — *Developer Resources and EDGAR APIs*: https://www.sec.gov/about/developer-resources
- VentureScout repository and architecture: https://github.com/BagofRamen27/Venture-capital-tracker-

**End of specification.**
