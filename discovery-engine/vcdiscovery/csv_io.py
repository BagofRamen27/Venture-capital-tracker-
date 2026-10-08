"""CSV export/import and import of the original 20-startup research file."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .confidence import compute_confidence
from .funding import refresh_funding_summary
from .models import (
    PIPELINE_STATUSES,
    Citation,
    FundingRound,
    InvestmentScore,
    ReviewEvent,
    SecFiling,
    Startup,
    utcnow,
)
from .text import company_domain, normalize_company_name, parse_amount

STARTUP_CSV_FIELDS = [
    "id", "external_id", "name", "legal_name", "website", "industry", "sub_industry", "description", "hq_city",
    "hq_state", "hq_country", "founded_year", "funding_stage", "business_model", "founders", "key_people",
    "total_funding_amount", "total_funding_currency", "total_funding_basis", "latest_funding_amount",
    "latest_funding_currency", "latest_funding_date", "latest_funding_status", "valuation_amount", "valuation_currency",
    "valuation_basis", "revenue_amount", "revenue_basis", "investors", "growth_signals", "latest_news_title",
    "latest_news_url", "primary_source_url", "source_url", "sec_cik", "review_status", "confidence_score",
    "confidence_label", "investment_score", "score_rating", "score_coverage", "flags", "is_demo",
    "first_discovered_at", "last_updated_at",
]
ROUND_CSV_FIELDS = ["id", "startup_id", "startup_name", "round_type", "amount", "currency", "amount_text",
                    "announced_date", "evidence_status", "investors", "lead_investors", "publishers", "conflict",
                    "conflict_note", "source_url"]
FILING_CSV_FIELDS = ["accession_number", "cik", "form_type", "issuer_name", "filing_date", "industry_group",
                     "total_offering_amount", "offering_amount_indefinite", "total_amount_sold", "total_remaining",
                     "investor_count", "city", "state_or_country", "is_startup_candidate", "candidate_reason",
                     "match_status", "startup_id", "filing_url"]

IMPORT_ALIASES = {
    "company_name": "name", "company": "name", "startup": "name", "sector": "industry", "startup_id": "external_id",
    "sub_sector": "sub_industry", "notable_investors": "investors", "traction_summary": "growth_signals",
    "pipeline_stage": "review_status", "status": "review_status", "url": "website", "hq": "hq_city",
}
TEXT_FIELDS = ["legal_name", "industry", "sub_industry", "description", "hq_city", "hq_state", "hq_country",
               "funding_stage", "business_model", "founders", "key_people", "growth_signals", "primary_source_url"]
TRACKER_STAGE_TO_STATUS = {
    "Sourced": "Discovered", "Screening": "Under Review", "Due Diligence": "Due Diligence", "IC Review": "Due Diligence",
    "Committed": "Due Diligence", "Passed": "Rejected", "Watchlist": "Watchlist",
}


def _fmt(value):
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return "; ".join(map(str, value)) if isinstance(value, list) else json.dumps(value)
    return value


def _write(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _fmt(row.get(k)) for k in fields})
    return buf.getvalue()


def startup_investors(s: Startup) -> list[str]:
    names = []
    for r in s.rounds:
        if r.evidence_status in ("rumor", "target"):
            continue
        for ri in r.investors:
            if ri.investor.name not in names:
                names.append(ri.investor.name)
    return names


def export_startups_csv(session: Session, include_demo: bool = True) -> str:
    query = select(Startup).order_by(Startup.id)
    if not include_demo:
        query = query.where(Startup.is_demo.is_(False))
    rows = []
    for s in session.scalars(query):
        score = session.scalar(select(InvestmentScore).where(InvestmentScore.startup_id == s.id, InvestmentScore.is_current))
        row = {f: getattr(s, f, None) for f in STARTUP_CSV_FIELDS if hasattr(s, f)}
        row.update(investors=startup_investors(s), source_url=s.primary_source_url,
                   investment_score=score.total_score if score else None, score_rating=score.rating if score else None,
                   score_coverage=score.coverage if score else None)
        rows.append(row)
    return _write(rows, STARTUP_CSV_FIELDS)


def export_rounds_csv(session: Session) -> str:
    rows = []
    for r in session.scalars(select(FundingRound).order_by(FundingRound.startup_id, FundingRound.announced_date)):
        rows.append({
            **{f: getattr(r, f, None) for f in ROUND_CSV_FIELDS if hasattr(r, f)},
            "startup_name": r.startup.name,
            "investors": [ri.investor.name for ri in r.investors],
            "lead_investors": [ri.investor.name for ri in r.investors if ri.is_lead],
        })
    return _write(rows, ROUND_CSV_FIELDS)


def export_filings_csv(session: Session) -> str:
    rows = [{f: getattr(f_, f) for f in FILING_CSV_FIELDS} for f_ in session.scalars(select(SecFiling).order_by(SecFiling.filing_date.desc()))]
    return _write(rows, FILING_CSV_FIELDS)


def _find_for_import(session: Session, row: dict) -> Startup | None:
    if row.get("id", "").isdigit():
        found = session.get(Startup, int(row["id"]))
        if found:
            return found
    if row.get("external_id"):
        found = session.scalar(select(Startup).where(Startup.external_id == row["external_id"]))
        if found:
            return found
    domain = company_domain(row.get("website"))
    if domain:
        found = session.scalar(select(Startup).where(Startup.domain == domain))
        if found:
            return found
    norm = normalize_company_name(row.get("name"))
    matches = list(session.scalars(select(Startup).where(Startup.normalized_name == norm))) if norm else []
    return matches[0] if len(matches) == 1 else None


def import_startups_csv(session: Session, content: str, mark_demo: bool = False, actor: str = "csv import") -> dict:
    """Create or update companies from CSV. Only `name` (or `company_name`) is required.
    Financial figures are stored with the CSV's `source_url` (if any) as an analyst-entered citation."""
    reader = csv.DictReader(io.StringIO(content.lstrip("﻿")))
    created = updated = 0
    errors: list[str] = []
    for line_no, raw in enumerate(reader, start=2):
        row = {}
        for key, value in raw.items():
            if key is None:
                continue
            k = key.strip().lower().replace(" ", "_")
            row[IMPORT_ALIASES.get(k, k)] = (value or "").strip()
        if not row.get("name"):
            errors.append(f"Line {line_no}: missing company name")
            continue
        startup = _find_for_import(session, row)
        is_new = startup is None
        if is_new:
            startup = Startup(name=row["name"], normalized_name=normalize_company_name(row["name"]),
                              discovered_via="csv_import", flags=[], review_status="Discovered")
            session.add(startup)
        if row.get("external_id") and not startup.external_id:
            startup.external_id = row["external_id"]
        if row.get("website"):
            startup.website, startup.domain = row["website"], company_domain(row["website"])
        for field in TEXT_FIELDS:
            if row.get(field):
                setattr(startup, field, row[field])
        if row.get("founded_year", "").isdigit():
            startup.founded_year = int(row["founded_year"])
        if row.get("review_status") in PIPELINE_STATUSES:
            startup.review_status = row["review_status"]
        elif row.get("review_status") in TRACKER_STAGE_TO_STATUS:
            startup.review_status = TRACKER_STAGE_TO_STATUS[row["review_status"]]
        if row.get("is_demo", "").lower() in ("true", "1", "yes") or mark_demo:
            startup.is_demo = True
        session.flush()
        source_url = row.get("source_url") or row.get("primary_source_url") or None
        for field, basis_field in (("valuation_amount", "valuation_basis"), ("revenue_amount", "revenue_basis")):
            amount = parse_amount(row.get(field))
            if amount is not None:
                setattr(startup, field, amount)
                setattr(startup, basis_field, row.get(basis_field) or f"Imported by {actor}; source: {source_url or 'not provided'}")
                _cite(session, startup, field, str(amount), source_url, actor)
        if row.get("investors"):
            _cite(session, startup, "investors", row["investors"], source_url, actor)
        if is_new:
            session.add(ReviewEvent(startup_id=startup.id, to_status=startup.review_status, actor=actor, note="Imported from CSV"))
            created += 1
        else:
            updated += 1
        compute_confidence(session, startup)
    return {"created": created, "updated": updated, "errors": errors}


