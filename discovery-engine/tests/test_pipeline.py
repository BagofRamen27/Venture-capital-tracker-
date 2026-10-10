from datetime import date, datetime

from sqlalchemy import func, select

from tests.conftest import fixture_text, make_client
from tests.test_sources import sec_routes
from vcdiscovery import db
from vcdiscovery.funding import record_round
from vcdiscovery.models import (
    ArticleMention,
    DiscoverySignal,
    DuplicateCandidate,
    FundingRound,
    JobLock,
    JobRun,
    NewsArticle,
    SecFiling,
    Startup,
)
from vcdiscovery.pipeline import acquire_lock, ingest_items, run_discovery
from vcdiscovery.sources.base import NewsItem
from vcdiscovery.sources.hackernews import HackerNewsSource
from vcdiscovery.sources.rss import RSSSource
from vcdiscovery.sources.sec_formd import SecFormDSource

FEED_URL = "https://news.example.com/feed/"


def rss(key="example_news", publisher="Example News", url=FEED_URL):
    return RSSSource(key=key, name=publisher, url=url, publisher=publisher, group="funding")


def news(title, url, publisher="Other Outlet", when=datetime(2026, 10, 2, 9), source_type="news", summary=None):
    return NewsItem(source_key="manual", source_type=source_type, publisher=publisher, url=url, title=title,
                    summary=summary, published_at=when)


def ingest(settings, items):
    result = {"new": 0, "duplicate": 0, "startups_created": 0, "item_errors": 0}
    ingest_items(items, settings, result)
    return result


def get_startup(name):
    with db.session_scope() as s:
        st = s.scalar(select(Startup).where(Startup.name == name))
        if st:
            s.expunge(st)
        return st


def test_rss_discovery_extracts_companies_and_is_idempotent(settings):
    client = make_client({FEED_URL: fixture_text("rss_funding.xml")})
    first = run_discovery(settings, sources=[rss()], client=client)
    assert first["results"][0]["status"] == "success"
    assert first["results"][0]["startups_created"] == 3  # Acme Robotics, Qonto, Stripe (rumour)

    with db.session_scope() as s:
        names = set(s.scalars(select(Startup.name)))
        assert names == {"Acme Robotics", "Qonto", "Stripe"}
        acme = s.scalar(select(Startup).where(Startup.name == "Acme Robotics"))
        assert acme.funding_stage == "Series A"
        assert acme.total_funding_amount == 12e6 and acme.total_funding_currency == "USD"
        r = acme.rounds[0]
        assert r.evidence_status == "reported"
        assert {(ri.investor.name, ri.is_lead) for ri in r.investors} == {("Example Ventures", True), ("Sample Capital", False)}
        # The partnership headline is linked to Acme as company-specific news
        mentions = s.scalars(select(ArticleMention).where(ArticleMention.startup_id == acme.id)).all()
        assert len(mentions) == 2
        assert s.scalar(select(DiscoverySignal).where(DiscoverySignal.startup_id == acme.id,
                                                      DiscoverySignal.signal_type == "partnership"))
        stripe = s.scalar(select(Startup).where(Startup.name == "Stripe"))
        assert stripe.rounds[0].evidence_status == "rumor"
        assert stripe.total_funding_amount is None  # rumours never count as raised
        qonto = s.scalar(select(Startup).where(Startup.name == "Qonto"))
        assert qonto.hq_city == "Paris" and qonto.industry == "Fintech"
        assert acme.confidence_score is not None and acme.confidence_breakdown["components"]

    second = run_discovery(settings, sources=[rss()], client=client)
    assert second["results"][0]["new"] == 0 and second["results"][0]["duplicate"] == 5
    with db.session_scope() as s:
        assert s.scalar(select(func.count(Startup.id))) == 3
        assert s.scalar(select(func.count(NewsArticle.id))) == 5
        assert s.scalar(select(func.count(JobRun.id))) == 2


