"""Discovery pipeline: fetch from each source, store raw evidence, extract companies,
deduplicate, and refresh confidence scores. One failing source never stops the others."""
from __future__ import annotations

import re
import traceback
from datetime import date, datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .classify import classify_text
from .confidence import compute_confidence
from .config import Settings
from .db import session_scope
from .extraction import extract_funding, extract_hn
from .funding import record_round, refresh_funding_summary
from .http import PoliteClient
from .models import (
    ArticleMention,
    Citation,
    DiscoverySignal,
    FundingRound,
    JobLock,
    JobRun,
    NewsArticle,
    SecFiling,
    ReviewEvent,
    Startup,
    utcnow,
)
from .resolution import record_duplicate, resolve_or_create, similar_names, similar_startups
from .sources import build_sources
from .sources.base import FormDItem, NewsItem
from .sources.reddit import RedditSource
from .sources.sec_formd import INDUSTRY_LABELS, SecFormDSource, assess_candidate, review_flags
from .text import canonical_url, company_domain, display_name, normalize_company_name, title_fingerprint

COUNTRY_HINTS = {
    "us", "u.s.", "uk", "u.k.", "usa", "germany", "german", "france", "french", "india", "indian", "israel", "israeli",
    "canada", "canadian", "spain", "spanish", "italy", "italian", "sweden", "swedish", "netherlands", "dutch", "denmark",
    "danish", "finland", "finnish", "norway", "norwegian", "switzerland", "swiss", "ireland", "irish", "estonia",
    "poland", "polish", "portugal", "brazil", "brazilian", "mexico", "singapore", "japan", "japanese", "australia",
    "australian", "nigeria", "nigerian", "kenya", "egypt", "uae", "saudi", "korea", "korean", "china", "chinese",
    "europe", "european", "austria", "belgium", "greece", "lithuania", "latvia", "czech", "romania", "turkey",
}
SYNDICATION_WINDOW = timedelta(days=3)


# --------------------------------------------------------------------------- locks / logs

def acquire_lock(session: Session, name: str, minutes: int) -> bool:
    now = utcnow()
    lock = session.get(JobLock, name)
    if lock and lock.expires_at > now:
        return False
    if lock:
        lock.acquired_at, lock.expires_at = now, now + timedelta(minutes=minutes)
    else:
        session.add(JobLock(name=name, acquired_at=now, expires_at=now + timedelta(minutes=minutes)))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return False
    return True


def release_lock(session: Session, name: str) -> None:
    lock = session.get(JobLock, name)
    if lock:
        session.delete(lock)
        session.commit()


# --------------------------------------------------------------------------- helpers

def add_citation(session: Session, startup: Startup, field: str, value: str | None, status: str, *, key: str,
                  source_type: str | None, publisher: str | None, url: str | None, article: NewsArticle | None = None,
                  filing: SecFiling | None = None, published_at: datetime | None = None, is_estimate: bool = False,
                  note: str | None = None) -> None:
    dedupe = f"{startup.id}:{field}:{key}"
    if session.scalar(select(exists().where(Citation.dedupe_key == dedupe))):
        return
    session.add(Citation(
        startup_id=startup.id, field_name=field, value_text=value, evidence_status=status, is_estimate=is_estimate,
        source_type=source_type, publisher=publisher, source_url=url, article_id=article.id if article else None,
        sec_filing_id=filing.id if filing else None, published_at=published_at, note=note, dedupe_key=dedupe,
    ))


def _add_signal(session: Session, startup: Startup, signal_type: str, key: str, *, source_key: str, detail: str,
                url: str | None, observed_at: datetime | None, article: NewsArticle | None = None,
                filing: SecFiling | None = None) -> bool:
    if session.scalar(select(exists().where(DiscoverySignal.dedupe_key == key))):
        return False
    session.add(DiscoverySignal(
        startup_id=startup.id, signal_type=signal_type, source_key=source_key, detail=detail, source_url=url,
        observed_at=observed_at, article_id=article.id if article else None, sec_filing_id=filing.id if filing else None,
        dedupe_key=key,
    ))
    return True


