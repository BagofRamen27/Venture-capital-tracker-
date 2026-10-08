"""RSS / Atom feeds published by news sites and press-release wires for public syndication.

Only the headline, link, publication date and a short summary (max 500 characters) are kept.
Full articles are never downloaded, so no paywall is touched.
"""
from __future__ import annotations

from datetime import datetime

import feedparser

from ..http import PoliteClient, SourceUnavailable
from ..text import short
from .base import NewsItem


class RSSSource:
    def __init__(self, key: str, name: str, url: str, publisher: str, group: str = "news",
                 source_type: str = "news", max_items: int = 100):
        self.key = key
        self.name = name
        self.url = url
        self.publisher = publisher
        self.group = group  # news | funding
        self.source_type = source_type  # news | press_release
        self.max_items = max_items

    def fetch(self, client: PoliteClient) -> list[NewsItem]:
        resp = client.get(self.url, headers={"Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"})
        return parse_feed(resp.content, self)


def _entry_time(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        value = entry.get(attr)
        if value:
            return datetime(*value[:6])  # feedparser already converts to UTC
    return None


def parse_feed(content: bytes | str, source: RSSSource) -> list[NewsItem]:
    feed = feedparser.parse(content)
    if not feed.entries:
        if feed.bozo:
            raise SourceUnavailable(f"{source.url} did not return a readable feed ({feed.bozo_exception})")
        return []
    items = []
    for entry in feed.entries[: source.max_items]:
        title = (entry.get("title") or "").strip()
        link = entry.get("link")
        if not title or not link:
            continue
        items.append(NewsItem(
            source_key=source.key,
            source_type=source.source_type,
            publisher=source.publisher,
            url=link,
            title=" ".join(title.split()),
            summary=short(entry.get("summary") or entry.get("description")),
            published_at=_entry_time(entry),
            category=source.group if source.source_type != "press_release" else "press_release",
        ))
    return items