def test_corroboration_confirms_and_conflict_is_flagged(settings):
    ingest(settings, [news("Acme Robotics raises $12M Series A", "https://a.example/1", publisher="Outlet A")])
    ingest(settings, [news("Acme Robotics lands $12 million Series A to scale robots", "https://b.example/1", publisher="Outlet B")])
    with db.session_scope() as s:
        rounds = s.scalars(select(FundingRound)).all()
        assert len(rounds) == 1
        assert rounds[0].evidence_status == "confirmed"
        assert rounds[0].publishers == ["Outlet A", "Outlet B"]
    ingest(settings, [news("Acme Robotics raises $20M Series A", "https://c.example/1", publisher="Outlet C")])
    with db.session_scope() as s:
        rounds = s.scalars(select(FundingRound).order_by(FundingRound.id)).all()
        assert len(rounds) == 2 and all(r.conflict for r in rounds)
        acme = s.scalar(select(Startup))
        assert "conflicting_funding" in acme.flags
        assert any(c["component"] == "conflicts" for c in acme.confidence_breakdown["components"])


def test_missing_funding_date_is_not_imputed_or_merged(settings):
    ingest(settings, [news("Acme Robotics raises $12M Series A", "https://a.example/dated", publisher="Outlet A")])
    with db.session_scope() as s:
        startup = s.scalar(select(Startup).where(Startup.name == "Acme Robotics"))
        rnd, outcome = record_round(
            s, startup, round_type="Series A", amount=12e6, currency="USD",
            amount_text="$12M", announced=None, evidence_status="reported",
            publisher="Outlet B", source_url="https://b.example/undated",
        )
        assert outcome == "new"
        assert rnd.announced_date is None
        assert s.scalar(select(func.count(FundingRound.id))) == 2


def test_rumours_are_never_confirmed_by_repetition(settings):
    ingest(settings, [news("Orbital reportedly in talks to raise $50M", "https://a.example/r", publisher="Outlet A"),
                      news("Orbital is said to be raising $50M, sources say", "https://b.example/r", publisher="Outlet B")])
    with db.session_scope() as s:
        rounds = s.scalars(select(FundingRound)).all()
        assert {r.evidence_status for r in rounds} == {"rumor"}
        assert s.scalar(select(Startup)).total_funding_amount is None
    # A real report later replaces the rumour but is not "confirmed" by the earlier rumour outlets
    ingest(settings, [news("Orbital raises $50M", "https://c.example/r", publisher="Outlet C")])
    with db.session_scope() as s:
        r = s.scalars(select(FundingRound)).first()
        assert r.evidence_status == "reported"
        assert r.publishers == ["Outlet C"]


def test_syndicated_copy_is_marked_duplicate_and_not_counted(settings):
    ingest(settings, [news("Acme Robotics raises $12M Series A", "https://a.example/1", publisher="Outlet A")])
    ingest(settings, [news("Acme Robotics raises $12M Series A", "https://mirror.example/x", publisher="Mirror Site")])
    with db.session_scope() as s:
        articles = s.scalars(select(NewsArticle).order_by(NewsArticle.id)).all()
        assert articles[1].duplicate_of_id == articles[0].id
        assert s.scalar(select(FundingRound)).evidence_status == "reported"


def test_hn_discovery_promotes_only_credible_launches(settings):
    client = make_client({"https://hn.algolia.com/api/v1/search_by_date": fixture_text("hn_search.json")})
    run_discovery(settings, sources=[HackerNewsSource()], client=client)
    with db.session_scope() as s:
        startups = {st.name: st for st in s.scalars(select(Startup))}
        assert set(startups) == {"Hyperlane", "Tamarind Bio"}
        assert startups["Hyperlane"].domain == "hyperlane.dev"
        assert startups["Hyperlane"].description == "Open-source API gateway for small teams"
        tamarind = startups["Tamarind Bio"]
        types = {sig.signal_type for sig in tamarind.signals}
        assert {"launch_hn", "accelerator", "product_launch"} <= types
        # Every post is still stored as an article for the record
        assert s.scalar(select(func.count(NewsArticle.id))) == 5


