import pytest

from vcdiscovery.classify import classify_text
from vcdiscovery.extraction import extract_funding, extract_hn, extract_investors
from vcdiscovery.text import (
    canonical_url,
    company_domain,
    display_name,
    normalize_company_name,
    parse_money,
    title_fingerprint,
)


def test_canonical_url_strips_tracking_and_www():
    a = canonical_url("http://www.Example.com/story/?utm_source=rss&utm_medium=x&id=5#top")
    b = canonical_url("https://example.com/story?id=5")
    assert a == b == "https://example.com/story?id=5"


def test_company_domain_ignores_shared_hosts():
    assert company_domain("https://app.acme.co.uk/login") == "acme.co.uk"
    assert company_domain("https://github.com/acme/repo") is None
    assert company_domain("https://acme.vercel.app") is None
    assert company_domain(None) is None


def test_normalize_company_name_keeps_brand_words():
    assert normalize_company_name("Acme Robotics, Inc.") == "acme robotics"
    assert normalize_company_name("ACME ROBOTICS INC") == "acme robotics"
    assert normalize_company_name("Acme AI, LLC") == "acme ai"
    assert normalize_company_name("Acme AI") != normalize_company_name("Acme")
    assert normalize_company_name("Café Labs GmbH") == "cafe labs"


def test_display_name_for_sec_capitals():
    assert display_name("ACME ROBOTICS, INC.") == "Acme Robotics, Inc."
    assert display_name("Already Mixed Case") == "Already Mixed Case"


@pytest.mark.parametrize("text,expected", [
    ("$12M", (12e6, "USD")), ("€3.5 million", (3.5e6, "EUR")), ("£500K", (5e5, "GBP")),
    ("US$1.2 billion", (1.2e9, "USD")), ("$1,250,000", (1.25e6, "USD")), ("no money here", None),
])
def test_parse_money(text, expected):
    result = parse_money(text)
    assert (result[:2] if result else None) == expected


def test_title_fingerprint_matches_syndicated_copies():
    assert title_fingerprint("Acme raises $5M to build robots") == title_fingerprint("ACME raises $5M to build the robots!")


@pytest.mark.parametrize("title,name,amount,currency,round_type,status", [
    ("Acme Robotics raises $12M Series A led by Example Ventures", "Acme Robotics", 12e6, "USD", "Series A", "reported"),
    ("Paris-based fintech Qonto secures €50 million in Series D funding", "Qonto", 50e6, "EUR", "Series D", "reported"),
    ("Exclusive: AI chip startup Lumina closes $8.5M seed round", "Lumina", 8.5e6, "USD", "Seed", "reported"),
    ("Northwind Health Raises $5M in Seed Funding", "Northwind Health", 5e6, "USD", "Seed", "reported"),
    ("Kite, the AI startup, nabs $3M pre-seed", "Kite", 3e6, "USD", "Pre-seed", "reported"),
    ("Berlin-based climate tech startup Lumen Grid raises €4M seed round", "Lumen Grid", 4e6, "EUR", "Seed", "reported"),
    ("Platform Science raises $125M", "Platform Science", 125e6, "USD", None, "reported"),
    ("dbt Labs raises $222M", "dbt Labs", 222e6, "USD", None, "reported"),
    ("Stripe reportedly in talks to raise $1B", "Stripe", 1e9, "USD", None, "rumor"),
    ("Orbital aims to raise $20M Series B", "Orbital", 20e6, "USD", "Series B", "target"),
])
def test_extract_funding(title, name, amount, currency, round_type, status):
    ext = extract_funding(title)
    assert ext is not None
    assert (ext.company_name, ext.amount, ext.currency, ext.round_type, ext.evidence_status) == (
        name, amount, currency, round_type, status)


def test_press_release_is_company_announced():
    assert extract_funding("Acme raises $5M seed", source_type="press_release").evidence_status == "company_announced"


@pytest.mark.parametrize("title", [
    "How startups raise $1M in 2026",
    "Acme lands new CEO",
    "The week's 10 biggest funding rounds: Acme raises $5M",
    "Investors pour $2B into AI",
])
def test_extract_funding_rejects_non_events(title):
    assert extract_funding(title) is None


def test_extract_investors_lead_vs_participants():
    investors, leads = extract_investors(
        "Acme raised $12M led by Example Ventures with participation from Sample Capital and Placeholder Partners.")
    assert leads == ["Example Ventures"]
    assert set(investors) == {"Example Ventures", "Sample Capital", "Placeholder Partners"}


def test_extract_hn():
    launch = extract_hn("Launch HN: Tamarind Bio (YC W26) – Protein design tools")
    assert (launch.kind, launch.company_name, launch.yc_batch) == ("launch_hn", "Tamarind Bio", "W26")
    assert extract_hn("Show HN: Hyperlane – Open-source API gateway").company_name == "Hyperlane"
    assert extract_hn("Show HN: I built a tiny RSS reader").company_name is None
    assert extract_hn("Ask HN: Who is hiring?") is None


def test_classifier_explains_labels():
    neg = classify_text("Acme lays off 20% of staff amid restructuring")
    assert "layoffs" in neg["event_types"] and neg["sentiment"] == "negative"
    assert neg["evidence"]["negative_terms"]
    pos = classify_text("Acme raises $10M and partners with Example Bank")
    assert {"funding", "partnership"} <= set(pos["event_types"]) and pos["sentiment"] == "positive"
    assert classify_text("Acme publishes annual report")["sentiment"] == "neutral"
