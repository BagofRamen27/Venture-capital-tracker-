from datetime import date

import httpx
import pytest

from tests.conftest import FIXTURES, fixture_text, make_client
from vcdiscovery.http import SourceUnavailable
from vcdiscovery.sources.hackernews import HackerNewsSource
from vcdiscovery.sources.rss import RSSSource
from vcdiscovery.sources.sec_formd import (
    SecFormDSource,
    assess_candidate,
    daily_index_url,
    parse_daily_index,
    parse_form_d_xml,
    review_flags,
)

ACME_DIR = "https://www.sec.gov/Archives/edgar/data/1999001/000199900126000001/"
FUND_DIR = "https://www.sec.gov/Archives/edgar/data/1999002/000199900226000001/"
NORTH_DIR = "https://www.sec.gov/Archives/edgar/data/1999003/000199900326000002/"


def sec_routes():
    return {
        daily_index_url(date(2026, 10, 7)): fixture_text("sec_daily_index.idx"),
        ACME_DIR + "primary_doc.xml": fixture_text("form_d_acme.xml"),
        FUND_DIR + "primary_doc.xml": fixture_text("form_d_fund.xml"),
        NORTH_DIR + "primary_doc.xml": fixture_text("form_d_northstar_amendment.xml"),
    }


def test_hackernews_fetch_filters_non_launch_posts():
    client = make_client({"https://hn.algolia.com/api/v1/search_by_date": fixture_text("hn_search.json")})
    items = HackerNewsSource().fetch(client)
    titles = {i.title for i in items}
    assert "Ask HN: Who is hiring?" not in titles
    assert len(items) == 5  # deduplicated across the two queries
    hyperlane = next(i for i in items if "Hyperlane" in i.title)
    assert hyperlane.community_metrics["points"] == 142
    assert hyperlane.community_metrics["discussion_url"].endswith("41000001")


def test_rss_fetch_parses_items():
    src = RSSSource(key="example", name="Example", url="https://news.example.com/feed/", publisher="Example News", group="funding")
    items = src.fetch(make_client({"https://news.example.com/feed/": fixture_text("rss_funding.xml")}))
    assert len(items) == 5
    assert items[0].title.startswith("Acme Robotics raises")
    assert items[0].published_at.isoformat() == "2026-10-01T14:00:00"
    assert "<p>" not in items[0].summary


def test_rss_unreadable_feed_raises():
    src = RSSSource(key="bad", name="Bad", url="https://bad.example.com/feed", publisher="Bad")
    with pytest.raises(SourceUnavailable):
        src.fetch(make_client({"https://bad.example.com/feed": "<html><body>not a feed"}))


def test_daily_index_keeps_only_form_d():
    rows = parse_daily_index(fixture_text("sec_daily_index.idx"))
    assert [r["form_type"] for r in rows] == ["D", "D", "D/A"]
    acme = rows[0]
    assert acme["cik"] == "1999001"
    assert acme["accession_number"] == "0001999001-26-000001"
    assert acme["document_url"] == ACME_DIR + "primary_doc.xml"
    assert acme["filing_url"] == ACME_DIR + "0001999001-26-000001-index.htm"


def test_parse_form_d_startup():
    meta = parse_daily_index(fixture_text("sec_daily_index.idx"))[0]
    item = parse_form_d_xml((FIXTURES / "form_d_acme.xml").read_bytes(), meta)
    assert item.issuer_name == "ACME ROBOTICS, INC."
    assert (item.total_offering_amount, item.total_amount_sold, item.total_remaining) == (15e6, 12e6, 3e6)
    assert item.industry_group == "Other Technology"
    assert item.year_of_incorporation == 2023 and item.incorporated_within_five_years is True
    assert item.date_of_first_sale == date(2026, 9, 15)
    assert item.investor_count == 9
    assert item.state_or_country == "TEXAS" and item.city == "AUSTIN"
    assert [p.name for p in item.related_persons] == ["Jane Example", "Sam Sample"]
    assert item.related_persons[0].relationships == ["Executive Officer", "Director"]
    assert item.securities_types == ["Equity"]
    assert assess_candidate(item)[0] is True
    assert review_flags(item) == []


