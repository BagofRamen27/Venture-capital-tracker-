"""Produce a snapshot in the exact JSON shape the existing dashboard reads
(`vc-investment-tracker-web/dist/data/demo-data.json`), filled from the database.

Records imported from that file keep their original rows (stored in `Startup.extra`), so
exporting them reproduces the dashboard's data. Newly discovered companies are added with
the same keys, blank where nothing is known. Discovery-specific values sit in extra
`discovery_*` keys, which the current dashboard ignores.
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .config import Settings
from .csv_io import startup_investors
from .models import Citation, FundingRound, InvestmentScore, SecFiling, Startup, utcnow

STARTUP_KEYS = [
    "startup_id", "company_name", "legal_name", "website", "sector", "sub_sector", "hq_city", "hq_state", "founded_year",
    "founded_basis", "founders", "funding_stage", "accelerator", "fundraising_status", "fundraising_detail",
    "verification_confidence", "verification_basis", "business_model", "traction_summary", "traction_source",
    "notable_investors", "primary_source_url", "sec_filing_url", "sec_filing_status", "verification_date",
    "missing_fields", "data_flags", "raw_industry", "raw_founded_year", "raw_funding_stage", "raw_round_status",
    "raw_platform", "current_round_id", "current_round_type", "current_platform", "current_regulation",
    "current_security_type", "current_discount_pct", "current_revenue_share_terms", "current_price_per_share_usd",
    "current_min_target_usd", "current_max_target_usd", "current_capital_raised_usd", "current_capital_raised_status",
    "current_reserved_noncommitted_usd", "current_investor_count", "current_investor_count_note",
    "current_valuation_amount_usd", "current_valuation_type", "current_valuation_terms_note",
    "current_valuation_next_tier_usd", "current_offering_deadline", "current_deadline_alt_date",
    "current_round_close_date", "current_round_status", "current_source_type", "revenue_stage", "latest_fy_revenue_usd",
    "latest_fy_revenue_status", "latest_fy_revenue_source", "current_arr_usd", "current_arr_status", "current_arr_source",
    "revenue_to_date_usd", "revenue_to_date_status", "employees", "employees_status", "long_term_debt_usd",
    "long_term_debt_status", "form_c_balance_sheet_status", "raw_revenue_latest_fy", "prior_capital_company_stated_usd",
    "unverified_claims_count", "open_conflicts_count", "suggested_next_action", "record_version", "last_updated",
    "updated_by", "raw_traction", "financial_notes",
]
ROUND_KEYS = [
    "round_id", "startup_id", "round_label", "round_type", "is_current_round", "current_round_key", "platform",
    "regulation", "security_type", "discount_pct", "revenue_share_terms", "price_per_share_usd", "min_target_usd",
    "max_target_usd", "target_status", "capital_raised_usd", "capital_raised_status", "reserved_noncommitted_usd",
    "investor_count", "investor_count_note", "valuation_amount_usd", "valuation_type", "valuation_terms_note",
    "valuation_next_tier_usd", "offering_deadline", "deadline_source", "deadline_alt_date", "round_close_date",
    "round_status", "source_type", "verification_confidence", "source_url", "sec_filing_url", "raw_security",
    "raw_min_target", "raw_max_target", "raw_capital_raised", "raw_investor_count", "raw_valuation", "raw_deadline", "notes",
]
CLAIM_KEYS = ["claim_id", "startup_id", "claim_category", "field_name", "claimed_value", "source_type", "source_url",
              "verification_status", "confidence", "conflict_note", "verified_on", "next_check", "reviewer", "review_status"]
PIPELINE_KEYS = ["startup_id", "pipeline_stage", "priority", "owner", "suggested_next_action", "next_action",
                 "next_action_date", "dd_form_c_review", "dd_terms_verified", "dd_financials_reviewed",
                 "dd_founder_references", "dd_customer_references", "dd_legal_cap_table", "decision", "decision_date",
                 "memo_status", "memo_link", "last_updated", "updated_by"]
SCORE_KEYS = ["startup_id", "market_score", "market_evidence", "traction_score", "traction_evidence", "team_score",
              "team_evidence", "moat_score", "moat_evidence", "financials_score", "financials_evidence", "analyst",
              "scored_on", "analyst_notes"]

STATUS_TO_STAGE = {
    "Discovered": "Sourced", "Needs Verification": "Screening", "Under Review": "Screening", "Watchlist": "Watchlist",
    "Due Diligence": "Due Diligence", "Rejected": "Passed", "Archived": "Passed",
}
EVIDENCE_TO_TRACKER = {
    "regulatory_filing": "Verified - SEC filing",
    "confirmed": "Verified - corroborated (2+ sources)",
    "company_announced": "Company-stated (unverified)",
    "reported": "Reported - news (unverified)",
    "analyst_entered": "Analyst-entered",
    "target": "Target (not raised)",
    "rumor": "Rumor (unconfirmed)",
}
FIELD_TO_CATEGORY = {
    "funding_round": "Capital raised", "investors": "Investors", "sec_form_d": "Offering terms",
    "valuation_amount": "Valuation", "revenue_amount": "Financials",
}


def _s(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _blank(keys: list[str]) -> dict:
    return {k: "" for k in keys}


def _confidence_word(evidence: str) -> str:
    return {"regulatory_filing": "High", "confirmed": "High", "company_announced": "Medium", "reported": "Medium"}.get(evidence, "Low")


def build_snapshot(session: Session, settings: Settings, include_demo: bool = False) -> dict:
    snapshot = {"settings": settings.load_json(settings.dashboard_settings_file), "startups": [], "rounds": [],
                "claims": [], "pipeline": [], "scores": []}
    query = select(Startup).where(Startup.review_status != "Archived").order_by(Startup.id)
    if not include_demo:
        query = query.where(Startup.is_demo.is_(False))
    for s in session.scalars(query):
        extra = s.extra or {}
        sid = s.external_id or f"VCD-{s.id:04d}"
        score = session.scalar(select(InvestmentScore).where(InvestmentScore.startup_id == s.id, InvestmentScore.is_current))
        filing = session.scalar(select(SecFiling).where(SecFiling.startup_id == s.id).order_by(SecFiling.filing_date.desc()))
        imported = extra.get("tracker_startup")

        row = _blank(STARTUP_KEYS)
        if imported:
            row.update(imported)
        else:
            row.update({
                "company_name": s.name, "legal_name": _s(s.legal_name), "website": _s(s.website), "sector": _s(s.industry),
                "sub_sector": _s(s.sub_industry), "hq_city": _s(s.hq_city), "hq_state": _s(s.hq_state or s.hq_country),
                "founded_year": _s(s.founded_year), "founded_basis": "SEC Form D year of incorporation" if s.founded_year and s.sec_cik else "",
                "founders": _s(s.founders), "funding_stage": _s(s.funding_stage),
                "fundraising_status": "No Active Round Known",
                "verification_confidence": _s(s.confidence_label),
                "verification_basis": "Automated discovery; see claims. Needs analyst verification.",
                "business_model": _s(s.business_model), "traction_summary": _s(s.growth_signals or s.description),
                "notable_investors": "; ".join(startup_investors(s)), "primary_source_url": _s(s.primary_source_url),
                "sec_filing_url": filing.filing_url if filing else "", "sec_filing_status": f"Form {filing.form_type} on EDGAR" if filing else "",
                "verification_date": s.last_updated_at.date().isoformat() if s.last_updated_at else "",
                "missing_fields": ", ".join(f for f in ("website", "industry", "founders", "funding_stage") if not getattr(s, f)) or "none",
                "data_flags": "; ".join(s.flags or []), "record_version": "1",
                "last_updated": s.last_updated_at.date().isoformat() if s.last_updated_at else "", "updated_by": "discovery-engine",
            })
        row["startup_id"] = sid
        row.update({
            "discovery_id": s.id, "discovery_status": s.review_status, "discovery_confidence": s.confidence_score,
            "discovery_confidence_label": s.confidence_label, "discovery_score": score.total_score if score else None,
            "discovery_score_rating": score.rating if score else None, "discovery_flags": s.flags or [],
            "discovery_first_seen": s.first_discovered_at.isoformat() if s.first_discovered_at else None,
            "discovery_is_demo": s.is_demo,
        })
        snapshot["startups"].append(row)

        rounds = extra.get("tracker_rounds") or []
        snapshot["rounds"].extend({**_blank(ROUND_KEYS), **r} for r in rounds)
        new_rounds = [r for r in s.rounds if not (r.extra or {}).get("round_id")]
        has_current = any(r.get("is_current_round") == "Yes" for r in rounds)
        latest = max(new_rounds, key=lambda r: r.announced_date or utcnow().date(), default=None)
        for r in new_rounds:
            snapshot["rounds"].append(_round_row(r, sid, is_current=(not has_current and r is latest)))

        snapshot["claims"].extend({**_blank(CLAIM_KEYS), **c} for c in extra.get("tracker_claims") or [])
        for c in session.scalars(select(Citation).where(Citation.startup_id == s.id, or_(Citation.note.is_(None), ~Citation.note.like("Imported claim %")))):
            snapshot["claims"].append({
                **_blank(CLAIM_KEYS), "claim_id": f"VCDC-{c.id:05d}", "startup_id": sid,
                "claim_category": FIELD_TO_CATEGORY.get(c.field_name, "Company profile"), "field_name": c.field_name,
                "claimed_value": _s(c.value_text), "source_type": _s(c.publisher or c.source_type), "source_url": _s(c.source_url),
                "verification_status": EVIDENCE_TO_TRACKER.get(c.evidence_status, c.evidence_status),
                "confidence": _confidence_word(c.evidence_status), "conflict_note": _s(c.note) if c.is_estimate else "",
                "verified_on": (c.published_at or c.retrieved_at).date().isoformat(), "review_status": "Open",
            })

        pipe = {**_blank(PIPELINE_KEYS), **(extra.get("tracker_pipeline") or {})}
        if not extra.get("tracker_pipeline") or s.review_status != extra.get("imported_review_status"):
            pipe["pipeline_stage"] = STATUS_TO_STAGE.get(s.review_status, "Sourced")
            pipe.setdefault("dd_form_c_review", "Not started")
            for k in ("dd_form_c_review", "dd_terms_verified", "dd_financials_reviewed", "dd_founder_references",
                      "dd_customer_references", "dd_legal_cap_table"):
                pipe[k] = pipe[k] or "Not started"
            pipe["last_updated"] = pipe["last_updated"] or utcnow().date().isoformat()
            pipe["updated_by"] = pipe["updated_by"] or "discovery-engine"
        pipe["startup_id"] = sid
        snapshot["pipeline"].append(pipe)
        snapshot["scores"].append({**_blank(SCORE_KEYS), **(extra.get("tracker_score") or {}), "startup_id": sid})
    snapshot["generated_by"] = {"tool": "vc-discovery-engine", "generated_at": utcnow().isoformat(),
                                "note": "Built from the discovery database. Scores are preliminary research indicators."}
    return snapshot


def _round_row(r: FundingRound, sid: str, is_current: bool) -> dict:
    status = EVIDENCE_TO_TRACKER.get(r.evidence_status, r.evidence_status)
    if r.conflict:
        status = "Conflicting sources"
    raised = r.amount if r.evidence_status not in ("target", "rumor") and r.currency in (None, "USD") else None
    return {
        **_blank(ROUND_KEYS), "round_id": f"VCDR-{r.id:05d}", "startup_id": sid,
        "round_label": " ".join(p for p in (r.round_type, r.amount_text) if p) or "Funding event",
        "round_type": _s(r.round_type) or ("Form D offering" if r.evidence_status == "regulatory_filing" else ""),
        "is_current_round": "Yes" if is_current else "No", "current_round_key": sid if is_current else "",
        "regulation": "Reg D" if r.evidence_status == "regulatory_filing" else "",
        "capital_raised_usd": _s(raised), "capital_raised_status": status,
        "target_status": "Target only (not raised)" if r.evidence_status == "target" else "",
        "round_close_date": r.announced_date.isoformat() if r.announced_date else "",
        "round_status": "Historical", "source_type": ", ".join(r.publishers or []) or r.evidence_status,
        "verification_confidence": _confidence_word(r.evidence_status), "source_url": _s(r.source_url),
        "raw_capital_raised": _s(r.amount_text),
        "notes": "; ".join(p for p in (r.conflict_note, r.notes,
                                       None if r.currency in (None, "USD") else f"Amount in {r.currency}; not converted") if p),
    }
