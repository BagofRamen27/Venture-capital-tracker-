"""Wikidata enrichment, tested against responses shaped like the real MediaWiki API."""
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import select

from tests.conftest import make_client
from vcdiscovery import db
from vcdiscovery.models import Citation, JobLock, JobRun, Startup
from vcdiscovery.resolution import resolve_or_create
from vcdiscovery.text import company_domain
from vcdiscovery.wikidata import API, parse_entity, run_enrichment


def item(qid, label, description, p31=None, website=None, inception=None, founders=(), hq=(), country=(), industry=(),
         aliases=()):
    def ref(q):
        return {"mainsnak": {"snaktype": "value", "datavalue": {"value": {"entity-type": "item", "id": q}, "type": "wikibase-entityid"}},
                "rank": "normal"}
    claims = {}
    if p31:
        claims["P31"] = [ref(p31)]
    if website:
        claims["P856"] = [{"mainsnak": {"snaktype": "value", "datavalue": {"value": website, "type": "string"}}, "rank": "normal"}]
    if inception:
        claims["P571"] = [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": inception, "precision": 11}, "type": "time"}},
                           "rank": "normal"}]
    for prop, values in (("P112", founders), ("P159", hq), ("P17", country), ("P452", industry)):
        if values:
            claims[prop] = [ref(q) for q in values]
    return {"id": qid, "labels": {"en": {"value": label}}, "descriptions": {"en": {"value": description}},
            "aliases": {"en": [{"value": a} for a in aliases]}, "claims": claims}


ENTITIES = {
    "Q1001": item("Q1001", "Acme Robotics", "American warehouse robotics startup", p31="Q4830453",
                  website="https://www.acmerobotics.example/", inception="+2019-03-01T00:00:00Z",
                  founders=["Q2001"], hq=["Q3001"], country=["Q30"], industry=["Q4001"]),
    "Q1002": item("Q1002", "Acme Robotics", "1985 studio album", p31="Q482994"),
    "Q1101": item("Q1101", "Nova", "French software company", p31="Q4830453"),
    "Q1102": item("Q1102", "Nova", "American fintech startup"),
    "Q2001": item("Q2001", "Jane Example", "engineer"),
    "Q3001": item("Q3001", "Austin", "city in Texas"),
    "Q30": item("Q30", "United States", "country"),
    "Q4001": item("Q4001", "robotics", "branch of engineering"),
}
SEARCH = {"Acme Robotics": ["Q1001", "Q1002"], "Nova": ["Q1101", "Q1102"]}


def wikidata_api(calls, error=False):
    def handler(request: httpx.Request) -> httpx.Response:
        q = {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}
        calls.append(q)
        assert q["maxlag"] == "5" and q["format"] == "json"
        if error:
            return httpx.Response(200, json={"error": {"code": "maxlag", "info": "Waiting for a database server"}})
        if q["action"] == "wbsearchentities":
            return httpx.Response(200, json={"search": [{"id": i, "label": ENTITIES[i]["labels"]["en"]["value"]}
                                                        for i in SEARCH.get(q["search"], [])]})
        ids = q["ids"].split("|")
        return httpx.Response(200, json={"entities": {i: ENTITIES.get(i, {"id": i, "missing": ""}) for i in ids}})
    return {API: handler}


def add(name, **fields):
    with db.session_scope() as s:
        st = resolve_or_create(s, name, discovered_via="test").startup
        for k, v in fields.items():
            setattr(st, k, v)
        if "website" in fields:
            st.domain = company_domain(fields["website"])
        return st.id


def get(sid):
    with db.session_scope() as s:
        st = s.get(Startup, sid)
        s.expunge(st)
        return st


