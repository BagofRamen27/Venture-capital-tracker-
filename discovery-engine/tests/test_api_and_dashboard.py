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


def test_sanitize_job_error_classification_and_leak_prevention():
    from vcdiscovery.api.serializers import sanitize_job_error

    # None and empty inputs
    assert sanitize_job_error(None) is None
    assert sanitize_job_error("") is None
    assert sanitize_job_error("   \n\t  ") is None

    # HTTP status code extraction and secret redaction
    http_500_leak = (
        "httpx.HTTPStatusError: Server error '500 Internal Server Error' for url "
        "'https://api.example.com/v1/feed?token=FAKE_TOKEN_DO_NOT_USE_500'"
    )
    s_500 = sanitize_job_error(http_500_leak)
    assert s_500 == "HTTP 500"
    assert "FAKE_TOKEN_DO_NOT_USE_500" not in s_500
    assert "api.example.com" not in s_500

    http_404_leak = (
        "Client error '404 Not Found' for url 'https://internal.host/api?key=FAKE_TOKEN_DO_NOT_USE_404'"
    )
    s_404 = sanitize_job_error(http_404_leak)
    assert s_404 == "HTTP 404"
    assert "FAKE_TOKEN_DO_NOT_USE_404" not in s_404

    http_502_status = "Failed upstream with status code: 502 (bad gateway)"
    assert sanitize_job_error(http_502_status) == "HTTP 502"

    http_429_rate = (
        "httpx.HTTPStatusError: Client error '429 Too Many Requests' for url "
        "'https://api.example.com/v1/search?token=FAKE_TOKEN_DO_NOT_USE_429'"
    )
    s_429 = sanitize_job_error(http_429_rate)
    assert s_429 == "Rate limit exceeded (HTTP 429)"
    assert "FAKE_TOKEN_DO_NOT_USE_429" not in s_429

    # Batch item ingestion failures
    item_fail_leak = (
        "7 item(s) failed. First: https://rss.example.com/feed?auth=FAKE_TOKEN_DO_NOT_USE_ITEM: "
        "ValueError: invalid line format at /var/secrets/schema.json"
    )
    s_items = sanitize_job_error(item_fail_leak)
    assert s_items == "7 item(s) failed during ingestion"
    assert "FAKE_TOKEN_DO_NOT_USE_ITEM" not in s_items
    assert "rss.example.com" not in s_items
    assert "/var/secrets" not in s_items

    # Concurrency lock and adversarial appended secret text
    lock_injection = "Already running (lock held) token=FAKE_TOKEN_DO_NOT_USE_LOCK at /tmp/lock.pid"
    s_lock = sanitize_job_error(lock_injection)
    assert s_lock == "Already running (lock held)"
    assert "FAKE_TOKEN_DO_NOT_USE_LOCK" not in s_lock
    assert "/tmp/lock.pid" not in s_lock

    # Database connection error with synthetic credentials and IP/host
    db_leak = (
        "sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection to server at "
        "'db.internal.corp' (10.0.1.99), port 5432 failed: FATAL: password authentication failed "
        "for user 'FAKE_USER_DO_NOT_USE'"
    )
    s_db = sanitize_job_error(db_leak)
    assert s_db == "Database error"
    assert "db.internal.corp" not in s_db
    assert "10.0.1.99" not in s_db
    assert "FAKE_USER_DO_NOT_USE" not in s_db

    # Timeouts and network connection errors
    timeout_leak = "httpx.ConnectTimeout: timed out connecting to https://secret-api.internal:8443"
    s_timeout = sanitize_job_error(timeout_leak)
    assert s_timeout == "Request timeout"
    assert "secret-api.internal" not in s_timeout

    conn_leak = "httpx.ConnectError: [Errno 111] Connection refused by internal-host.lan:443"
    s_conn = sanitize_job_error(conn_leak)
    assert s_conn == "Connection failed"
    assert "internal-host.lan" not in s_conn

    # Parsing and data format errors
    parse_leak = "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)"
    assert sanitize_job_error(parse_leak) == "Data format error"

    # Rate limiting without status code
    rate_leak = "API rate limit reached for endpoint https://api.internal/v1"
    s_rate = sanitize_job_error(rate_leak)
    assert s_rate == "Rate limit exceeded"
    assert "api.internal" not in s_rate

    # Windows filesystem path failure
    win_path_leak = (
        "FileNotFoundError: [Errno 2] No such file or directory: "
        "'C:\\Users\\admin\\app_secrets\\FAKE_PATH_SECRET.key'"
    )
    s_win = sanitize_job_error(win_path_leak)
    assert s_win == "Job execution failed"
    assert "app_secrets" not in s_win
    assert "FAKE_PATH_SECRET" not in s_win
    assert "admin" not in s_win

    # POSIX filesystem path failure
    posix_path_leak = "PermissionError: [Errno 13] Permission denied: '/var/secrets/FAKE_POSIX_SECRET.pem'"
    s_posix = sanitize_job_error(posix_path_leak)
    assert s_posix == "Job execution failed"
    assert "/var/secrets" not in s_posix
    assert "FAKE_POSIX_SECRET" not in s_posix

    # Unknown exception format fails closed
    unknown_leak = "CustomInternalException: secret state corrupted: token=FAKE_UNKNOWN_TOKEN"
    s_unknown = sanitize_job_error(unknown_leak)
    assert s_unknown == "Job execution failed"
    assert "FAKE_UNKNOWN_TOKEN" not in s_unknown


