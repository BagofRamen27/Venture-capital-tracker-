"""YouTube search through the official YouTube Data API v3 (free API key, read-only).

Setup: create a free API key in Google Cloud (enable "YouTube Data API v3"; no billing needed) and provide
VCD_YOUTUBE_API_KEY. Each search costs 100 of the 10,000 free daily quota units, so a few queries a day is
well within the free limit.

What is stored, to respect the YouTube API Services Terms and Developer Policies:
* only a video's title, link, channel name, publication date and a short description;
* videos are never downloaded and captions are never read;
* everything stored from the API is deleted after 30 days (the policies' storage limit).

Search results can come from any uploader, so they never create new companies; they are linked to companies
we already track when the title names the company. Videos from chosen publisher channels are read through
their public RSS feeds instead (plain `rss` sources in config/sources.json, no key needed).
"""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

from ..http import PoliteClient
from ..text import short
from .base import NewsItem

API = "https://www.googleapis.com/youtube/v3/search"
WATCH = "https://www.youtube.com/watch?v="


class YouTubeSearchSource:
    group = "video"

    def __init__(self, key: str, name: str, queries: list[str], api_key: str, lookback_hours: int = 48,
                 results_per_query: int = 25):
        self.key = key
        self.name = name
        self.queries = queries
        self.api_key = api_key
        self.lookback_hours = lookback_hours
        self.results_per_query = results_per_query

    def fetch(self, client: PoliteClient) -> list[NewsItem]:
        since = (datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # The key goes in a header, not the URL, so it can never appear in logged error messages.
        headers = {"X-Goog-Api-Key": self.api_key, "Accept": "application/json"}
        items: dict[str, NewsItem] = {}
        for query in self.queries:
            data = client.get(API, params={"part": "snippet", "type": "video", "q": query, "order": "date",
                                           "publishedAfter": since, "maxResults": str(self.results_per_query),
                                           "relevanceLanguage": "en", "safeSearch": "strict"}, headers=headers).json()
            for result in data.get("items", []):
                item = to_item(result, self.key)
                if item:
                    items[item.community_metrics["youtube_id"]] = item
        return list(items.values())


def to_item(result: dict, source_key: str) -> NewsItem | None:
    """Convert one search result into a NewsItem, or None if it is not a usable video."""
    video_id = (result.get("id") or {}).get("videoId")
    snippet = result.get("snippet") or {}
    title = html.unescape(snippet.get("title") or "").strip()  # the API returns HTML-escaped text
    if not video_id or not title or snippet.get("liveBroadcastContent") == "upcoming":
        return None
    published = snippet.get("publishedAt")
    channel = html.unescape(snippet.get("channelTitle") or "").strip() or "unknown channel"
    return NewsItem(
        source_key=source_key, source_type="community", publisher=f"YouTube: {channel}", url=WATCH + video_id,
        title=" ".join(title.split()), summary=short(html.unescape(snippet.get("description") or "")),
        published_at=datetime.fromisoformat(published.replace("Z", "+00:00")).replace(tzinfo=None) if published else None,
        community_metrics={"youtube_id": video_id, "channel": channel, "discussion_url": WATCH + video_id},
        category="video",
    )
