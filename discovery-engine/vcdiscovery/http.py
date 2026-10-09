"""A polite HTTP client: identifies itself, waits between calls to the same site, retries
temporary errors, and honours `Retry-After`. It never tries to get around blocks or CAPTCHAs."""
from __future__ import annotations

import time
from urllib.parse import urlsplit

import httpx


class SourceUnavailable(Exception):
    """Raised when a source cannot be reached or refuses access."""


class PoliteClient:
    def __init__(
        self,
        user_agent: str,
        timeout: float = 20.0,
        min_interval: float = 1.0,
        host_intervals: dict[str, float] | None = None,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 3,
        sleep=time.sleep,
    ):
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self.min_interval = min_interval
        self.host_intervals = host_intervals or {}
        self.max_retries = max_retries
        self._last_call: dict[str, float] = {}
        self._sleep = sleep

    def _wait_turn(self, host: str) -> None:
        interval = self.host_intervals.get(host, self.min_interval)
        elapsed = time.monotonic() - self._last_call.get(host, 0.0)
        if elapsed < interval:
            self._sleep(interval - elapsed)
        self._last_call[host] = time.monotonic()

    def get(
        self, url: str, params: dict | None = None, headers: dict | None = None, ok_statuses: tuple[int, ...] = ()
    ) -> httpx.Response:
        """GET with retries. Statuses in `ok_statuses` (e.g. 404) are returned instead of raised."""
        return self._request("GET", url, params=params, headers=headers, ok_statuses=ok_statuses)

    def post(self, url: str, data: dict | None = None, headers: dict | None = None,
             auth: tuple[str, str] | None = None) -> httpx.Response:
        """POST with the same politeness and retry rules (used for OAuth token requests)."""
        return self._request("POST", url, data=data, headers=headers, auth=auth)

    def _request(self, method: str, url: str, ok_statuses: tuple[int, ...] = (), **kwargs) -> httpx.Response:
        host = urlsplit(url).hostname or ""
        last_error: str = ""
        for attempt in range(self.max_retries + 1):
            self._wait_turn(host)
            try:
                resp = self._client.request(method, url, **{k: v for k, v in kwargs.items() if v is not None})
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._sleep(min(2 ** attempt, 30))
                continue
            if resp.status_code in ok_statuses:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                retry_after = resp.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1)
                last_error = f"HTTP {resp.status_code}"
                self._sleep(min(delay, 60))
                continue
            if resp.status_code in (401, 403):
                raise SourceUnavailable(f"{url} refused access (HTTP {resp.status_code}). Check the source's access rules.")
            if resp.status_code >= 400:
                raise SourceUnavailable(f"{url} returned HTTP {resp.status_code}")
            return resp
        raise SourceUnavailable(f"{url} unavailable after {self.max_retries + 1} attempts ({last_error})")

    def pause(self, seconds: float) -> None:
        """Wait when a source asks us to (for example Wikidata's maxlag)."""
        self._sleep(seconds)

    def close(self) -> None:
        self._client.close()