def _mention(session: Session, article: NewsArticle, startup: Startup, method: str) -> None:
    if not session.scalar(select(exists().where(
            ArticleMention.article_id == article.id, ArticleMention.startup_id == startup.id))):
        session.add(ArticleMention(article_id=article.id, startup_id=startup.id, match_method=method))
    when = article.published_at or article.retrieved_at
    if startup.latest_news_date is None or (when and when > startup.latest_news_date):
        startup.latest_news_title, startup.latest_news_url, startup.latest_news_date = article.title, article.url, when


def _location_defaults(hint: str | None) -> dict:
    if not hint:
        return {}
    return {"hq_country": hint} if hint.lower() in COUNTRY_HINTS else {"hq_city": hint}


def _event_signals(session: Session, startup: Startup, article: NewsArticle, source_key: str) -> None:
    for event in article.event_types or []:
        if event == "funding":
            continue  # funding signals are recorded once per round, not per article
        _add_signal(session, startup, event, f"news:{startup.id}:{event}:{article.id}", source_key=source_key,
                    detail=article.title, url=article.url, observed_at=article.published_at, article=article)


# --------------------------------------------------------------------------- news ingestion

class NameMatcher:
    """Find already-tracked companies mentioned in a headline (exact, case-sensitive, whole words)."""

    COMMON = {"apple", "amazon", "google", "meta", "open", "notion", "linear", "signal", "square", "stripe"}

    def __init__(self, session: Session):
        self.entries = []
        for sid, name in session.execute(select(Startup.id, Startup.name)):
            if len(name) >= 4 and name.lower() not in self.COMMON:
                self.entries.append((sid, name, re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")))

    def add(self, startup: Startup) -> None:
        if len(startup.name) >= 4:
            self.entries.append((startup.id, startup.name, re.compile(rf"(?<![\w-]){re.escape(startup.name)}(?![\w-])")))

    def find(self, title: str) -> list[int]:
        return [sid for sid, name, rx in self.entries if name in title and rx.search(title)]


def ingest_news_item(session: Session, item: NewsItem, settings: Settings, matcher: NameMatcher) -> dict:
    stats = {"new": 0, "duplicate": 0, "startups_created": 0}
    url = canonical_url(item.url)
    if not url or session.scalar(select(exists().where(NewsArticle.url == url))):
        stats["duplicate"] = 1
        return stats
    fp = title_fingerprint(item.title)
    when = item.published_at or utcnow()
    syndicated = session.scalar(select(NewsArticle).where(
        NewsArticle.title_fingerprint == fp, NewsArticle.duplicate_of_id.is_(None),
        NewsArticle.published_at.between(when - SYNDICATION_WINDOW, when + SYNDICATION_WINDOW)))
    cls = classify_text(item.title, item.summary)
    article = NewsArticle(
        source_key=item.source_key, source_type=item.source_type, publisher=item.publisher, url=url, title=item.title,
        summary=item.summary, published_at=item.published_at, title_fingerprint=fp,
        duplicate_of_id=syndicated.id if syndicated else None, event_types=cls["event_types"],
        sentiment=cls["sentiment"], sentiment_score=cls["sentiment_score"], classification_evidence=cls["evidence"],
        community_metrics=item.community_metrics,
    )
    session.add(article)
    session.flush()
    stats["new"] = 1
    if syndicated:
        # Same story republished: link it to the same companies but do not count it as new evidence.
        for m in syndicated.mentions:
            _mention(session, article, m.startup, "syndicated_copy")
        stats["duplicate"] = 1
        return stats

    touched: set[int] = set()
    if item.source_type == "community":
        if (item.community_metrics or {}).get("hn_id"):
            _ingest_hn(session, item, article, settings, stats, touched, matcher)
        _link_by_domain(session, item, article, touched)
    else:
        _ingest_funding_news(session, item, article, stats, touched, matcher)
    # Link remaining mentions of companies we already track.
    for sid in matcher.find(item.title):
        if sid not in touched:
            startup = session.get(Startup, sid)
            _mention(session, article, startup, "name_mention")
            _event_signals(session, startup, article, item.source_key)
            touched.add(sid)
    stats["touched"] = touched
    return stats


def _ingest_funding_news(session, item: NewsItem, article: NewsArticle, stats, touched, matcher) -> None:
    ext = extract_funding(item.title, item.summary, item.source_type)
    if not ext:
        return
    res = resolve_or_create(session, ext.company_name, discovered_via=item.source_key, defaults={
        "industry": ext.industry_hint, "description": None, **_location_defaults(ext.location_hint),
    })
    startup = res.startup
    if res.created:
        stats["startups_created"] += 1
        matcher.add(startup)
        startup.primary_source_url = article.url
        if ext.industry_hint:
            add_citation(session, startup, "industry", ext.industry_hint, "reported", key=f"a{article.id}",
                          source_type=item.source_type, publisher=item.publisher, url=article.url, article=article,
                          published_at=item.published_at, is_estimate=True,
                          note=f"Estimated from headline wording ('{ext.descriptor or item.title[:60]}')")
    if not startup.industry and ext.industry_hint:
        startup.industry = ext.industry_hint
    touched.add(startup.id)
    _mention(session, article, startup, "extracted_subject")
    announced = (item.published_at or utcnow()).date()
    rnd, outcome = record_round(
        session, startup, round_type=ext.round_type, amount=ext.amount, currency=ext.currency,
        amount_text=ext.amount_text, announced=announced, evidence_status=ext.evidence_status,
        publisher=item.publisher, source_url=article.url, article_id=article.id,
        investors=ext.investors, leads=ext.lead_investors,
    )
    value = " ".join(p for p in (ext.round_type, ext.amount_text) if p) or "Funding mentioned"
    add_citation(session, startup, "funding_round", value, ext.evidence_status, key=f"a{article.id}",
                  source_type=item.source_type, publisher=item.publisher, url=article.url, article=article,
                  published_at=item.published_at, note=f"Extraction rule: {ext.rule}; outcome: {outcome}")
    if ext.investors:
        add_citation(session, startup, "investors", "; ".join(ext.investors), ext.evidence_status,
                      key=f"a{article.id}", source_type=item.source_type, publisher=item.publisher, url=article.url,
                      article=article, published_at=item.published_at,
                      note=("Lead: " + ", ".join(ext.lead_investors)) if ext.lead_investors else None)
    _add_signal(session, startup, "funding_announcement" if ext.evidence_status not in ("rumor", "target") else f"funding_{ext.evidence_status}",
                f"funding:{rnd.id}", source_key=item.source_key, detail=f"{value} ({ext.evidence_status})",
                url=article.url, observed_at=item.published_at, article=article)
    _event_signals(session, startup, article, item.source_key)


def _link_by_domain(session: Session, item: NewsItem, article: NewsArticle, touched: set[int]) -> None:
    """A community post linking to a tracked company's own website is about that company."""
    domain = company_domain(item.url)
    if not domain:
        return
    for startup in session.scalars(select(Startup).where(Startup.domain == domain)):
        if startup.id not in touched:
            _mention(session, article, startup, "link_domain")
            _add_signal(session, startup, "community_post", f"community:{startup.id}:{article.id}",
                        source_key=item.source_key, detail=item.title, url=(item.community_metrics or {}).get("discussion_url"),
                        observed_at=item.published_at, article=article)
            touched.add(startup.id)


def _ingest_hn(session, item: NewsItem, article: NewsArticle, settings: Settings, stats, touched, matcher) -> None:
    ext = extract_hn(item.title)
    metrics = item.community_metrics or {}
    points = metrics.get("points", 0)
    if not ext or not ext.company_name:
        return
    domain = company_domain(item.url)
    if ext.kind == "show_hn" and (points < settings.hn_min_points or not domain):
        return  # side projects and repo links are kept as articles but not promoted to companies
    res = resolve_or_create(session, ext.company_name, website=item.url if domain else None,
                            discovered_via=item.source_key, defaults={"description": ext.tagline})
    startup = res.startup
    if res.created:
        stats["startups_created"] += 1
        matcher.add(startup)
        startup.primary_source_url = metrics.get("discussion_url") or article.url
    elif not startup.description and ext.tagline:
        startup.description = ext.tagline
    touched.add(startup.id)
    _mention(session, article, startup, "hn_title")
    discussion = metrics.get("discussion_url")
    _add_signal(session, startup, ext.kind, f"hn:{metrics.get('hn_id', article.id)}", source_key=item.source_key,
                detail=f"{item.title} ({points} points, {metrics.get('comments', 0)} comments)",
                url=discussion or article.url, observed_at=item.published_at, article=article)
    _add_signal(session, startup, "product_launch", f"news:{startup.id}:product_launch:{article.id}",
                source_key=item.source_key, detail=item.title, url=discussion, observed_at=item.published_at, article=article)
    if domain:
        add_citation(session, startup, "website", item.url, "company_announced", key=f"a{article.id}",
                      source_type="community", publisher="Hacker News", url=discussion or article.url, article=article,
                      published_at=item.published_at, note="Link posted by the submitter; verify ownership")
    if ext.yc_batch:
        detail = f"Y Combinator {ext.yc_batch} (stated in Launch HN title)"
        _add_signal(session, startup, "accelerator", f"accelerator:{startup.id}:yc", source_key=item.source_key,
                    detail=detail, url=discussion, observed_at=item.published_at, article=article)
        add_citation(session, startup, "accelerator", f"Y Combinator {ext.yc_batch}", "company_announced",
                      key=f"a{article.id}", source_type="community", publisher="Hacker News", url=discussion,
                      article=article, published_at=item.published_at)


# --------------------------------------------------------------------------- SEC ingestion

def ingest_form_d(session: Session, item: FormDItem) -> dict:
    stats = {"new": 0, "duplicate": 0, "startups_created": 0, "touched": set()}
    if session.scalar(select(exists().where(SecFiling.accession_number == item.accession_number))):
        stats["duplicate"] = 1
        return stats
    candidate, reason = assess_candidate(item)
    executives = [p.name for p in item.related_persons if any("Executive" in r for r in p.relationships)]
    filing = SecFiling(
        accession_number=item.accession_number, cik=item.cik, form_type=item.form_type, is_amendment=item.is_amendment,
        issuer_name=item.issuer_name, normalized_name=normalize_company_name(item.issuer_name),
        filing_date=item.filing_date, entity_type=item.entity_type, year_of_incorporation=item.year_of_incorporation,
        incorporated_within_five_years=item.incorporated_within_five_years, industry_group=item.industry_group,
        investment_fund_type=item.investment_fund_type, revenue_range=item.revenue_range,
        federal_exemptions=item.federal_exemptions, date_of_first_sale=item.date_of_first_sale,
        total_offering_amount=item.total_offering_amount, offering_amount_indefinite=item.offering_amount_indefinite,
        total_amount_sold=item.total_amount_sold, total_remaining=item.total_remaining,
        investor_count=item.investor_count, has_non_accredited_investors=item.has_non_accredited_investors,
        securities_types=item.securities_types,
        related_persons=[{"name": p.name, "relationships": p.relationships, "clarification": p.clarification}
                         for p in item.related_persons],
        city=item.city, state_or_country=item.state_or_country, filing_url=item.filing_url,
        document_url=item.document_url, is_startup_candidate=candidate, candidate_reason=reason,
        review_flags=review_flags(item),
    )
    session.add(filing)
    session.flush()
    stats["new"] = 1

    startup = _match_filing(session, filing)
    if startup is None and candidate:
        startup = Startup(
            name=display_name(item.issuer_name), normalized_name=filing.normalized_name, legal_name=item.issuer_name,
            sec_cik=item.cik, hq_city=item.city.title() if item.city else None, hq_state=item.state_or_country,
            founded_year=item.year_of_incorporation, industry=INDUSTRY_LABELS.get(item.industry_group or ""),
            key_people=", ".join(executives) or None, discovered_via="sec_form_d", review_status="Needs Verification",
            primary_source_url=item.filing_url, flags=[],
        )
        session.add(startup)
        session.flush()
        session.add(ReviewEvent(startup_id=startup.id, to_status="Needs Verification", actor="discovery-engine",
                                note="Discovered via SEC Form D; verify it is an operating startup"))
        filing.startup_id, filing.match_status, filing.match_score = startup.id, "created", 1.0
        filing.match_note = "New record created from the filing"
        stats["startups_created"] = 1
        for other, score in similar_startups(session, startup):
            record_duplicate(session, startup, other, score, f"Similar names ({score:.0%}) - Form D issuer vs existing record")
    if startup is None or filing.startup_id is None:
        return stats

    stats["touched"].add(startup.id)
    _apply_filing(session, startup, filing, executives)
    return stats


def _match_filing(session: Session, filing: SecFiling) -> Startup | None:
    found = session.scalar(select(Startup).where(Startup.sec_cik == filing.cik))
    if found:
        filing.startup_id, filing.match_status, filing.match_score = found.id, "auto_matched", 1.0
        filing.match_note = "Same SEC CIK"
        return found
    exact = list(session.scalars(select(Startup).where(Startup.normalized_name == filing.normalized_name)))
    if len(exact) == 1:
        s = exact[0]
        state_conflict = s.hq_state and filing.state_or_country and s.hq_state.strip().lower() not in (
            filing.state_or_country.lower(), _state_code(filing.state_or_country))
        if state_conflict:
            filing.suggested_startup_id, filing.match_status, filing.match_score = s.id, "needs_review", 0.8
            filing.match_note = f"Same name but location differs ({s.hq_state} vs {filing.state_or_country})"
            return None
        filing.startup_id, filing.match_status, filing.match_score = s.id, "auto_matched", 0.95
        filing.match_note = "Identical normalised legal name; no conflicting location"
        s.sec_cik = s.sec_cik or filing.cik
        return s
    if len(exact) > 1:
        filing.suggested_startup_id, filing.match_status = exact[0].id, "needs_review"
        filing.match_note = f"{len(exact)} tracked companies share this name"
        return None
    similar = sorted(similar_names(session, filing.normalized_name), key=lambda x: -x[1])
    if similar:
        s, score = similar[0]
        filing.suggested_startup_id, filing.match_status, filing.match_score = s.id, "needs_review", score
        filing.match_note = f"Similar name to '{s.name}' ({score:.0%}); confirm before linking"
    return None


def _state_code(value: str) -> str:
    return value.strip().lower()[:2]


def _apply_filing(session: Session, startup: Startup, filing: SecFiling, executives: list[str]) -> None:
    if not startup.legal_name:
        startup.legal_name = filing.issuer_name
    startup.sec_cik = startup.sec_cik or filing.cik
    if not startup.key_people and executives:
        startup.key_people = ", ".join(executives)
    if not startup.founded_year and filing.year_of_incorporation:
        startup.founded_year = filing.year_of_incorporation
    if not startup.hq_state and filing.state_or_country:
        startup.hq_state, startup.hq_city = filing.state_or_country, startup.hq_city or (filing.city or "").title() or None

    sold = filing.total_amount_sold
    offered = "Indefinite" if filing.offering_amount_indefinite else (
        f"${filing.total_offering_amount:,.0f}" if filing.total_offering_amount is not None else "not stated")
    summary = f"Form {filing.form_type}: ${sold or 0:,.0f} sold of {offered} offered"
    filed = filing.filing_date or utcnow().date()
    if sold:
        existing = None
        if filing.is_amendment:
            existing = session.scalar(select(FundingRound).where(
                FundingRound.startup_id == startup.id, FundingRound.evidence_status == "regulatory_filing"
            ).order_by(FundingRound.announced_date.desc()))
        if existing:
            existing.notes = ((existing.notes + "; ") if existing.notes else "") + (
                f"Amended by {filing.accession_number} on {filed}: amount sold {existing.amount or 0:,.0f} -> {sold:,.0f}")
            existing.amount, existing.amount_text, existing.sec_filing_id = sold, summary, filing.id
            existing.source_url = filing.filing_url
        else:
            record_round(session, startup, round_type=None, amount=sold, currency="USD", amount_text=summary,
                         announced=filed, evidence_status="regulatory_filing", publisher="SEC EDGAR",
                         source_url=filing.filing_url, sec_filing_id=filing.id)
    _add_signal(session, startup, "regulatory_filing", f"formd:{filing.accession_number}", source_key="sec_form_d",
                detail=summary, url=filing.filing_url, observed_at=datetime.combine(filed, datetime.min.time()), filing=filing)
    add_citation(session, startup, "sec_form_d", summary, "regulatory_filing", key=filing.accession_number,
                  source_type="regulatory", publisher="SEC EDGAR", url=filing.filing_url, filing=filing,
                  published_at=datetime.combine(filed, datetime.min.time()),
                  note="Form D is an offering notice; it does not confirm a priced round, valuation or investor identity")
    if executives:
        add_citation(session, startup, "key_people", ", ".join(executives), "regulatory_filing",
                      key=filing.accession_number, source_type="regulatory", publisher="SEC EDGAR",
                      url=filing.filing_url, filing=filing, note="Executive officers listed on Form D (not necessarily founders)")


def link_filing(session: Session, filing: SecFiling, startup: Startup, actor: str = "analyst") -> None:
    """Manually confirm that a filing belongs to a company (from the review queue)."""
    filing.startup_id, filing.match_status, filing.match_note = startup.id, "confirmed", f"Confirmed by {actor}"
    executives = [p["name"] for p in (filing.related_persons or []) if any("Executive" in r for r in p["relationships"])]
    _apply_filing(session, startup, filing, executives)
    refresh_funding_summary(startup)
    compute_confidence(session, startup)


# --------------------------------------------------------------------------- orchestration

def make_client(settings: Settings) -> PoliteClient:
    hosts = {"www.sec.gov": settings.sec_min_interval_seconds, "efts.sec.gov": settings.sec_min_interval_seconds}
    return PoliteClient(user_agent=settings.http_user_agent, timeout=settings.http_timeout_seconds,
                        min_interval=settings.http_min_interval_seconds, host_intervals=hosts)


REDDIT_RECHECK_DAYS = 60


def stored_reddit_ids(source_key: str) -> list[str]:
    """Reddit posts stored in the last 60 days, re-checked each run so deleted posts are removed."""
    since = utcnow() - timedelta(days=REDDIT_RECHECK_DAYS)
    with session_scope() as session:
        rows = session.scalars(select(NewsArticle).where(NewsArticle.source_key == source_key,
                                                         NewsArticle.retrieved_at >= since))
        return [a.community_metrics["reddit_id"] for a in rows if (a.community_metrics or {}).get("reddit_id")]


def purge_reddit_posts(source_key: str, reddit_ids: list[str]) -> int:
    """Delete stored posts (and signals quoting their titles) that were deleted or removed on Reddit."""
    if not reddit_ids:
        return 0
    wanted = set(reddit_ids)
    with session_scope() as session:
        articles = [a for a in session.scalars(select(NewsArticle).where(NewsArticle.source_key == source_key))
                    if (a.community_metrics or {}).get("reddit_id") in wanted]
        for a in articles:
            for sig in session.scalars(select(DiscoverySignal).where(DiscoverySignal.article_id == a.id)):
                session.delete(sig)
            session.delete(a)
        return len(articles)


def make_sec_client(settings: Settings) -> PoliteClient:
    return PoliteClient(user_agent=settings.sec_user_agent, timeout=settings.http_timeout_seconds,
                        min_interval=settings.sec_min_interval_seconds)


def run_source(source, client: PoliteClient, settings: Settings, trigger: str,
               sec_client: PoliteClient | None = None) -> dict:
    lock_name = f"source:{source.key}"
    with session_scope() as session:
        if not acquire_lock(session, lock_name, settings.job_lock_minutes):
            session.add(JobRun(job_name="discovery", source_key=source.key, trigger=trigger, status="skipped",
                               finished_at=utcnow(), error_message="Already running (lock held)"))
            return {"source": source.key, "status": "skipped", "reason": "already running"}
        run = JobRun(job_name="discovery", source_key=source.key, trigger=trigger)
        session.add(run)
        session.commit()
        run_id = run.id

    result = {"source": source.key, "status": "running", "fetched": 0, "new": 0, "duplicate": 0,
              "startups_created": 0, "item_errors": 0}
    error = None
    try:
        if isinstance(source, SecFormDSource):
            def _known(accession: str) -> bool:
                with session_scope() as s:
                    return bool(s.scalar(select(exists().where(SecFiling.accession_number == accession))))
            source.skip_accession = _known
            items = source.fetch(sec_client or client)  # SEC needs its own User-Agent with contact details
        elif isinstance(source, RedditSource):
            source.stored_ids = stored_reddit_ids(source.key)
            items = source.fetch(client)
            result["removed"] = purge_reddit_posts(source.key, source.removed_ids)
        else:
            items = source.fetch(client)
        result["fetched"] = len(items)
        error = ingest_items(items, settings, result)
        result["status"] = "partial" if result["item_errors"] else "success"
    except Exception as exc:  # the source failed as a whole; other sources keep running
        result["status"] = "failed"
        error = f"{type(exc).__name__}: {exc}"
        result["error"] = error
    finally:
        with session_scope() as session:
            run = session.get(JobRun, run_id)
            run.status, run.finished_at, run.error_message = result["status"], utcnow(), error
            run.items_fetched, run.items_new = result["fetched"], result["new"]
            run.items_duplicate, run.startups_created = result["duplicate"], result["startups_created"]
            release_lock(session, lock_name)
    return result


def ingest_items(items: list, settings: Settings, result: dict) -> str | None:
    errors: list[str] = []
    touched: set[int] = set()
    with session_scope() as session:
        matcher = NameMatcher(session)
        for item in items:
            savepoint = session.begin_nested()
            try:
                if isinstance(item, FormDItem):
                    stats = ingest_form_d(session, item)
                else:
                    stats = ingest_news_item(session, item, settings, matcher)
                savepoint.commit()
            except Exception as exc:
                savepoint.rollback()
                result["item_errors"] += 1
                label = getattr(item, "url", None) or getattr(item, "accession_number", "?")
                errors.append(f"{label}: {type(exc).__name__}: {exc}")
                if len(errors) <= 1:
                    traceback.print_exc()
                continue
            result["new"] += stats["new"]
            result["duplicate"] += stats["duplicate"]
            result["startups_created"] += stats["startups_created"]
            touched |= stats.get("touched", set())
        session.flush()
        for sid in touched:
            startup = session.get(Startup, sid)
            refresh_funding_summary(startup)
            compute_confidence(session, startup, settings.stale_after_days)
    if errors:
        return f"{len(errors)} item(s) failed. First: {errors[0]}"
    return None


def run_discovery(settings: Settings, keys: list[str] | None = None, groups: list[str] | None = None,
                  trigger: str = "manual", client: PoliteClient | None = None, sources: list | None = None,
                  sec_client: PoliteClient | None = None) -> dict:
    """Run the given sources (default: all enabled ones). Passing `client` (e.g. a test transport) uses it
    for every source, including SEC."""
    started = utcnow()
    skipped: list[dict] = []
    if sources is None:
        sources, skipped = build_sources(settings, keys=keys, groups=groups)
    own_client = client is None
    if own_client:
        client = make_client(settings)
        if any(isinstance(s, SecFormDSource) for s in sources):
            sec_client = make_sec_client(settings)
    results = []
    try:
        for source in sources:
            results.append(run_source(source, client, settings, trigger, sec_client=sec_client))
    finally:
        if own_client:
            client.close()
            if sec_client:
                sec_client.close()
    return {"started_at": started.isoformat(), "finished_at": utcnow().isoformat(), "results": results, "skipped": skipped}


def latest_success(session: Session) -> dict[str, datetime]:
    out: dict[str, datetime] = {}
    for run in session.scalars(select(JobRun).where(JobRun.status.in_(["success", "partial"])).order_by(JobRun.finished_at)):
        if run.source_key and run.finished_at:
            out[run.source_key] = run.finished_at
    return out


def today() -> date:
    return utcnow().date()