def test_name_only_match_fills_missing_fields_without_overwriting(settings):
    sid = add("Acme Robotics", industry="Robotics")  # industry already known: must not change
    calls = []
    result = run_enrichment(settings, make_client(wikidata_api(calls)))
    assert result == {"source": "wikidata", "status": "success", "checked": 1, "matched": 1, "fields_filled": 6}
    st = get(sid)
    assert st.website == "https://www.acmerobotics.example/" and st.domain == "acmerobotics.example"
    assert (st.founded_year, st.founders, st.hq_city, st.hq_country) == (2019, "Jane Example", "Austin", "United States")
    assert st.industry == "Robotics"
    assert st.description == "American warehouse robotics startup"
    assert st.extra["wikidata"]["qid"] == "Q1001"  # the 1985 album with the same name is ignored
    with db.session_scope() as s:
        cites = s.scalars(select(Citation).where(Citation.startup_id == sid, Citation.publisher == "Wikidata")).all()
        assert {c.field_name for c in cites} == {"website", "founded_year", "founders", "hq_city", "hq_country", "description"}
        assert all(c.evidence_status == "community_sourced" and c.source_url == "https://www.wikidata.org/wiki/Q1001" for c in cites)
        run = s.scalar(select(JobRun).where(JobRun.source_key == "wikidata"))
        assert run.status == "success" and run.items_new == 1
        assert s.scalar(select(JobLock)) is None
    assert [c["action"] for c in calls] == ["wbsearchentities", "wbgetentities", "wbgetentities"]


def test_sec_style_legal_name_is_searched_without_suffix(settings):
    sid = add("Acme Robotics, Inc.", website="https://acmerobotics.example")
    calls = []
    run_enrichment(settings, make_client(wikidata_api(calls)))
    assert calls[0]["search"] == "Acme Robotics"
    assert get(sid).extra["wikidata"]["qid"] == "Q1001"


def test_known_website_must_match(settings):
    good = add("Acme Robotics", website="https://acmerobotics.example")
    calls = []
    run_enrichment(settings, make_client(wikidata_api(calls)))
    assert get(good).extra["wikidata"]["qid"] == "Q1001"


def test_different_website_is_not_matched(settings):
    sid = add("Acme Robotics", website="https://acme-other.example")
    result = run_enrichment(settings, make_client(wikidata_api([])))
    st = get(sid)
    assert result["matched"] == 0 and "qid" not in st.extra["wikidata"]
    assert st.founders is None and st.website == "https://acme-other.example"


def test_ambiguous_names_are_left_alone(settings):
    sid = add("Nova")
    run_enrichment(settings, make_client(wikidata_api([])))
    st = get(sid)
    assert "qid" not in st.extra["wikidata"] and "share this name" in st.extra["wikidata"]["reason"]


def test_companies_are_not_looked_up_again(settings):
    add("Acme Robotics")
    add("Nova")
    run_enrichment(settings, make_client(wikidata_api([])))
    calls = []
    result = run_enrichment(settings, make_client(wikidata_api(calls)))
    assert calls == [] and result["checked"] == 0  # matched: done; unmatched: re-checked after 30 days


def test_api_error_is_logged_and_releases_lock(settings):
    sid = add("Acme Robotics")
    result = run_enrichment(settings, make_client(wikidata_api([], error=True)))
    assert result["status"] == "failed" and "maxlag" in result["error"]
    assert get(sid).founders is None
    with db.session_scope() as s:
        assert s.scalar(select(JobRun).where(JobRun.source_key == "wikidata")).status == "failed"
        assert s.scalar(select(JobLock)) is None


def test_parse_entity_skips_deprecated_and_imprecise_values():
    e = item("Q9", "X Corp", "company", website="https://old.example")
    e["claims"]["P856"] = [
        {"mainsnak": {"snaktype": "value", "datavalue": {"value": "https://old.example", "type": "string"}}, "rank": "deprecated"},
        {"mainsnak": {"snaktype": "value", "datavalue": {"value": "https://new.example", "type": "string"}}, "rank": "normal"},
        {"mainsnak": {"snaktype": "value", "datavalue": {"value": "https://best.example", "type": "string"}}, "rank": "preferred"},
    ]
    e["claims"]["P571"] = [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": "+1900-00-00T00:00:00Z", "precision": 7}}},
                            "rank": "normal"}]
    facts = parse_entity(e)
    assert facts.website == "https://best.example" and facts.founded_year is None
