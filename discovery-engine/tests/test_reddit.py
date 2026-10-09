"""Reddit connector, tested against responses shaped like the real Reddit Data API."""
import base64
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import func, select

from tests.conftest import make_client
from tests.test_pipeline import ingest, news
from vcdiscovery import db
from vcdiscovery.models import ArticleMention, DiscoverySignal, JobRun, NewsArticle, Startup
from vcdiscovery.pipeline import run_discovery
from vcdiscovery.sources import build_sources
from vcdiscovery.sources.reddit import API, TOKEN_URL, RedditSource


def post(pid, title, score=50, url=None, is_self=False, sub="startups", **extra):
    return {"kind": "t3", "data": {"name": f"t3_{pid}", "id": pid, "title": title, "score": score, "num_comments": 12,
                                   "permalink": f"/r/{sub}/comments/{pid}/x/", "url": url or f"https://www.reddit.com/r/{sub}/comments/{pid}/x/",
                                   "is_self": is_self, "subreddit": sub, "created_utc": 1790000000, "author": "someone",
                                   "selftext": "long body that must never be stored", **extra}}


LISTING = [
    post("a1", "We just launched Acme Robotics' new picking arm", url="https://acmerobotics.example/launch"),
    post("a2", "Acme Robotics raised $12M Series A, AMA", is_self=True),
    post("a3", "Low effort post", score=1, is_self=True),
    post("a4", "NSFW thing", over_18=True, is_self=True),
    post("a5", "Removed by mods", removed_by_category="moderator", is_self=True),
]


def reddit_api(calls, listing=LISTING, info_gone=(), token_ok=True):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append((request.method, url, dict(request.headers)))
        if url.startswith(TOKEN_URL):
            if not token_ok:
                return httpx.Response(401, json={"message": "Unauthorized"})
            return httpx.Response(200, json={"access_token": "tok123", "token_type": "bearer", "expires_in": 86400})
        if "/api/info" in url:
            ids = parse_qs(urlsplit(url).query)["id"][0].split(",")
            children = [{"kind": "t3", "data": {"name": i, "author": "[deleted]" if i in info_gone else "someone"}} for i in ids]
            return httpx.Response(200, json={"data": {"children": children}})
        return httpx.Response(200, json={"data": {"children": listing if "/r/startups/" in url else []}})
    return {TOKEN_URL: handler, API: handler}


def source():
    return RedditSource(key="reddit", name="Reddit", subreddits=["startups", "SaaS"], client_id="cid", client_secret="csecret",
                        username="venturescout-bot", min_score=5)


def setup_company(settings):
    ingest(settings, [news("Acme Robotics raises $12M Series A", "https://a.example/1")])
    with db.session_scope() as s:
        st = s.scalar(select(Startup))
        st.website, st.domain = "https://acmerobotics.example", "acmerobotics.example"
        return st.id


def test_oauth_and_polite_headers():
    calls = []
    items = source().fetch(make_client(reddit_api(calls)))
    method, url, headers = calls[0]
    assert (method, url) == ("POST", TOKEN_URL)
    assert headers["authorization"] == "Basic " + base64.b64encode(b"cid:csecret").decode()
    assert headers["user-agent"] == "python:venturescout:0.1 (by /u/venturescout-bot)"
    listing_calls = [c for c in calls if "/r/" in c[1]]
    assert len(listing_calls) == 2 and all(c[2]["authorization"] == "bearer tok123" for c in listing_calls)
    # low score, NSFW and removed posts are skipped; post bodies and authors are never kept
    assert [i.community_metrics["reddit_id"] for i in items] == ["t3_a1", "t3_a2"]
    assert all(i.summary is None and "someone" not in repr(i) for i in items)
    assert items[0].url == "https://acmerobotics.example/launch"
    assert items[1].url == "https://www.reddit.com/r/startups/comments/a2/x/"


def test_posts_link_to_tracked_companies_but_never_create_them(settings):
    sid = setup_company(settings)
    result = run_discovery(settings, sources=[source()], client=make_client(reddit_api([])))
    assert result["results"][0]["status"] == "success" and result["results"][0]["startups_created"] == 0
    with db.session_scope() as s:
        assert s.scalar(select(func.count(Startup.id))) == 1
        methods = {m.match_method for m in s.scalars(select(ArticleMention).where(ArticleMention.startup_id == sid))}
        assert {"link_domain", "name_mention"} <= methods  # by website link and by name in the title
        assert s.scalar(select(DiscoverySignal).where(DiscoverySignal.signal_type == "community_post"))


def test_posts_deleted_on_reddit_are_removed_from_our_database(settings):
    setup_company(settings)
    run_discovery(settings, sources=[source()], client=make_client(reddit_api([])))
    with db.session_scope() as s:
        assert s.scalar(select(func.count(NewsArticle.id)).where(NewsArticle.source_key == "reddit")) == 2
    calls = []
    result = run_discovery(settings, sources=[source()], client=make_client(reddit_api(calls, listing=[], info_gone={"t3_a1"})))
    assert result["results"][0]["removed"] == 1
    assert any("/api/info" in c[1] and "t3_a1" in c[1] for c in calls)
    with db.session_scope() as s:
        titles = [a.title for a in s.scalars(select(NewsArticle).where(NewsArticle.source_key == "reddit"))]
        assert titles == ["Acme Robotics raised $12M Series A, AMA"]
        assert not s.scalars(select(DiscoverySignal).where(DiscoverySignal.detail.like("%picking arm%"))).all()


def test_rejected_credentials_fail_the_source_only(settings):
    result = run_discovery(settings, sources=[source()], client=make_client(reddit_api([], token_ok=False)))
    assert result["results"][0]["status"] == "failed" and "HTTP 401" in result["results"][0]["error"]
    with db.session_scope() as s:
        assert s.scalar(select(JobRun).where(JobRun.source_key == "reddit")).status == "failed"


def test_reddit_waits_for_credentials(settings):
    sources, skipped = build_sources(settings, keys=["reddit"])
    assert sources == [] and "REDDIT_CLIENT_ID" in skipped[0]["reason"]
    settings.reddit_client_id, settings.reddit_client_secret, settings.reddit_username = "id", "secret", "bot"
    sources, _ = build_sources(settings, keys=["reddit"])
    assert isinstance(sources[0], RedditSource) and "ycombinator" in sources[0].subreddits
