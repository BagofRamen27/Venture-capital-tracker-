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
    health = c.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["database"] == "sqlite"
    assert health["startups"] == 2
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


def test_database_backend_utility():
    from vcdiscovery.api.app import database_backend

    assert database_backend("sqlite:///./data/vc_discovery.db") == "sqlite"
    assert database_backend("sqlite:///:memory:") == "sqlite"
    assert database_backend("sqlite:////abs/path/db.sqlite") == "sqlite"
    assert database_backend("postgresql://user:pass@host:5432/vcdb") == "postgresql"
    assert database_backend("postgresql+psycopg://user:pass@host:5432/vcdb") == "postgresql"
    assert database_backend("postgresql+asyncpg://user:pass@host:5432/vcdb") == "postgresql"
    assert database_backend("mysql+pymysql://user:pass@host:3306/vcdb") == "mysql"
    # Malformed, empty, or non-URI inputs must fail closed to 'unknown' without leaking
    assert database_backend("") == "unknown"
    assert database_backend(None) == "unknown"
    assert database_backend("not-a-valid-database-url") == "unknown"
    assert database_backend("://corrupted") == "unknown"


def test_health_endpoint_redacts_credentials_for_network_database(monkeypatch):
    from unittest.mock import MagicMock
    from vcdiscovery.config import Settings

    synthetic_user = "sec_analyst_user"
    synthetic_pass = "super_secret_p@ss#123"
    synthetic_host = "private-db.internal.cloud"
    synthetic_port = "5432"
    synthetic_dbname = "confidential_vc_discovery"

    secret_url = (
        f"postgresql+psycopg://{synthetic_user}:{synthetic_pass}@"
        f"{synthetic_host}:{synthetic_port}/{synthetic_dbname}?sslmode=require"
    )
    custom_settings = Settings(_env_file=None, database_url=secret_url)

    # Mock configure and init_db in app.py so create_app does not attempt a real connection
    monkeypatch.setattr("vcdiscovery.api.app.configure", lambda *a, **k: None)
    monkeypatch.setattr("vcdiscovery.api.app.init_db", lambda *a, **k: None)

    app = create_app(custom_settings)
    mock_session = MagicMock()
    mock_session.scalar.return_value = 5
    app.dependency_overrides[db.get_db] = lambda: mock_session

    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "postgresql"
    assert data["startups"] == 5

    # Strictly assert sensitive connection components are completely absent from serialized response
    raw_response = response.text
    assert synthetic_user not in raw_response
    assert synthetic_pass not in raw_response
    assert synthetic_host not in raw_response
    assert synthetic_port not in raw_response
    assert synthetic_dbname not in raw_response
    assert "sslmode" not in raw_response


def test_health_endpoint_sqlite_path_redaction(settings):
    c = client_for(settings)
    response = c.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["database"] == "sqlite"

    # Strictly assert that the filesystem path of the SQLite database does not leak
    raw_text = response.text
    assert ".db" not in raw_text
    assert "test.db" not in raw_text
    assert str(settings.resolve_path("data")) not in raw_text


def test_health_endpoint_malformed_url_safety(monkeypatch):
    from unittest.mock import MagicMock
    from vcdiscovery.config import Settings

    malformed_secret_url = "://hidden_user:hidden_secret@leak_host/leak_path"
    custom_settings = Settings(_env_file=None, database_url=malformed_secret_url)

    monkeypatch.setattr("vcdiscovery.api.app.configure", lambda *a, **k: None)
    monkeypatch.setattr("vcdiscovery.api.app.init_db", lambda *a, **k: None)

    app = create_app(custom_settings)
    mock_session = MagicMock()
    mock_session.scalar.return_value = 0
    app.dependency_overrides[db.get_db] = lambda: mock_session

    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["database"] == "unknown"

    raw_response = response.text
    assert "hidden_secret" not in raw_response
    assert "hidden_user" not in raw_response
    assert "leak_host" not in raw_response
    assert "leak_path" not in raw_response
