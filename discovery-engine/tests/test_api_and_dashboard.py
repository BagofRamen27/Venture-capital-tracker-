import json

from fastapi.testclient import TestClient

from tests.conftest import REPO_ROOT
from tests.test_pipeline import ingest, news
from vcdiscovery import db
from vcdiscovery.api import create_app
from vcdiscovery.csv_io import import_tracker_snapshot
from vcdiscovery.dashboard_export import build_snapshot

TRACKER_JSON = REPO_ROOT / "vc-investment-tracker-web" / "dist" / "data" / "demo-data.json"


def client_for(settings):
    return TestClient(create_app(settings))


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
    c = client_for(settings)
    assert c.post("/api/discovery/run", json={}).status_code == 401
    assert c.get("/api/startups").status_code == 200  # reads stay open


def test_run_discovery_endpoint_starts_background_job(settings, monkeypatch):
    calls = []
    monkeypatch.setattr("vcdiscovery.api.app.run_discovery", lambda *a, **k: calls.append(k))
    r = client_for(settings).post("/api/discovery/run", json={"groups": ["funding"]})
    assert r.status_code == 202 and calls[0]["groups"] == ["funding"]


def test_tracker_import_round_trips_into_dashboard_snapshot(settings):
    original = json.loads(TRACKER_JSON.read_text(encoding="utf-8"))
    with db.session_scope() as s:
        assert import_tracker_snapshot(s, TRACKER_JSON)["created"] == 20
    with db.session_scope() as s:
        assert import_tracker_snapshot(s, TRACKER_JSON)["updated"] == 20  # re-import updates, never duplicates
    ingest(settings, [news("Acme Robotics raises $12M Series A", "https://a.example/1")])
    with db.session_scope() as s:
        snap = build_snapshot(s, settings)
    assert snap["settings"] == original["settings"]
    by_id = {r["startup_id"]: r for r in snap["startups"]}
    for row in original["startups"]:
        exported = by_id[row["startup_id"]]
        assert {k: exported[k] for k in row} == row  # every original field unchanged
    assert len([r for r in snap["rounds"] if r["round_id"].startswith("RND-")]) == len(original["rounds"])
    assert len([c for c in snap["claims"] if c["claim_id"].startswith("CLM-")]) == len(original["claims"])
    new = next(r for r in snap["startups"] if r["company_name"] == "Acme Robotics")
    assert set(original["startups"][0]) <= set(new)  # same keys as the dashboard expects
    acme_rounds = [r for r in snap["rounds"] if r["startup_id"] == new["startup_id"]]
    assert acme_rounds[0]["is_current_round"] == "Yes" and acme_rounds[0]["capital_raised_usd"] == "12000000"
    for key in ("pipeline", "scores"):
        assert len(snap[key]) == 21
