"""Convert database rows into plain JSON for the dashboard."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..csv_io import startup_investors
from ..models import (
    EVIDENCE_STATUSES,
    ArticleMention,
    Citation,
    DiscoverySignal,
    DuplicateCandidate,
    FundingRound,
    InvestmentScore,
    JobRun,
    NewsArticle,
    ReviewEvent,
    SecFiling,
    Startup,
)


def iso(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def money(amount, currency, basis=None, status=None):
    if amount is None:
        return {"amount": None, "currency": None, "display": "Not disclosed", "basis": basis, "evidence_status": status}
    sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency or "", f"{currency or ''} ")
    display = f"{sym}{amount / 1e9:,.2f}B" if amount >= 1e9 else f"{sym}{amount / 1e6:,.1f}M" if amount >= 1e6 else f"{sym}{amount:,.0f}"
    return {"amount": amount, "currency": currency, "display": display, "basis": basis, "evidence_status": status}


def score_summary(score: InvestmentScore | None) -> dict | None:
    if not score:
        return None
    return {"total": score.total_score, "rating": score.rating, "coverage": score.coverage,
            "computed_at": iso(score.computed_at), "model_version": score.model_version}


def startup_summary(s: Startup, score: InvestmentScore | None = None) -> dict:
    return {
        "id": s.id, "external_id": s.external_id, "name": s.name, "website": s.website, "industry": s.industry,
        "description": s.description,
        "headquarters": ", ".join(p for p in (s.hq_city, s.hq_state, s.hq_country) if p) or None,
        "founded_year": s.founded_year, "funding_stage": s.funding_stage,
        "total_funding": money(s.total_funding_amount, s.total_funding_currency, s.total_funding_basis),
        "latest_funding": {**money(s.latest_funding_amount, s.latest_funding_currency, status=s.latest_funding_status),
                           "date": iso(s.latest_funding_date)},
        "review_status": s.review_status,
        "confidence": {"score": s.confidence_score, "label": s.confidence_label},
        "investment_score": score_summary(score),
        "flags": s.flags or [], "is_demo": s.is_demo, "discovered_via": s.discovered_via,
        "first_discovered_at": iso(s.first_discovered_at), "last_updated_at": iso(s.last_updated_at),
        "latest_news": {"title": s.latest_news_title, "url": s.latest_news_url, "date": iso(s.latest_news_date)}
        if s.latest_news_title else None,
    }


def round_dict(r: FundingRound) -> dict:
    return {
        "id": r.id, "startup_id": r.startup_id, "round_type": r.round_type,
        "amount_display": money(r.amount, r.currency)["display"],
        "amount": r.amount, "currency": r.currency, "amount_text": r.amount_text, "announced_date": iso(r.announced_date),
        "evidence_status": r.evidence_status, "evidence_meaning": EVIDENCE_STATUSES.get(r.evidence_status),
        "publishers": r.publishers or [], "investors": [
            {"name": ri.investor.name, "is_lead": ri.is_lead, "source_url": ri.source_url} for ri in r.investors],
        "conflict": r.conflict, "conflict_note": r.conflict_note, "notes": r.notes, "source_url": r.source_url,
        "announced_date_basis": (r.extra or {}).get("announced_date_basis"),
        "funding_resolution": (r.extra or {}).get("funding_resolution"),
        "funding_observations": (r.extra or {}).get("funding_observations", []),
        "sec_filing_id": r.sec_filing_id,
    }


def filing_dict(f: SecFiling) -> dict:
    return {
        "id": f.id, "accession_number": f.accession_number, "cik": f.cik, "form_type": f.form_type,
        "is_amendment": f.is_amendment, "issuer_name": f.issuer_name, "filing_date": iso(f.filing_date),
        "industry_group": f.industry_group, "entity_type": f.entity_type, "year_of_incorporation": f.year_of_incorporation,
        "revenue_range": f.revenue_range, "federal_exemptions": f.federal_exemptions,
        "date_of_first_sale": iso(f.date_of_first_sale), "total_offering_amount": f.total_offering_amount,
        "offering_amount_indefinite": f.offering_amount_indefinite, "total_amount_sold": f.total_amount_sold,
        "total_remaining": f.total_remaining, "investor_count": f.investor_count,
        "has_non_accredited_investors": f.has_non_accredited_investors, "securities_types": f.securities_types,
        "related_persons": f.related_persons, "location": ", ".join(p for p in (f.city, f.state_or_country) if p),
        "filing_url": f.filing_url, "document_url": f.document_url, "retrieved_at": iso(f.retrieved_at),
        "is_startup_candidate": f.is_startup_candidate, "candidate_reason": f.candidate_reason,
        "startup_id": f.startup_id, "suggested_startup_id": f.suggested_startup_id, "match_status": f.match_status,
        "match_score": f.match_score, "match_note": f.match_note, "review_flags": f.review_flags or [],
        "disclaimer": "A Form D is a notice of an exempt securities offering. It does not establish a completed venture "
                      "round, a valuation, or institutional investor participation.",
    }


def article_dict(a: NewsArticle) -> dict:
    return {
        "id": a.id, "title": a.title, "url": a.url, "publisher": a.publisher, "source_key": a.source_key,
        "source_type": a.source_type, "summary": a.summary, "published_at": iso(a.published_at),
        "retrieved_at": iso(a.retrieved_at), "duplicate_of_id": a.duplicate_of_id, "event_types": a.event_types or [],
        "sentiment": a.sentiment, "sentiment_score": a.sentiment_score,
        "classification_evidence": a.classification_evidence, "community_metrics": a.community_metrics,
        "note": "Tone describes the wording of the story, not the quality of the investment.",
    }


def signal_dict(sig: DiscoverySignal) -> dict:
    return {"id": sig.id, "type": sig.signal_type, "source_key": sig.source_key, "detail": sig.detail,
            "source_url": sig.source_url, "observed_at": iso(sig.observed_at), "detected_at": iso(sig.detected_at)}


def citation_dict(c: Citation) -> dict:
    return {"id": c.id, "field": c.field_name, "value": c.value_text, "evidence_status": c.evidence_status,
            "is_estimate": c.is_estimate, "source_type": c.source_type, "publisher": c.publisher,
            "source_url": c.source_url, "published_at": iso(c.published_at), "retrieved_at": iso(c.retrieved_at),
            "note": c.note}


def full_score(score: InvestmentScore | None) -> dict | None:
    if not score:
        return None
    return {**score_summary(score), "weights": score.weights, "factors": score.factors, "missing": score.missing,
            "thesis": score.thesis, "risks": score.risks,
            "disclaimer": "Preliminary research indicator based only on public evidence. Not an investment recommendation."}


def startup_detail(session: Session, s: Startup) -> dict:
    score = session.scalar(select(InvestmentScore).where(InvestmentScore.startup_id == s.id, InvestmentScore.is_current))
    articles = session.scalars(
        select(NewsArticle).join(ArticleMention, ArticleMention.article_id == NewsArticle.id)
        .where(ArticleMention.startup_id == s.id).order_by(NewsArticle.published_at.desc())).all()
    filings = session.scalars(select(SecFiling).where(or_(SecFiling.startup_id == s.id, SecFiling.suggested_startup_id == s.id))
                              .order_by(SecFiling.filing_date.desc())).all()
    dups = session.scalars(select(DuplicateCandidate).where(or_(
        DuplicateCandidate.startup_a_id == s.id, DuplicateCandidate.startup_b_id == s.id))).all()
    return {
        **startup_summary(s, score),
        "legal_name": s.legal_name, "sub_industry": s.sub_industry, "hq_city": s.hq_city, "hq_state": s.hq_state,
        "hq_country": s.hq_country, "business_model": s.business_model, "founders": s.founders,
        "key_people": s.key_people, "investors": startup_investors(s),
        "valuation": money(s.valuation_amount, s.valuation_currency, s.valuation_basis),
        "revenue": money(s.revenue_amount, "USD" if s.revenue_amount else None, s.revenue_basis),
        "growth_signals": s.growth_signals, "primary_source_url": s.primary_source_url, "sec_cik": s.sec_cik,
        "last_verified_at": iso(s.last_verified_at),
        "confidence_breakdown": s.confidence_breakdown,
        "funding_rounds": [round_dict(r) for r in sorted(s.rounds, key=lambda r: r.announced_date or date.min, reverse=True)],
        "sec_filings": [filing_dict(f) for f in filings],
        "news": [article_dict(a) for a in articles],
        "signals": [signal_dict(x) for x in sorted(s.signals, key=lambda x: x.detected_at, reverse=True)],
        "citations": [citation_dict(c) for c in sorted(s.citations, key=lambda c: c.retrieved_at, reverse=True)],
        "score": full_score(score),
        "review_history": [{"from": e.from_status, "to": e.to_status, "note": e.note, "actor": e.actor,
                            "at": iso(e.created_at)} for e in session.scalars(
            select(ReviewEvent).where(ReviewEvent.startup_id == s.id).order_by(ReviewEvent.created_at))],
        "possible_duplicates": [{"id": d.id, "other_startup_id": d.startup_b_id if d.startup_a_id == s.id else d.startup_a_id,
                                 "similarity": d.similarity, "reason": d.reason, "status": d.status} for d in dups],
    }


def job_dict(j: JobRun) -> dict:
    return {"id": j.id, "job": j.job_name, "source_key": j.source_key, "trigger": j.trigger, "status": j.status,
            "started_at": iso(j.started_at), "finished_at": iso(j.finished_at), "items_fetched": j.items_fetched,
            "items_new": j.items_new, "items_duplicate": j.items_duplicate, "startups_created": j.startups_created,
            "error": j.error_message}
