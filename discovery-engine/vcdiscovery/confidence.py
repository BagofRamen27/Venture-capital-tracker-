"""Data-confidence score (0-100): how well-supported is this company record?

This is about the quality of the evidence, NOT about whether the company is a good investment.
Each component is listed in the breakdown so the number can be audited.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .models import Citation, DuplicateCandidate, SecFiling, Startup, utcnow

SOURCE_TYPE_POINTS = {"regulatory": 25, "news": 18, "press_release": 14, "video": 12, "analyst": 12, "open_data": 10, "community": 8}
KEY_FIELDS = ["website", "industry", "description", "hq_city", "founded_year", "funding_stage", "founders"]


def compute_confidence(session: Session, startup: Startup, stale_after_days: int = 180) -> dict:
    parts: list[dict] = []

    def add(component: str, points: float, why: str) -> None:
        parts.append({"component": component, "points": round(points, 1), "explanation": why})

    citations = list(session.scalars(select(Citation).where(Citation.startup_id == startup.id)))
    filings = list(session.scalars(select(SecFiling).where(
        SecFiling.startup_id == startup.id, SecFiling.match_status.in_(["auto_matched", "created", "confirmed"]))))

    # 1. Identity
    if startup.domain:
        add("identity", 15, f"Company website identified ({startup.domain})")
    if startup.sec_cik and filings:
        add("identity", 10, f"Linked to SEC filer CIK {startup.sec_cik}")

    # 2. Best source type
    types = {c.source_type for c in citations if c.source_type}
    if filings:
        types.add("regulatory")
    if types:
        best = max(types, key=lambda t: SOURCE_TYPE_POINTS.get(t, 0))
        add("source_quality", SOURCE_TYPE_POINTS.get(best, 0), f"Strongest source type: {best}")
    else:
        add("source_quality", 0, "No cited sources")

    # 3. Independent corroboration (distinct publishers, not article count)
    publishers = {c.publisher for c in citations if c.publisher and c.source_type != "analyst"}
    if len(publishers) >= 3:
        add("corroboration", 20, f"{len(publishers)} independent publishers")
    elif len(publishers) == 2:
        add("corroboration", 14, "2 independent publishers")
    else:
        add("corroboration", 0, "Single publisher" if publishers else "No independent publisher")

    # 4. Freshness
    dates = [c.published_at or c.retrieved_at for c in citations] + [
        datetime.combine(f.filing_date, time()) for f in filings if f.filing_date
    ]
    dates = [d for d in dates if d]
    stale = False
    if dates:
        age = (utcnow() - max(dates)).days
        if age <= 90:
            add("freshness", 10, f"Latest evidence {age} days old")
        elif age <= stale_after_days:
            add("freshness", 5, f"Latest evidence {age} days old")
        else:
            stale = True
            add("freshness", 0, f"Stale: latest evidence {age} days old")
    else:
        add("freshness", 0, "No dated evidence")

    # 5. Completeness of key profile fields
    filled = [f for f in KEY_FIELDS if getattr(startup, f) not in (None, "")]
    add("completeness", 20 * len(filled) / len(KEY_FIELDS), f"{len(filled)}/{len(KEY_FIELDS)} key fields filled")

    # 6. Penalties
    conflicts = sum(1 for r in startup.rounds if r.conflict)
    if conflicts:
        add("conflicts", -min(30, 15 * conflicts), f"{conflicts} funding round(s) with conflicting figures")
    raised_rounds = [r for r in startup.rounds if r.evidence_status not in ("rumor", "target")]
    if startup.rounds and not raised_rounds:
        add("unconfirmed_funding", -10, "Funding information is only rumoured or a target")
    open_dups = session.scalar(select(func.count(DuplicateCandidate.id)).where(
        DuplicateCandidate.status == "open",
        or_(DuplicateCandidate.startup_a_id == startup.id, DuplicateCandidate.startup_b_id == startup.id)))
    if open_dups:
        add("possible_duplicate", -10, "Possible duplicate record awaiting review")

    total = max(0.0, min(100.0, sum(p["points"] for p in parts)))
    label = "High" if total >= 70 else "Medium" if total >= 45 else "Low"
    startup.confidence_score = round(total, 1)
    startup.confidence_label = label
    startup.confidence_breakdown = {"components": parts, "method": "confidence v1", "computed_at": utcnow().isoformat()}
    if stale:
        startup.add_flag("stale")
    else:
        startup.remove_flag("stale")
    if open_dups == 0:
        startup.remove_flag("possible_duplicate")
    return startup.confidence_breakdown


def recompute_all(session: Session, stale_after_days: int = 180, since_days: int | None = None) -> int:
    query = select(Startup)
    if since_days is not None:
        query = query.where(Startup.last_updated_at >= utcnow() - timedelta(days=since_days))
    n = 0
    for s in session.scalars(query):
        compute_confidence(session, s, stale_after_days)
        n += 1
    return n