def test_parse_form_d_fund_is_not_a_startup():
    meta = parse_daily_index(fixture_text("sec_daily_index.idx"))[1]
    item = parse_form_d_xml(fixture_text("form_d_fund.xml"), meta)
    assert item.offering_amount_indefinite and item.total_offering_amount is None
    candidate, reason = assess_candidate(item)
    assert candidate is False and "fund" in reason.lower()
    assert any("Indefinite" in f for f in review_flags(item))
    assert any("not evidence of a completed raise" in f for f in review_flags(item))


def test_parse_form_d_amendment_older_company():
    meta = parse_daily_index(fixture_text("sec_daily_index.idx"))[2]
    item = parse_form_d_xml(fixture_text("form_d_northstar_amendment.xml"), meta)
    assert item.is_amendment and item.form_type == "D/A"
    assert assess_candidate(item) == (False, "Incorporated more than five years ago")
    assert any("Amendment" in f for f in review_flags(item))


def test_sec_source_fetch_skips_weekends_missing_days_and_known_filings():
    calls: list[str] = []
    client = make_client(sec_routes(), calls)
    # Thursday 8 Oct 2026, three days back: Wed 7 (has index), Tue 6 (404), Mon 5 (404)
    src = SecFormDSource(lookback_days=3, today=lambda: date(2026, 10, 8))
    src.skip_accession = lambda acc: acc == "0001999002-26-000001"
    items = src.fetch(client)
    assert {i.accession_number for i in items} == {"0001999001-26-000001", "0001999003-26-000002"}
    assert not any("1999002" in c and "primary_doc" in c for c in calls)


def test_sec_unpublished_index_403_is_skipped_when_older_days_load():
    # EDGAR answers 403 for yesterday's index until it is published (about 10 pm US Eastern)
    routes = {**sec_routes(), daily_index_url(date(2026, 10, 8)): 403}
    items = SecFormDSource(lookback_days=3, today=lambda: date(2026, 10, 9)).fetch(make_client(routes))
    assert len(items) == 3


def test_sec_403_on_every_index_means_access_refused():
    src = SecFormDSource(lookback_days=3, today=lambda: date(2026, 10, 9))
    with pytest.raises(SourceUnavailable, match="refused access"):
        src.fetch(make_client({"https://www.sec.gov/Archives/edgar/daily-index/": 403}))


def test_polite_client_retries_then_succeeds_and_refuses_403():
    attempts = {"n": 0}

    def flaky(_req):
        attempts["n"] += 1
        return httpx.Response(503) if attempts["n"] < 3 else httpx.Response(200, text="ok")

    client = make_client({"https://flaky.example.com/": flaky, "https://blocked.example.com/": 403})
    assert client.get("https://flaky.example.com/x").text == "ok"
    assert attempts["n"] == 3
    with pytest.raises(SourceUnavailable, match="refused access"):
        client.get("https://blocked.example.com/x")


def test_pasted_sec_user_agent_is_cleaned_for_http_headers():
    import h11

    from vcdiscovery.config import Settings

    raw = "  José Example\njose@example.com\r\n"
    with pytest.raises((h11.LocalProtocolError, UnicodeEncodeError)):  # what the first live run hit
        h11.Request(method="GET", target="/", headers=[("Host", "www.sec.gov"), ("User-Agent", raw)])
    cleaned = Settings(_env_file=None, sec_user_agent=raw).sec_user_agent
    assert cleaned == "Jose Example jose@example.com"
    h11.Request(method="GET", target="/", headers=[("Host", "www.sec.gov"), ("User-Agent", cleaned)])
