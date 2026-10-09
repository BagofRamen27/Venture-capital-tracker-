"""Source connectors and the registry that builds them from `config/sources.json`."""
from __future__ import annotations

from ..config import Settings
from .hackernews import HackerNewsSource
from .reddit import RedditSource
from .rss import RSSSource
from .sec_formd import SecFormDSource
from .youtube import YouTubeSearchSource

GROUPS = ("news", "funding", "community", "video", "regulatory")


def load_source_configs(settings: Settings) -> list[dict]:
    return settings.load_json(settings.sources_file)["sources"]


def configuration_problem(cfg: dict, settings: Settings) -> str | None:
    """Why an enabled source cannot run yet (missing credentials), or None."""
    if cfg["type"] == "sec_form_d" and (not settings.sec_user_agent.strip() or "@" not in settings.sec_user_agent):
        return "Set VCD_SEC_USER_AGENT to 'Your Name your@email' (SEC requirement)"
    if cfg["type"] == "reddit" and not (settings.reddit_client_id and settings.reddit_client_secret and settings.reddit_username):
        return ("Waiting for Reddit API credentials: add the REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET and "
                "REDDIT_USERNAME repository secrets (see README)")
    if cfg["type"] == "youtube_search" and not settings.youtube_api_key:
        return "Waiting for a YouTube Data API key: add the YOUTUBE_API_KEY repository secret (see README)"
    return None


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
        problem = configuration_problem(cfg, settings)
        if problem:
            skipped.append({"key": key, "reason": problem})
            continue
        if kind == "rss":
            sources.append(RSSSource(key=key, name=cfg["name"], url=cfg["url"], publisher=cfg["publisher"],
                                     group=cfg["group"], source_type=cfg.get("source_type", "news")))
        elif kind == "hackernews":
            sources.append(HackerNewsSource(key=key, name=cfg["name"], lookback_hours=settings.hn_lookback_hours,
                                            min_points=settings.hn_min_points))
        elif kind == "wikidata":
            continue  # enrichment, not discovery: runs in `python -m vcdiscovery.cli enrich`
        elif kind == "reddit":
            sources.append(RedditSource(key=key, name=cfg["name"], subreddits=cfg["subreddits"],
                                        client_id=settings.reddit_client_id, client_secret=settings.reddit_client_secret,
                                        username=settings.reddit_username, per_subreddit=settings.reddit_posts_per_subreddit,
                                        min_score=settings.reddit_min_score))
        elif kind == "youtube_search":
            sources.append(YouTubeSearchSource(key=key, name=cfg["name"], queries=cfg["queries"],
                                               api_key=settings.youtube_api_key,
                                               lookback_hours=settings.youtube_lookback_hours,
                                               results_per_query=settings.youtube_results_per_query))
        elif kind == "sec_form_d":
            sources.append(SecFormDSource(key=key, name=cfg["name"], lookback_days=settings.sec_lookback_days,
                                          max_filings=settings.sec_max_filings_per_run))
        else:
            skipped.append({"key": key, "reason": f"Unknown source type '{kind}'"})
    return sources, skipped