def test_job_status_endpoints_redact_sensitive_errors(settings):
    from vcdiscovery.models import JobRun, utcnow

    with db.session_scope() as s:
        # Clear any prior jobs to ensure clean state
        for j in s.scalars(select(JobRun)).all():
            s.delete(j)
        s.commit()

        # Job 1: Failed with HTTP 500 error containing synthetic URL token
        s.add(JobRun(
            job_name="discovery", source_key="hackernews", trigger="manual",
            status="failed", started_at=utcnow(), finished_at=utcnow(),
            items_fetched=0, items_new=0, items_duplicate=0, startups_created=0,
            error_message=(
                "httpx.HTTPStatusError: Server error '500 Internal Server Error' for url "
                "'https://api.example.com/v1/hn?key=FAKE_TOKEN_API_JOBS_500'"
            ),
        ))
        # Job 2: Failed with Database connection credentials
        s.add(JobRun(
            job_name="score_refresh", source_key=None, trigger="scheduled",
            status="failed", started_at=utcnow(), finished_at=utcnow(),
            items_fetched=0, items_new=0, items_duplicate=0, startups_created=0,
            error_message=(
                "sqlalchemy.exc.OperationalError: connection to 'secret-db.internal.corp' failed "
                "for user 'FAKE_USER_DB_LEAK'"
            ),
        ))
        # Job 3: Partial with item count and URL token
        s.add(JobRun(
            job_name="discovery", source_key="sec_form_d", trigger="manual",
            status="partial", started_at=utcnow(), finished_at=utcnow(),
            items_fetched=10, items_new=8, items_duplicate=0, startups_created=2,
            error_message=(
                "2 item(s) failed. First: https://sec.example.com/filing?auth=FAKE_TOKEN_ITEM_LEAK: "
                "XMLParseError: invalid XML"
            ),
        ))
        # Job 4: Skipped with lock message and token injection
        s.add(JobRun(
            job_name="discovery", source_key="techcrunch_funding", trigger="scheduled",
            status="skipped", started_at=utcnow(), finished_at=utcnow(),
            items_fetched=0, items_new=0, items_duplicate=0, startups_created=0,
            error_message="Already running (lock held) token=FAKE_LOCK_AUTH_TOKEN",
        ))
        # Job 5: Success with None error
        s.add(JobRun(
            job_name="discovery", source_key="techcrunch_funding", trigger="manual",
            status="success", started_at=utcnow(), finished_at=utcnow(),
            items_fetched=5, items_new=3, items_duplicate=2, startups_created=1,
            error_message=None,
        ))
        s.commit()

    c = client_for(settings)

    # 1. Test GET /api/jobs
    res_jobs = c.get("/api/jobs")
    assert res_jobs.status_code == 200
    jobs_text = res_jobs.text

    # Strict negative assertions: secrets and sensitive hosts must never appear
    assert "FAKE_TOKEN_API_JOBS_500" not in jobs_text
    assert "api.example.com" not in jobs_text
    assert "secret-db.internal.corp" not in jobs_text
    assert "FAKE_USER_DB_LEAK" not in jobs_text
    assert "FAKE_TOKEN_ITEM_LEAK" not in jobs_text
    assert "FAKE_LOCK_AUTH_TOKEN" not in jobs_text

    jobs_data = res_jobs.json()
    assert len(jobs_data) == 5

    by_status = {j["status"]: j for j in jobs_data}
    assert "failed" in by_status and "partial" in by_status and "skipped" in by_status and "success" in by_status

    jobs_by_source = {j["source_key"]: j for j in jobs_data if j["source_key"]}
    assert jobs_by_source["hackernews"]["error"] == "HTTP 500"
    assert jobs_by_source["hackernews"]["status"] == "failed"

    assert jobs_by_source["sec_form_d"]["error"] == "2 item(s) failed during ingestion"
    assert jobs_by_source["sec_form_d"]["status"] == "partial"
    assert jobs_by_source["sec_form_d"]["items_new"] == 8

    # Job without source_key (score_refresh)
    score_job = next(j for j in jobs_data if j["job"] == "score_refresh")
    assert score_job["error"] == "Database error"
    assert score_job["status"] == "failed"

    skipped_job = next(j for j in jobs_data if j["status"] == "skipped")
    assert skipped_job["error"] == "Already running (lock held)"

    success_job = next(j for j in jobs_data if j["status"] == "success")
    assert success_job["error"] is None

    # 2. Test GET /api/sources/status
    res_sources = c.get("/api/sources/status")
    assert res_sources.status_code == 200
    sources_text = res_sources.text

    assert "FAKE_TOKEN_API_JOBS_500" not in sources_text
    assert "api.example.com" not in sources_text
    assert "secret-db.internal.corp" not in sources_text
    assert "FAKE_USER_DB_LEAK" not in sources_text
    assert "FAKE_TOKEN_ITEM_LEAK" not in sources_text
    assert "FAKE_LOCK_AUTH_TOKEN" not in sources_text

    sources_data = res_sources.json()
    hn_source = next(s for s in sources_data if s["key"] == "hackernews")
    assert hn_source["last_run"]["error"] == "HTTP 500"
    assert hn_source["last_run"]["status"] == "failed"

    sec_source = next(s for s in sources_data if s["key"] == "sec_form_d")
    assert sec_source["last_run"]["error"] == "2 item(s) failed during ingestion"
    assert sec_source["last_run"]["status"] == "partial"