def _cite(session: Session, startup: Startup, field: str, value: str, url: str | None, actor: str, key: str | None = None) -> None:
    digest = hashlib.sha1(f"{value}|{url}".encode()).hexdigest()[:16]
    dedupe = f"{startup.id}:{field}:{key or 'import:' + digest}"
    if session.scalar(select(Citation).where(Citation.dedupe_key == dedupe)):
        return
    session.add(Citation(startup_id=startup.id, field_name=field, value_text=value, evidence_status="analyst_entered",
                         source_type="analyst", publisher=None, source_url=url, note=f"Imported by {actor}",
                         dedupe_key=dedupe))


def _tracker_evidence(status: str | None) -> tuple[str, bool]:
    status = status or ""
    if status.startswith("Verified"):
        return ("regulatory_filing" if any(k in status for k in ("SEC", "Form C", "filing")) else "confirmed"), False
    if status == "Platform-reported":
        return "reported", False
    if status.startswith("Company-stated"):
        return "company_announced", False
    if status == "Conflicting sources":
        return "reported", True
    return "analyst_entered", False


def import_tracker_snapshot(session: Session, path: str | Path) -> dict:
    """Import the original research file (`vc-investment-tracker-web/examples/original-research.json`).
    Original rows are kept in `extra` so nothing from the source file is lost. Safe to run more than once."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pipeline = {p["startup_id"]: p for p in data.get("pipeline", [])}
    scores = {p["startup_id"]: p for p in data.get("scores", [])}
    created = updated = 0
    for row in data.get("startups", []):
        ext_id = row["startup_id"]
        startup = session.scalar(select(Startup).where(Startup.external_id == ext_id))
        is_new = startup is None
        if is_new:
            startup = Startup(external_id=ext_id, name=row["company_name"], normalized_name=normalize_company_name(row["company_name"]),
                              discovered_via="tracker_import", flags=[])
            session.add(startup)
        stage = pipeline.get(ext_id, {}).get("pipeline_stage", "Sourced")
        status = TRACKER_STAGE_TO_STATUS.get(stage, "Discovered")
        rounds_raw = [r for r in data.get("rounds", []) if r["startup_id"] == ext_id]
        claims_raw = [c for c in data.get("claims", []) if c["startup_id"] == ext_id]
        startup.legal_name = row.get("legal_name") or None
        startup.website, startup.domain = row.get("website") or None, company_domain(row.get("website"))
        startup.industry = row.get("sector") or None
        startup.sub_industry = row.get("sub_sector") or None
        startup.hq_city, startup.hq_state = row.get("hq_city") or None, row.get("hq_state") or None
        year = str(row.get("founded_year") or "")
        startup.founded_year = int(year) if year.isdigit() else None
        startup.founders = row.get("founders") or None
        startup.funding_stage = row.get("funding_stage") or None
        startup.business_model = row.get("business_model") or None
        startup.growth_signals = row.get("traction_summary") or None
        startup.primary_source_url = row.get("primary_source_url") or None
        if is_new:
            startup.review_status = status
        startup.extra = {"tracker_startup": row, "tracker_pipeline": pipeline.get(ext_id), "tracker_score": scores.get(ext_id),
                         "tracker_rounds": rounds_raw, "tracker_claims": claims_raw, "imported_review_status": status}
        if "sec.gov" in (row.get("sec_filing_url") or ""):
            parts = row["sec_filing_url"].split("/edgar/data/")
            if len(parts) == 2:
                startup.sec_cik = parts[1].split("/")[0]
        val = parse_amount(row.get("current_valuation_amount_usd"))
        if val is not None:
            startup.valuation_amount, startup.valuation_currency = val, "USD"
            startup.valuation_basis = f"{row.get('current_valuation_type') or 'Valuation'} (imported tracker; {row.get('current_source_type') or 'see source'})"
        rev = parse_amount(row.get("latest_fy_revenue_usd"))
        if rev is not None:
            startup.revenue_amount = rev
            startup.revenue_basis = f"Latest fiscal-year revenue, {row.get('latest_fy_revenue_status') or 'status not stated'} (imported tracker)"
        session.flush()
        known_rounds = {(r.extra or {}).get("round_id") for r in startup.rounds}
        for r in rounds_raw:
            if r["round_id"] in known_rounds:
                continue
            evidence, conflict = _tracker_evidence(r.get("capital_raised_status") or r.get("target_status"))
            amount = parse_amount(r.get("capital_raised_usd"))
            startup.rounds.append(FundingRound(
                round_type=r.get("round_type") or None, amount=amount, currency="USD" if amount is not None else None,
                amount_text=r.get("raw_capital_raised") or None,
                announced_date=_date(r.get("round_close_date")) or _date(row.get("verification_date")),
                evidence_status=evidence, source_url=r.get("source_url") or None, conflict=conflict,
                conflict_note="Imported tracker marks this figure as conflicting across sources" if conflict else None,
                publishers=[r.get("platform")] if r.get("platform") else [], notes=r.get("notes") or None, extra=r,
            ))
        for c in claims_raw:
            evidence, _ = _tracker_evidence(c.get("verification_status"))
            dedupe = f"{startup.id}:{c.get('field_name')}:{c['claim_id']}"
            if session.scalar(select(Citation).where(Citation.dedupe_key == dedupe)):
                continue
            session.add(Citation(
                startup_id=startup.id, field_name=c.get("field_name") or "claim", value_text=c.get("claimed_value"),
                evidence_status=evidence, source_type="regulatory" if evidence == "regulatory_filing" else "analyst",
                publisher=c.get("source_type"), source_url=c.get("source_url") or None,
                published_at=_dt(c.get("verified_on")), note=f"Imported claim {c['claim_id']}: {c.get('verification_status')}",
                dedupe_key=dedupe,
            ))
        if is_new:
            session.add(ReviewEvent(startup_id=startup.id, to_status=startup.review_status, actor="tracker import",
                                    note=f"Imported from dashboard snapshot (stage: {stage})"))
            created += 1
        else:
            updated += 1
        session.flush()
        refresh_funding_summary(startup)
        startup.funding_stage = row.get("funding_stage") or startup.funding_stage
        compute_confidence(session, startup)
        startup.last_verified_at = _dt(row.get("verification_date"))
    return {"created": created, "updated": updated, "imported_at": utcnow().isoformat()}


def _date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _dt(value) -> datetime | None:
    d = _date(value)
    return datetime.combine(d, datetime.min.time()) if d else None