def test_sec_ingestion_matches_news_company_and_ignores_funds(settings):
    ingest(settings, [news("Acme Robotics raises $12M Series A", "https://a.example/1", publisher="Outlet A",
                           when=datetime(2026, 10, 1))])
    client = make_client(sec_routes())
    result = run_discovery(settings, sources=[SecFormDSource(lookback_days=1, today=lambda: date(2026, 10, 8))], client=client)
    assert result["results"][0]["status"] == "success"
    with db.session_scope() as s:
        filings = {f.issuer_name: f for f in s.scalars(select(SecFiling))}
        acme_filing = filings["ACME ROBOTICS, INC."]
        assert acme_filing.match_status == "auto_matched"
        acme = s.scalar(select(Startup).where(Startup.name == "Acme Robotics"))
        assert acme_filing.startup_id == acme.id and acme.sec_cik == "1999001"
        assert acme.key_people == "Jane Example" and acme.founders is None  # executives are not assumed founders
        assert acme.founded_year == 2023
        statuses = sorted(r.evidence_status for r in acme.rounds)
        assert statuses == ["regulatory_filing", "reported"]
        # Form D is shown separately and NOT added to total funding
        assert acme.total_funding_amount == 12e6
        assert filings["EXAMPLE GROWTH FUND II, L.P."].startup_id is None
        assert filings["EXAMPLE GROWTH FUND II, L.P."].is_startup_candidate is False
        assert filings["NORTHSTAR THERAPEUTICS INC"].match_status == "unmatched"
        assert s.scalar(select(func.count(Startup.id))) == 1
    # Running again downloads nothing new
    calls: list[str] = []
    run_discovery(settings, sources=[SecFormDSource(lookback_days=1, today=lambda: date(2026, 10, 8))],
                  client=make_client(sec_routes(), calls))
    assert not [c for c in calls if c.endswith("primary_doc.xml")]


def test_sec_creates_startup_for_unknown_candidate(settings):
    run_discovery(settings, sources=[SecFormDSource(lookback_days=1, today=lambda: date(2026, 10, 8))],
                  client=make_client(sec_routes()))
    with db.session_scope() as s:
        acme = s.scalar(select(Startup))
        assert acme.name == "Acme Robotics, Inc." and acme.review_status == "Needs Verification"
        assert acme.hq_city == "Austin" and acme.industry == "Technology"
        assert s.scalar(select(SecFiling).where(SecFiling.startup_id == acme.id)).match_status == "created"


def test_one_failing_source_does_not_stop_others(settings):
    client = make_client({FEED_URL: fixture_text("rss_funding.xml"), "https://down.example.com/": 500})
    result = run_discovery(settings, sources=[rss(key="down", url="https://down.example.com/feed"), rss()], client=client)
    by_key = {r["source"]: r for r in result["results"]}
    assert by_key["down"]["status"] == "failed" and "HTTP 500" in by_key["down"]["error"]
    assert by_key["example_news"]["status"] == "success"
    with db.session_scope() as s:
        failed = s.scalar(select(JobRun).where(JobRun.source_key == "down"))
        assert failed.status == "failed" and failed.error_message
        assert s.scalar(select(func.count(JobLock.name))) == 0  # locks released


def test_lock_prevents_duplicate_runs(settings):
    with db.session_scope() as s:
        assert acquire_lock(s, "source:example_news", 60) is True
        assert acquire_lock(s, "source:example_news", 60) is False
    result = run_discovery(settings, sources=[rss()], client=make_client({FEED_URL: fixture_text("rss_funding.xml")}))
    assert result["results"][0]["status"] == "skipped"


def test_similar_names_create_review_item_not_merge(settings):
    ingest(settings, [news("Acme raises $3M seed", "https://a.example/s1", publisher="Outlet A"),
                      news("Acme Robotics raises $12M Series A", "https://b.example/s2", publisher="Outlet B")])
    with db.session_scope() as s:
        assert s.scalar(select(func.count(Startup.id))) == 2
        dup = s.scalar(select(DuplicateCandidate))
        assert dup is not None and dup.status == "open"
