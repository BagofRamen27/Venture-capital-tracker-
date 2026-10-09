"""Application settings, loaded from environment variables or a `.env` file.

Every setting can be overridden with an environment variable that starts with `VCD_`,
for example `VCD_DATABASE_URL=sqlite:///./data/other.db`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import unicodedata

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Folder that contains `vcdiscovery/`, `config/`, `data/` (the discovery-engine folder).
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_prefix="VCD_", extra="ignore"
    )

    database_url: str = "sqlite:///./data/vc_discovery.db"

    # SEC requires every automated request to identify the requester:
    # "Your Name your.email@example.com". The SEC source is skipped until this is set.
    sec_user_agent: str = ""
    # Generic identifier sent to every other website.
    http_user_agent: str = (
        "VCDiscoveryEngine/0.1 (open-source startup research; https://github.com/BagofRamen27/Venture-capital-tracker-)"
    )
    http_timeout_seconds: float = 20.0
    http_min_interval_seconds: float = 1.0  # minimum pause between calls to the same website
    sec_min_interval_seconds: float = 0.25  # SEC allows up to 10 requests/second; we stay well below

    sources_file: str = "config/sources.json"
    scoring_file: str = "config/scoring.json"

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Optional shared secret. When set, every write request needs the header `X-API-Key`.
    api_token: str = ""

    enable_scheduler: bool = False
    hn_min_points: int = 20
    hn_lookback_hours: int = 48
    sec_lookback_days: int = 3
    sec_max_filings_per_run: int = 150
    stale_after_days: int = 180
    job_lock_minutes: int = 60
    wikidata_max_lookups: int = 60  # companies looked up per run (about 2-3 requests each)

    # Reddit Data API (register a "script" app at https://www.reddit.com/prefs/apps). Left empty = Reddit is skipped.
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_username: str = ""
    reddit_min_score: int = 5
    reddit_posts_per_subreddit: int = 50

    @field_validator("sec_user_agent", "http_user_agent", mode="before")
    @classmethod
    def _clean_header(cls, value):
        """Pasted values often carry line breaks, tabs or accented letters, which are not allowed in an
        HTTP header. Collapse whitespace and convert to plain ASCII ('José' -> 'Jose')."""
        if not isinstance(value, str):
            return value
        ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        return " ".join(ascii_text.split())

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def resolved_database_url(self) -> str:
        """Relative SQLite paths are resolved against the discovery-engine folder."""
        prefix = "sqlite:///"
        url = self.database_url
        if url.startswith(prefix) and not url.startswith(prefix + "/") and ":memory:" not in url:
            path = self.resolve_path(url[len(prefix):])
            path.parent.mkdir(parents=True, exist_ok=True)
            return prefix + str(path)
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def load_json(self, value: str) -> dict:
        with open(self.resolve_path(value), encoding="utf-8") as fh:
            return json.load(fh)


@lru_cache
def get_settings() -> Settings:
    return Settings()
