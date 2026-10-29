from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from competitor_watch.config import Settings
from competitor_watch.fetcher import PoliteFetcher, RobotsDisallowed


@dataclass
class Resp:
    text: str
    status_code: int = 200
    encoding: str | None = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


@dataclass
class FakeSession:
    routes: dict[str, Resp]
    calls: list[str] = field(default_factory=list)

    def get(self, url: str, timeout: float) -> Resp:
        self.calls.append(url)
        return self.routes.get(url, Resp("not found", 404))


class Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(round(s, 3))
        self.t += s


def make(routes, delay=2.0):
    clock = Clock()
    session = FakeSession(routes)
    f = PoliteFetcher(Settings(min_delay_seconds=delay), session=session, sleep=clock.sleep, clock=clock.now)  # type: ignore[arg-type]
    return f, session, clock


def test_robots_disallow_blocks_request():
    f, session, _ = make(
        {
            "https://shop.test/robots.txt": Resp("User-agent: *\nDisallow: /private/\n"),
            "https://shop.test/public": Resp("ok"),
        }
    )
    assert f.get("https://shop.test/public") == "ok"
    with pytest.raises(RobotsDisallowed):
        f.get("https://shop.test/private/x")
    assert "https://shop.test/private/x" not in session.calls
    assert session.calls.count("https://shop.test/robots.txt") == 1, "robots.txt is cached"


def test_missing_robots_means_allowed():
    f, _, _ = make({"https://shop.test/a": Resp("A")})
    assert f.get("https://shop.test/a") == "A"


def test_per_host_rate_limit():
    f, _, clock = make(
        {"https://a.test/1": Resp("1"), "https://a.test/2": Resp("2"), "https://b.test/1": Resp("b")}
    )
    f.get("https://a.test/1")
    f.get("https://b.test/1")  # different host: no wait
    f.get("https://a.test/2")  # same host, no time passed -> waits full delay
    assert clock.slept == [2.0]


def test_real_session_has_retries_configured():
    f = PoliteFetcher(Settings(max_retries=4, user_agent="ua-test"))
    adapter = f.session.get_adapter("https://example.com")
    assert adapter.max_retries.total == 4  # type: ignore[attr-defined]
    assert 503 in adapter.max_retries.status_forcelist  # type: ignore[attr-defined]
    assert f.session.headers["User-Agent"] == "ua-test"
