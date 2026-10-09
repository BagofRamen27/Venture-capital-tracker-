"""YouTube: public channel feeds (no key) and search through the official YouTube Data API v3."""
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import func, select, update

from tests.conftest import fixture_text, make_client
from tests.test_pipeline import ingest, news
from vcdiscovery import db
from vcdiscovery.models import ArticleMention, Citation, FundingRound, NewsArticle, Startup, utcnow
from vcdiscovery.pipeline import run_discovery
from vcdiscovery.sources import build_sources
from vcdiscovery.sources.rss import RSSSource
from vcdiscovery.sources.youtube import API, YouTubeSearchSource

FEED = "https://www.youtube.com/feeds/videos.xml?channel_id=UCCjyq_K1Xwfg8Lndy7lKMpA"


def channel():
    return RSSSource(key="youtube_techcrunch", name="YouTube: TechCrunch", url=FEED, publisher="TechCrunch",
                     group="video", source_type="video")


def result(vid, title, channel="Some Channel", **snippet):
    return {"kind": "youtube#searchResult", "id": {"kind": "youtube#video", "videoId": vid},
            "snippet": {"publishedAt": "2026-10-08T14:00:00Z", "channelId": "UCx", "title": title,
                        "description": "Short description", "channelTitle": channel,
                        "liveBroadcastContent": "none", **snippet}}


RESULTS = [
    result("v1", "Acme Robotics demo: the picking arm in action"),
    result("v2", "Founder Q&amp;A: we&#39;re hiring"),
    result("v3", "Live soon", liveBroadcastContent="upcoming"),
]


def youtube_api(calls, items=RESULTS):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"kind": "youtube#searchListResponse", "items": items})
    return {API: handler}


def search():
    return YouTubeSearchSource(key="youtube_search", name="YouTube search", queries=["startup raises", "Launch YC"],
                               api_key="AIzaSECRET")


def test_channel_feed_videos_are_read_like_headlines(settings):
    result_ = run_discovery(settings, sources=[channel()], client=make_client({FEED: fixture_text("youtube_channel.xml")}))
    assert result_["results"][0]["status"] == "success" and result_["results"][0]["fetched"] == 2
    with db.session_scope() as s:
        startup = s.scalar(select(Startup).where(Startup.name == "Orbital Grid"))
        rnd = s.scalar(select(FundingRound).where(FundingRound.startup_id == startup.id))
        assert (rnd.round_type, rnd.amount, rnd.evidence_status) == ("Series A", 18_000_000, "reported")
        cite = s.scalar(select(Citation).where(Citation.startup_id == startup.id, Citation.field_name == "funding_round"))
        assert (cite.source_type, cite.publisher, cite.source_url) == ("video", "TechCrunch", "https://youtube.com/watch?v=vid000001")
        article = s.scalar(select(NewsArticle).where(NewsArticle.title.like("Orbital Grid%")))
        assert "Example Ventures" in article.summary
        assert s.scalar(select(func.count(Startup.id))) == 1  # the panel video names no company


def test_same_publisher_video_and_article_are_not_independent(settings):
    ingest(settings, [news("Orbital Grid raises $18M Series A", "https://techcrunch.com/orbital", publisher="TechCrunch")])
    run_discovery(settings, sources=[channel()], client=make_client({FEED: fixture_text("youtube_channel.xml")}))
    with db.session_scope() as s:
        assert s.scalar(select(FundingRound)).evidence_status == "reported"  # one publisher, not corroborated


def test_search_uses_header_key_and_links_without_creating(settings):
    ingest(settings, [news("Acme Robotics raises $12M Series A", "https://a.example/1")])
    calls = []
    result_ = run_discovery(settings, sources=[search()], client=make_client(youtube_api(calls)))
    assert result_["results"][0]["status"] == "success" and result_["results"][0]["startups_created"] == 0
    assert len(calls) == 2 and all(c.headers["x-goog-api-key"] == "AIzaSECRET" and "AIza" not in str(c.url) for c in calls)
    query = parse_qs(urlsplit(str(calls[0].url)).query)
    assert query["type"] == ["video"] and query["q"] == ["startup raises"] and "publishedAfter" in query
    with db.session_scope() as s:
        assert s.scalar(select(func.count(Startup.id))) == 1
        titles = sorted(a.title for a in s.scalars(select(NewsArticle).where(NewsArticle.source_key == "youtube_search")))
        assert titles == ["Acme Robotics demo: the picking arm in action", "Founder Q&A: we're hiring"]  # unescaped; upcoming skipped
        mention = s.scalar(select(ArticleMention).join(NewsArticle).where(NewsArticle.source_key == "youtube_search"))
        assert mention.startup.name == "Acme Robotics" and mention.match_method == "name_mention"
        assert s.scalar(select(NewsArticle).where(NewsArticle.title.like("Acme Robotics demo%"))).publisher == "YouTube: Some Channel"


def test_search_results_are_deleted_after_30_days(settings):
    run_discovery(settings, sources=[search()], client=make_client(youtube_api([])))
    with db.session_scope() as s:
        s.execute(update(NewsArticle).where(NewsArticle.title.like("Founder%")).values(retrieved_at=utcnow() - timedelta(days=31)))
    result_ = run_discovery(settings, sources=[search()], client=make_client(youtube_api([], items=[])))
    assert result_["results"][0]["removed"] == 1
    with db.session_scope() as s:
        assert [a.title for a in s.scalars(select(NewsArticle))] == ["Acme Robotics demo: the picking arm in action"]


def test_quota_or_key_errors_fail_the_source_without_leaking_the_key(settings):
    client = make_client({API: lambda r: httpx.Response(403, json={"error": {"message": "quotaExceeded"}})})
    result_ = run_discovery(settings, sources=[search()], client=client)
    assert result_["results"][0]["status"] == "failed" and "403" in result_["results"][0]["error"]
    assert "AIza" not in result_["results"][0]["error"]


def test_search_waits_for_key_and_channel_feeds_need_none(settings):
    sources, skipped = build_sources(settings, keys=["youtube_search", "youtube_techcrunch"])
    assert [s.key for s in sources] == ["youtube_techcrunch"] and sources[0].source_type == "video"
    assert "YOUTUBE_API_KEY" in skipped[0]["reason"]
    settings.youtube_api_key = "key"
    sources, _ = build_sources(settings, keys=["youtube_search"])
    assert isinstance(sources[0], YouTubeSearchSource) and sources[0].queries
