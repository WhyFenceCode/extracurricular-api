"""A polite HTTP client: honours robots.txt Disallow + Crawl-delay, identifies itself,
retries transient failures, and never hammers a host."""

from __future__ import annotations

import logging
import os
import time
import urllib.robotparser
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

DEFAULT_DELAY = 3.0  # seconds between requests to one host when robots.txt names none


def user_agent() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "local/extracurricular-api")
    return f"extracurricular-api/1.0 (+https://github.com/{repo}; student-run open data project)"


class RobotsDisallowed(Exception):
    pass


class PoliteClient:
    def __init__(self, timeout: float = 30.0, max_delay: float | None = None):
        self._client = httpx.Client(
            headers={"User-Agent": user_agent(), "Accept": "application/json, text/html;q=0.9"},
            timeout=timeout,
            follow_redirects=True,
        )
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last: dict[str, float] = {}
        # Only for local dev against fixtures; CI never sets this, so real crawl-delays apply.
        env_cap = os.environ.get("ECAPI_MAX_CRAWL_DELAY")
        self._max_delay = max_delay if max_delay is not None else (float(env_cap) if env_cap else None)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- robots ---------------------------------------------------------------
    def _robots_for(self, host: str, scheme: str) -> urllib.robotparser.RobotFileParser | None:
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            url = f"{scheme}://{host}/robots.txt"
            try:
                r = self._client.get(url)
                self._last[host] = time.monotonic()
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                else:
                    rp.parse([])  # no robots.txt -> everything allowed
                self._robots[host] = rp
            except httpx.HTTPError as e:
                log.warning("robots.txt fetch failed for %s: %s", host, e)
                self._robots[host] = None  # host unreachable; fetch will fail too
        return self._robots[host]

    def delay_for(self, host: str) -> float:
        rp = self._robots.get(host)
        d = None
        if rp is not None:
            d = rp.crawl_delay(user_agent()) or rp.crawl_delay("*")
        d = float(d) if d else DEFAULT_DELAY
        if self._max_delay is not None:
            d = min(d, self._max_delay)
        return d

    # -- fetch ----------------------------------------------------------------
    def get(self, url: str, *, retries: int = 3) -> httpx.Response:
        parts = urlsplit(url)
        host = parts.netloc
        rp = self._robots_for(host, parts.scheme)
        if rp is not None and not rp.can_fetch(user_agent(), url):
            raise RobotsDisallowed(url)

        last_err: Exception | None = None
        for attempt in range(retries):
            wait = self._last.get(host, 0) + self.delay_for(host) - time.monotonic()
            if wait > 0:
                log.info("waiting %.0fs (crawl-delay) before %s", wait, url)
                time.sleep(wait)
            try:
                r = self._client.get(url)
                self._last[host] = time.monotonic()
                if r.status_code >= 500 or r.status_code == 429:
                    last_err = httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
                    time.sleep(min(60, 5 * 2**attempt))
                    continue
                r.raise_for_status()
                return r
            except (httpx.TransportError,) as e:
                self._last[host] = time.monotonic()
                last_err = e
                time.sleep(min(60, 5 * 2**attempt))
        assert last_err is not None
        raise last_err
