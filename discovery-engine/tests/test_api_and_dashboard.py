import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.conftest import REPO_ROOT
from tests.test_pipeline import ingest, news
from vcdiscovery import db
from vcdiscovery.api import create_app
from vcdiscovery.csv_io import import_tracker_snapshot
from vcdiscovery.models import FundingRound, Startup
from vcdiscovery.scoring import load_config, refresh_scores
from vcdiscovery.site_export import write_site_data

TRACKER_JSON = REPO_ROOT / "vc-investment-tracker-web" / "examples" / "original-research.json"


def client_for(settings):
    return TestClient(create_app(settings), headers={"X-API-Key": settings.api_token} if settings.api_token else {})


def test_core_endpoints(settings):
    ingest(settings, [news("Acme Robotics raises $12M Series A led by Example Ventures", "https://a.example/1"),
                      news("Qonto raises €50M Series D", "https://a.example/2")])
    c = client_for(settings)
    assert c.get("/api/health").json()["startups"] == 2
    listing = c.get("/api/startups", params={"stage": "Series A"}).json()
    assert listing["total"] == 1 and listing["items"][0]["name"] == "Acme Robotics"
    sid = listing["items"][0]["id"]
    profile = c.get(f"/api/startups/{sid}").json()
    for key in ("funding_rounds", "sec_filings", "news", "citations", "confidence_breakdown", "review_history", "signals"):
        assert key in profile
    assert profile["funding_rounds"][0]["investors"][0] == {"name": "Example Ventures", "is_lead": True,
                                                           "source_url": "https://a.example/1"}
    assert c.post(f"/api/startups/{sid}/status", json={"status": "Nonsense"}).status_code == 422
    assert c.post(f"/api/startups/{sid}/status", json={"status": "Watchlist", "note": "Interesting"}).json()["review_status"] == "Watchlist"
    pipeline = {p["status"]: p["count"] for p in c.get("/api/pipeline").json()}
    assert pipeline["Watchlist"] == 1
    patched = c.patch(f"/api/startups/{sid}", json={"founders": "Jane Example", "source_url": "https://acme.example/about"}).json()
    assert patched["founders"] == "Jane Example"
    assert any(x["field"] == "founders" and x["evidence_status"] == "analyst_entered" for x in patched["citations"])
    assert c.put("/api/scoring/weights", json={"weights": {"market_opportunity": 10}}).status_code == 422
    score = c.post(f"/api/startups/{sid}/score-override", json={"factor": "product_differentiation", "score": 70,
                                                                  "note": "Proprietary dataset"}).json()
    assert next(f for f in score["factors"] if f["factor"] == "product_differentiation")["status"] == "analyst_override"
    assert c.get("/api/news", params={"startup_id": sid}).json()[0]["title"].startswith("Acme")
    assert {s["key"] for s in c.get("/api/sources/status").json()} >= {"hackernews", "sec_form_d"}
    assert c.get("/api/filters").json()["stages"]


def test_csv_round_trip_updates_instead_of_duplicating(settings):
    ingest(settings, [news("Acme Robotics raises $12M Series A", "https://a.example/1")])
    c = client_for(settings)
    csv_text = c.get("/api/export/startups.csv").text
    assert csv_text.splitlines()[0].startswith("id,external_id,name")
    result = c.post("/api/import/startups", files={"file": ("startups.csv", csv_text, "text/csv")}).json()
    assert result == {"created": 0, "updated": 1, "errors": []}
    new = "company_name,website,sector\nNew Co,https://newco.example,Fintech\n"
    assert c.post("/api/import/startups", files={"file": ("n.csv", new, "text/csv")}).json()["created"] == 1


def test_write_endpoints_require_token_when_configured(settings):
    settings.api_token = "secret"
    # client_for intentionally supplies a valid key, so use a bare client to
    # verify that the same endpoint rejects requests without the header.
    c = TestClient(create_app(settings))
    assert c.post("/api/discovery/run", json={}).status_code == 401
    assert c.get("/api/startups").status_code == 200  # reads stay open


def test_run_discovery_endpoint_starts_background_job(settings, monkeypatch):
    calls = []
    monkeypatch.setattr("vcdiscovery.api.app.run_discovery", lambda *a, **k: calls.append(k))
    r = client_for(settings).post("/api/discovery/run", json={"groups": ["funding"]})
    assert r.status_code == 202 and calls[0]["groups"] == ["funding"]


def test_csv_export_neutralizes_formula_strings(settings):
    from vcdiscovery.csv_io import _write

    output = _write([{"name": "=HYPERLINK(\"https://bad.example\")", "amount": -120}], ["name", "amount"])
    assert "'=HYPERLINK" in output
    assert ",-120" in output  # legitimate numeric values remain numeric


def test_tracker_import_is_idempotent(settings):
    with db.session_scope() as s:
        assert import_tracker_snapshot(s, TRACKER_JSON)["created"] == 20
    with db.session_scope() as s:
        assert import_tracker_snapshot(s, TRACKER_JSON)["updated"] == 20  # re-import updates, never duplicates
    with db.session_scope() as s:
        assert s.scalar(select(func.count(Startup.id))) == 20
        original = json.loads(TRACKER_JSON.read_text(encoding="utf-8"))
        assert s.scalar(select(func.count(FundingRound.id))) == len(original["rounds"])


def test_site_export_writes_website_data(settings, tmp_path):
    ingest(settings, [news("Acme Robotics raises $12M Series A led by Example Ventures", "https://a.example/1"),
                      news("Acme Robotics lays off 5% of staff", "https://a.example/2")])
    with db.session_scope() as s:
        refresh_scores(s, load_config(s, settings.load_json(settings.scoring_file)))
    with db.session_scope() as s:
        paths = write_site_data(s, settings, tmp_path)
    assert sorted(p.name for p in paths) == ["discovery.json", "news.json", "status.json"]
    discovery = json.loads((tmp_path / "discovery.json").read_text())
    acme = discovery["companies"][0]
    assert acme["name"] == "Acme Robotics"
    assert acme["funding_rounds"][0]["evidence_status"] == "reported"
    assert acme["score"]["thesis"] and "not investment recommendations" in discovery["disclaimer"]
    assert {f["key"] for f in discovery["factors"]} >= {"market_opportunity", "growth_momentum"}
    news_file = json.loads((tmp_path / "news.json").read_text())
    layoffs = next(a for a in news_file["articles"] if "lays off" in a["title"])
    assert "layoffs" in layoffs["event_types"] and layoffs["companies"] == ["Acme Robotics"]
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["counts"]["companies"] == 1
    assert {x["key"] for x in status["sources"]} >= {"hackernews", "sec_form_d", "techcrunch_funding"}
