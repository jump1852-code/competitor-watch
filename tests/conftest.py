from __future__ import annotations

from pathlib import Path

import pytest

from competitor_watch.config import AppConfig, load_config

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def config() -> AppConfig:
    return load_config(ROOT / "config" / "targets.yaml")


@pytest.fixture()
def books_html() -> str:
    return (FIXTURES / "books_travel.html").read_text(encoding="utf-8")


@pytest.fixture()
def laptops_html() -> str:
    return (FIXTURES / "ws_laptops.html").read_text(encoding="utf-8")


class FakeFetcher:
    """Serves canned HTML by URL; records the URLs requested."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str) -> str:
        self.calls.append(url)
        return self.pages[url]


@pytest.fixture()
def fake_fetcher_cls() -> type[FakeFetcher]:
    return FakeFetcher