def test_site_export_status_json_redacts_sensitive_errors(settings, tmp_path):
    from vcdiscovery.models import JobRun, utcnow

    with db.session_scope() as s:
        # Insert a failed JobRun for hackernews with synthetic token
        s.add(JobRun(
            job_name="discovery", source_key="hackernews", trigger="scheduled",
            status="failed", started_at=utcnow(), finished_at=utcnow(),
            items_fetched=0, items_new=0, items_duplicate=0, startups_created=0,
            error_message=(
                "httpx.HTTPStatusError: Server error '502 Bad Gateway' for url "
                "'https://hn.internal.host/api?token=FAKE_TOKEN_EXPORT_502'"
            ),
        ))
        s.commit()

    with db.session_scope() as s:
        paths = write_site_data(s, settings, tmp_path)

    status_file = tmp_path / "status.json"
    assert status_file.exists()
    status_text = status_file.read_text(encoding="utf-8")

    # Strict negative assertions: secret token and internal host must not be present
    assert "FAKE_TOKEN_EXPORT_502" not in status_text
    assert "hn.internal.host" not in status_text

    status_data = json.loads(status_text)

    # Verify sources[].last_error
    hn_src = next(x for x in status_data["sources"] if x["key"] == "hackernews")
    assert hn_src["last_error"] == "HTTP 502"
    assert hn_src["health"] == "failed"

    # Verify recent_jobs[].error
    hn_job = next(j for j in status_data["recent_jobs"] if j["source_key"] == "hackernews")
    assert hn_job["error"] == "HTTP 502"
    assert hn_job["status"] == "failed"
