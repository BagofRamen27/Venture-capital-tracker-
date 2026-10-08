"""Source connectors and the registry that builds them from `config/sources.json`."""
from __future__ import annotations

from ..config import Settings
from .hackernews import HackerNewsSource
from .rss import RSSSource
from .sec_formd import SecFormDSource

GROUPS = ("news", "funding", "community", "regulatory")


def load_source_configs(settings: Settings) -> list[dict]:
    return settings.load_json(settings.sources_file)["sources"]


def build_sources(settings: Settings, keys: list[str] | None = None, groups: list[str] | None = None,
                  include_disabled: bool = False) -> tuple[list, list[dict]]:
    """Return (sources_to_run, skipped) where skipped lists {key, reason}."""
    sources, skipped = [], []
    for cfg in load_source_configs(settings):
        key = cfg["key"]
        if keys and key not in keys:
            continue
        if groups and cfg["group"] not in groups:
            continue
        if not cfg.get("enabled", False) and not include_disabled and not keys:
            skipped.append({"key": key, "reason": cfg.get("disabled_reason", "Disabled in config/sources.json")})
            continue
        kind = cfg["type"]
        if kind == "rss":
            sources.append(RSSSource(key=key, name=cfg["name"], url=cfg["url"], publisher=cfg["publisher"],
                                     group=cfg["group"], source_type=cfg.get("source_type", "news")))
        elif kind == "hackernews":
            sources.append(HackerNewsSource(key=key, name=cfg["name"], lookback_hours=settings.hn_lookback_hours,
                                            min_points=settings.hn_min_points))
        elif kind == "sec_form_d":
            if not settings.sec_user_agent.strip() or "@" not in settings.sec_user_agent:
                skipped.append({"key": key, "reason": "Set VCD_SEC_USER_AGENT to 'Your Name your@email' (SEC requirement)"})
                continue
            sources.append(SecFormDSource(key=key, name=cfg["name"], lookback_days=settings.sec_lookback_days,
                                          max_filings=settings.sec_max_filings_per_run))
        else:
            skipped.append({"key": key, "reason": f"Unknown source type '{kind}'"})
    return sources, skipped
