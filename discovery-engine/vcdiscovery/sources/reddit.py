"""Reddit through the official Data API (OAuth, read-only, application-only access).

Setup: register a "script" app at https://www.reddit.com/prefs/apps (Reddit may ask you to request
API access first) and provide VCD_REDDIT_CLIENT_ID, VCD_REDDIT_CLIENT_SECRET and VCD_REDDIT_USERNAME.

What is stored, to respect Reddit's Data API Terms:
* only a post's title, link, score, comment count and subreddit; never the post body or the author;
* posts later deleted or removed on Reddit are found on the next run and deleted from our database.

Reddit posts never create new companies (too noisy); they are linked to companies we already track
when the post links to the company's website or names it, and count towards community attention.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..http import PoliteClient, SourceUnavailable
from .base import NewsItem

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"


class RedditSource:
    group = "community"

    def __init__(self, key: str, name: str, subreddits: list[str], client_id: str, client_secret: str,
                 username: str, per_subreddit: int = 50, min_score: int = 5):
        self.key = key
        self.name = name
        self.subreddits = subreddits
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = f"python:venturescout:0.1 (by /u/{username})"  # format Reddit asks for
        self.per_subreddit = per_subreddit
        self.min_score = min_score
        # Filled by the pipeline before fetch: Reddit ids ("t3_abc") of posts we stored earlier.
        self.stored_ids: list[str] = []
        # Set by fetch: stored posts that were deleted or removed on Reddit since we saw them.
        self.removed_ids: list[str] = []

    def _token(self, client: PoliteClient) -> str:
        resp = client.post(TOKEN_URL, data={"grant_type": "client_credentials"},
                           auth=(self.client_id, self.client_secret), headers={"User-Agent": self.user_agent})
        token = resp.json().get("access_token")
        if not token:
            raise SourceUnavailable(f"Reddit did not issue an access token ({resp.json().get('error', 'no reason given')})")
        return token

    def fetch(self, client: PoliteClient) -> list[NewsItem]:
        headers = {"Authorization": f"bearer {self._token(client)}", "User-Agent": self.user_agent}
        items: dict[str, NewsItem] = {}
        for sub in self.subreddits:
            data = client.get(f"{API}/r/{sub}/new", params={"limit": str(self.per_subreddit), "raw_json": "1"},
                              headers=headers).json()
            for child in data.get("data", {}).get("children", []):
                item = to_item(child.get("data", {}), self.key, self.min_score)
                if item:
                    items[item.community_metrics["reddit_id"]] = item
        self.removed_ids = self._removed(client, headers)
        return list(items.values())

    def _removed(self, client: PoliteClient, headers: dict) -> list[str]:
        removed = []
        for start in range(0, len(self.stored_ids), 100):
            batch = self.stored_ids[start:start + 100]
            data = client.get(f"{API}/api/info", params={"id": ",".join(batch), "raw_json": "1"}, headers=headers).json()
            alive = {c["data"]["name"] for c in data.get("data", {}).get("children", []) if not is_gone(c.get("data", {}))}
            removed.extend(i for i in batch if i not in alive)
        return removed


def is_gone(post: dict) -> bool:
    return bool(post.get("removed_by_category")) or post.get("author") == "[deleted]" or post.get("selftext") == "[removed]"


def to_item(post: dict, source_key: str, min_score: int) -> NewsItem | None:
    """Convert one Reddit post into a NewsItem, or None if it should be skipped."""
    if not post.get("name") or not post.get("title") or post.get("over_18") or post.get("stickied") or is_gone(post):
        return None
    if (post.get("score") or 0) < min_score:
        return None
    discussion = "https://www.reddit.com" + post.get("permalink", "")
    created = post.get("created_utc")
    return NewsItem(
        source_key=source_key, source_type="community", publisher=f"Reddit r/{post.get('subreddit', '')}",
        url=discussion if post.get("is_self") else (post.get("url") or discussion),
        title=" ".join(post["title"].split()), summary=None,  # the post body is never stored
        published_at=datetime.fromtimestamp(created, timezone.utc).replace(tzinfo=None) if created else None,
        community_metrics={"points": post.get("score") or 0, "comments": post.get("num_comments") or 0,
                           "discussion_url": discussion, "reddit_id": post["name"], "subreddit": post.get("subreddit")},
        category="community",
    )
