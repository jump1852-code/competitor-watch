"""A polite HTTP fetcher: robots.txt aware, rate limited, with retries."""

from __future__ import annotations

import logging
import time
import urllib.robotparser
from collections.abc import Callable
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Settings

log = logging.getLogger(__name__)


class RobotsDisallowed(RuntimeError):
    """Raised when robots.txt forbids fetching a URL."""


class PoliteFetcher:
    """Fetch pages while respecting robots.txt and a per-host minimum delay."""

    def __init__(
        self,
        settings: Settings,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.session = session or self._build_session(settings)
        self._sleep = sleep
        self._clock = clock
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    @staticmethod
    def _build_session(settings: Settings) -> requests.Session:
        retry = Retry(
            total=settings.max_retries,
            backoff_factor=settings.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
            respect_retry_after_header=True,
        )
        session = requests.Session()
        session.headers.update({"User-Agent": settings.user_agent, "Accept-Language": "en"})
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # -- robots.txt -------------------------------------------------------
    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                resp = self.session.get(f"{origin}/robots.txt", timeout=self.settings.timeout_seconds)
                if resp.status_code >= 400:
                    # No robots.txt (or not accessible) => everything allowed per RFC 9309.
                    self._robots[origin] = None
                else:
                    parser.parse(resp.text.splitlines())
                    self._robots[origin] = parser
            except requests.RequestException as exc:
                log.warning("could not read robots.txt for %s (%s); assuming allowed", origin, exc)
                self._robots[origin] = None
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        parser = self._robots_for(url)
        return True if parser is None else parser.can_fetch(self.settings.user_agent, url)

    # -- rate limiting ----------------------------------------------------
    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        last = self._last_hit.get(host)
        if last is not None:
            wait = self.settings.min_delay_seconds - (self._clock() - last)
            if wait > 0:
                log.debug("throttling %s for %.2fs", host, wait)
                self._sleep(wait)
        self._last_hit[host] = self._clock()

    # -- public API -------------------------------------------------------
    def get(self, url: str) -> str:
        if not self.allowed(url):
            raise RobotsDisallowed(url)
        self._throttle(url)
        log.info("GET %s", url)
        resp = self.session.get(url, timeout=self.settings.timeout_seconds)
        resp.raise_for_status()
        resp.encoding = resp.encoding if resp.encoding and resp.encoding.lower() != "iso-8859-1" else "utf-8"
        return resp.text
