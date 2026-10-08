"""Hacker News via the free, keyless Algolia HN Search API (https://hn.algolia.com/api).

Collects "Show HN" posts (product launches) and "Launch HN" posts (usually Y Combinator
companies, with the batch in the title). Only titles, links and public point/comment counts
are stored.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..http import PoliteClient
from .base import NewsItem

API = "https://hn.algolia.com/api/v1/search_by_date"


class HackerNewsSource:
    group = "community"

    def __init__(self, key: str = "hackernews", name: str = "Hacker News (Show HN / Launch HN)",
                 lookback_hours: int = 48, min_points: int = 0, max_pages: int = 3):
        self.key = key
        self.name = name
        self.lookback_hours = lookback_hours
        self.min_points = min_points
        self.max_pages = max_pages

    def _query(self, client: PoliteClient, params: dict) -> list[dict]:
        hits: list[dict] = []
        for page in range(self.max_pages):
            resp = client.get(API, params={**params, "page": page, "hitsPerPage": 100})
            data = resp.json()
            hits.extend(data.get("hits", []))
            if page + 1 >= int(data.get("nbPages", 1)):
                break
        return hits

    def fetch(self, client: PoliteClient) -> list[NewsItem]:
        since = int((datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)).timestamp())
        numeric = f"created_at_i>{since},points>={self.min_points}"
        hits = self._query(client, {"tags": "show_hn", "numericFilters": numeric})
        hits += self._query(client, {
            "query": "Launch HN", "tags": "story", "restrictSearchableAttributes": "title", "numericFilters": numeric,
        })
        return parse_hits(hits, self.key)


def parse_hits(hits: list[dict], source_key: str = "hackernews") -> list[NewsItem]:
    items: dict[str, NewsItem] = {}
    for h in hits:
        title = (h.get("title") or "").strip()
        if not title.lower().startswith(("show hn", "launch hn")):
            continue
        object_id = str(h.get("objectID"))
        discussion = f"https://news.ycombinator.com/item?id={object_id}"
        created = h.get("created_at_i")
        items[object_id] = NewsItem(
            source_key=source_key,
            source_type="community",
            publisher="Hacker News",
            url=h.get("url") or discussion,
            title=title,
            summary=(h.get("story_text") or None),
            published_at=datetime.fromtimestamp(created, timezone.utc).replace(tzinfo=None) if created else None,
            community_metrics={
                "points": h.get("points") or 0,
                "comments": h.get("num_comments") or 0,
                "discussion_url": discussion,
                "hn_id": object_id,
            },
            category="community",
        )
    return list(items.values())
