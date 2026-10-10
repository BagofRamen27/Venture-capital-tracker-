"""Shared test fixtures. Tests never touch the internet: HTTP calls go to recorded fixtures."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from vcdiscovery import db
from vcdiscovery.config import Settings
from vcdiscovery.http import PoliteClient

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        sec_user_agent="Test Runner test@example.com",
        hn_min_points=20,
        http_min_interval_seconds=0,
        sec_min_interval_seconds=0,
        api_token="test-secret",
    )
    db.configure(s.resolved_database_url)
    db.init_db()
    return s


@pytest.fixture
def session(settings):
    s = db.SessionLocal()
    try:
        yield s
        s.commit()
    finally:
        s.close()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_client(routes: dict[str, object], calls: list | None = None) -> PoliteClient:
    """`routes` maps a URL prefix to a body (str/bytes), an int status, or a callable(request)->Response."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if calls is not None:
            calls.append(url)
        for prefix in sorted(routes, key=len, reverse=True):
            if url.startswith(prefix):
                value = routes[prefix]
                if callable(value):
                    return value(request)
                if isinstance(value, int):
                    return httpx.Response(value)
                return httpx.Response(200, content=value.encode() if isinstance(value, str) else value)
        return httpx.Response(404)

    return PoliteClient(user_agent="test", min_interval=0, transport=httpx.MockTransport(handler), sleep=lambda _s: None)
