"""Entity resolution: decide whether a newly seen company is one we already track.

Rules, strongest first:
1. Same SEC CIK                          -> same company.
2. Same company website domain           -> same company (shared hosts like github.com never count).
3. Same normalised name, no conflicting website -> same company.
   Same normalised name but DIFFERENT websites  -> treated as two companies, flagged for review.
4. Similar (not identical) names         -> new record + an open DuplicateCandidate for a human to check.

Records are only merged automatically under rules 1-3. Fuzzy matches are never auto-merged.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from .models import (
    ArticleMention,
    Citation,
    DiscoverySignal,
    DuplicateCandidate,
    FundingRound,
    InvestmentScore,
    ReviewEvent,
    ScoreOverride,
    SecFiling,
    Startup,
    utcnow,
)
from .text import company_domain, name_similarity, normalize_company_name

FUZZY_THRESHOLD = 0.88


@dataclass
class Resolution:
    startup: Startup
    created: bool
    method: str  # cik | domain | exact_name | created | created_name_collision


def find_existing(session: Session, name: str, website: str | None = None, cik: str | None = None) -> tuple[Startup | None, str]:
    if cik:
        found = session.scalar(select(Startup).where(Startup.sec_cik == cik))
        if found:
            return found, "cik"
    domain = company_domain(website)
    if domain:
        found = session.scalar(select(Startup).where(Startup.domain == domain))
        if found:
            return found, "domain"
    norm = normalize_company_name(name)
    if not norm:
        return None, "none"
    candidates = list(session.scalars(select(Startup).where(Startup.normalized_name == norm)))
    for cand in candidates:
        if domain and cand.domain and cand.domain != domain:
            continue  # same name, different website: probably a different company
        return cand, "exact_name"
    if candidates:
        return None, "name_collision"
    return None, "none"


def similar_startups(session: Session, startup: Startup, threshold: float = FUZZY_THRESHOLD) -> list[tuple[Startup, float]]:
    return similar_names(session, startup.normalized_name, exclude_id=startup.id, threshold=threshold)


def similar_names(session: Session, norm: str, exclude_id: int | None = None,
                  threshold: float = FUZZY_THRESHOLD) -> list[tuple[Startup, float]]:
    """Records whose names look alike (not identical). A first-letter prefilter keeps this fast on SQLite."""
    if not norm:
        return []
    query = select(Startup).where(Startup.normalized_name.like(norm[0] + "%"), Startup.normalized_name != norm)
    if exclude_id is not None:
        query = query.where(Startup.id != exclude_id)
    out = []
    for other in session.scalars(query):
        score = name_similarity(norm, other.normalized_name)
        if score >= threshold or _is_prefix_name(norm, other.normalized_name):
            out.append((other, round(score, 3)))
    return out


def _is_prefix_name(a: str, b: str) -> bool:
    """'acme' vs 'acme robotics': the shorter name is the start of the longer one."""
    short_, long_ = sorted((a.split(), b.split()), key=len)
    return len(short_) < len(long_) and long_[: len(short_)] == short_ and len(short_[0]) >= 4


def record_duplicate(session: Session, a: Startup, b: Startup, similarity: float, reason: str) -> DuplicateCandidate | None:
    lo, hi = sorted((a.id, b.id))
    existing = session.scalar(select(DuplicateCandidate).where(
        DuplicateCandidate.startup_a_id == lo, DuplicateCandidate.startup_b_id == hi))
    if existing:
        return existing
    dup = DuplicateCandidate(startup_a_id=lo, startup_b_id=hi, similarity=similarity, reason=reason)
    session.add(dup)
    a.add_flag("possible_duplicate")
    b.add_flag("possible_duplicate")
    return dup


def resolve_or_create(session: Session, name: str, *, website: str | None = None, cik: str | None = None,
                      discovered_via: str | None = None, defaults: dict | None = None) -> Resolution:
    existing, method = find_existing(session, name, website, cik)
    if existing:
        if website and not existing.website and company_domain(website):
            existing.website, existing.domain = website, company_domain(website)
        if cik and not existing.sec_cik:
            existing.sec_cik = cik
        return Resolution(existing, False, method)

    startup = Startup(
        name=name.strip(),
        normalized_name=normalize_company_name(name),
        website=website if company_domain(website) else None,
        domain=company_domain(website),
        sec_cik=cik,
        discovered_via=discovered_via,
        review_status="Needs Verification",
        flags=[],
        **(defaults or {}),
    )
    session.add(startup)
    session.flush()
    session.add(ReviewEvent(startup_id=startup.id, from_status=None, to_status=startup.review_status,
                            note=f"Discovered via {discovered_via or 'unknown source'}", actor="discovery-engine"))
    if method == "name_collision":
        startup.add_flag("name_collision")
        for other in session.scalars(select(Startup).where(
                Startup.normalized_name == startup.normalized_name, Startup.id != startup.id)):
            record_duplicate(session, startup, other, 1.0, "Same name but different website domains")
        return Resolution(startup, True, "created_name_collision")
    for other, score in similar_startups(session, startup):
        record_duplicate(session, startup, other, score, f"Similar names ({score:.0%} match)")
    return Resolution(startup, True, "created")


MERGEABLE_FIELDS = [
    "legal_name", "website", "domain", "industry", "sub_industry", "description", "hq_city", "hq_state", "hq_country",
    "founded_year", "funding_stage", "business_model", "founders", "key_people", "primary_source_url", "sec_cik",
    "external_id",
]


def merge_startups(session: Session, keep: Startup, remove: Startup, actor: str = "analyst") -> Startup:
    """Move everything from `remove` into `keep`, then delete `remove`. Only call after a human confirms."""
    if keep.id == remove.id:
        return keep
    for field in MERGEABLE_FIELDS:
        if getattr(keep, field) in (None, "") and getattr(remove, field) not in (None, ""):
            value = getattr(remove, field)
            if field in ("external_id", "sec_cik", "domain"):
                setattr(remove, field, None)
                session.flush()
            setattr(keep, field, value)
    for model in (FundingRound, DiscoverySignal, Citation, ReviewEvent, InvestmentScore):
        session.execute(update(model).where(model.startup_id == remove.id).values(startup_id=keep.id))
    session.execute(update(SecFiling).where(SecFiling.startup_id == remove.id).values(startup_id=keep.id))
    session.execute(update(SecFiling).where(SecFiling.suggested_startup_id == remove.id).values(suggested_startup_id=keep.id))
    # Mentions and overrides have uniqueness rules: move only those that do not clash.
    keep_articles = set(session.scalars(select(ArticleMention.article_id).where(ArticleMention.startup_id == keep.id)))
    for m in list(session.scalars(select(ArticleMention).where(ArticleMention.startup_id == remove.id))):
        if m.article_id in keep_articles:
            session.delete(m)
        else:
            m.startup_id = keep.id
    keep_factors = set(session.scalars(select(ScoreOverride.factor).where(ScoreOverride.startup_id == keep.id)))
    for o in list(session.scalars(select(ScoreOverride).where(ScoreOverride.startup_id == remove.id))):
        if o.factor in keep_factors:
            session.delete(o)
        else:
            o.startup_id = keep.id
    for dup in session.scalars(select(DuplicateCandidate).where(or_(
            DuplicateCandidate.startup_a_id == remove.id, DuplicateCandidate.startup_b_id == remove.id))):
        session.delete(dup)
    session.add(ReviewEvent(startup_id=keep.id, from_status=keep.review_status, to_status=keep.review_status,
                            note=f"Merged duplicate record #{remove.id} ({remove.name})", actor=actor))
    session.flush()
    session.expire_all()
    remove_obj = session.get(Startup, remove.id)
    if remove_obj is not None:
        session.delete(remove_obj)
    session.flush()
    keep = session.get(Startup, keep.id)
    still_open = session.scalar(select(DuplicateCandidate).where(
        DuplicateCandidate.status == "open",
        or_(DuplicateCandidate.startup_a_id == keep.id, DuplicateCandidate.startup_b_id == keep.id)))
    if not still_open:
        keep.remove_flag("possible_duplicate")
    keep.last_updated_at = utcnow()
    return keep
