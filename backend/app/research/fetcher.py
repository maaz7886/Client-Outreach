"""Polite HTTP fetcher: honors robots.txt, rate-limits per domain, retries
with backoff, identifies itself, and caps response size. Every page the
system ever reads from a college website goes through this class."""

import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings

MAX_BYTES = 2_000_000  # don't slurp 50 MB brochures
RETRY_STATUSES = {429, 500, 502, 503, 504}


class FetchBlocked(Exception):
    """robots.txt disallows this URL — caller must skip, never work around."""


class FetchFailed(Exception):
    """Transient or permanent fetch failure after retries."""


class PoliteFetcher:
    def __init__(
        self,
        *,
        delay_seconds: float | None = None,
        user_agent: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
        max_retries: int = 3,
    ):
        settings = get_settings()
        self.delay = settings.crawl_delay_seconds if delay_seconds is None else delay_seconds
        self.user_agent = user_agent or settings.crawl_user_agent
        self._sleep = sleep
        self._max_retries = max_retries
        self._client = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
            transport=transport,
        )
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_fetch: dict[str, float] = {}

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = self._client.get(origin + "/robots.txt")
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.parse([])  # no robots.txt -> everything allowed
            except httpx.HTTPError:
                rp.parse([])
            self._robots[origin] = rp
        return self._robots[origin]

    def _respect_delay(self, url: str) -> None:
        domain = urlparse(url).netloc
        last = self._last_fetch.get(domain)
        if last is not None:
            wait = self.delay - (time.monotonic() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_fetch[domain] = time.monotonic()

    def get(self, url: str) -> httpx.Response:
        if not self._robots_for(url).can_fetch(self.user_agent, url):
            raise FetchBlocked(f"robots.txt disallows {url}")

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            self._respect_delay(url)
            try:
                resp = self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = exc
                self._sleep(2**attempt)
                continue
            if resp.status_code in RETRY_STATUSES:
                last_error = FetchFailed(f"HTTP {resp.status_code} for {url}")
                self._sleep(2**attempt)
                continue
            if resp.status_code >= 400:
                raise FetchFailed(f"HTTP {resp.status_code} for {url}")
            if len(resp.content) > MAX_BYTES:
                raise FetchFailed(f"Response too large ({len(resp.content)} bytes) for {url}")
            return resp
        raise FetchFailed(f"Gave up on {url} after {self._max_retries} attempts: {last_error}")
