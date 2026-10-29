"""Generic, selector-driven scraper.

Every target in ``targets.yaml`` is described declaratively (item selector,
field selectors, pagination). :func:`parse_listing` is a pure function so it
can be unit-tested against saved HTML fixtures without touching the network.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .config import FieldSpec, TargetConfig
from .models import Product, product_id

log = logging.getLogger(__name__)

_PRICE_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


class Fetcher(Protocol):
    def get(self, url: str) -> str: ...


def parse_price(text: str | None) -> float | None:
    """Extract a float from strings such as ``'£51.77'`` or ``'$1,299.00'``."""
    if not text:
        return None
    match = _PRICE_RE.search(text.replace("\xa0", " "))
    return float(match.group().replace(",", "")) if match else None


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    text = " ".join(text.split())
    return text or None


def _extract(node: Tag, spec: FieldSpec) -> Any:
    el = node.select_one(spec.selector)
    if el is None:
        return None
    if spec.attr:
        raw = el.get(spec.attr)
        value: Any = " ".join(raw) if isinstance(raw, list) else raw
    else:
        value = el.get_text(" ", strip=True)
    if spec.map and isinstance(value, str):
        for token in value.split():
            if token in spec.map:
                return spec.map[token]
        return None
    return _clean(value) if isinstance(value, str) else value


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    f = parse_price(str(value)) if value is not None else None
    return int(f) if f is not None else None


def parse_listing(html: str, page_url: str, target: TargetConfig, scraped_at: str) -> list[Product]:
    """Parse one listing page into :class:`Product` objects."""
    soup = BeautifulSoup(html, "html.parser")
    products: list[Product] = []
    for node in soup.select(target.item_selector):
        values = {name: _extract(node, spec) for name, spec in target.fields.items()}
        if not values.get("name") or not values.get("url"):
            log.debug("skipping item without name/url on %s", page_url)
            continue
        url = urljoin(page_url, str(values["url"]))
        image = urljoin(page_url, str(values["image"])) if values.get("image") else None
        products.append(
            Product(
                id=product_id(target.id, url),
                target=target.id,
                name=str(values["name"]),
                url=url,
                price=parse_price(str(values.get("price") or "")),
                currency=target.currency,
                category=target.category,
                availability=values.get("availability"),
                rating=_to_float(values.get("rating")),
                reviews=_to_int(values.get("reviews")),
                description=values.get("description"),
                image=image,
                scraped_at=scraped_at,
            )
        )
    return products


def next_page_url(html: str, page_url: str, target: TargetConfig) -> str | None:
    if not target.next_page_selector:
        return None
    el = BeautifulSoup(html, "html.parser").select_one(target.next_page_selector)
    href = el.get("href") if el is not None else None
    return urljoin(page_url, str(href)) if href else None


class CssScraper:
    """Walks a target's paginated listing and yields products."""

    def __init__(self, target: TargetConfig, fetcher: Fetcher) -> None:
        self.target = target
        self.fetcher = fetcher

    def iter_pages(self) -> Iterator[tuple[str, str]]:
        url: str | None = self.target.start_url
        seen: set[str] = set()
        for _ in range(self.target.max_pages):
            if url is None or url in seen:
                break
            seen.add(url)
            html = self.fetcher.get(url)
            yield url, html
            url = next_page_url(html, url, self.target)

    def scrape(self, scraped_at: str | None = None) -> list[Product]:
        ts = scraped_at or datetime.now(UTC).replace(microsecond=0).isoformat()
        by_id: dict[str, Product] = {}
        for page_url, html in self.iter_pages():
            for product in parse_listing(html, page_url, self.target, ts):
                by_id.setdefault(product.id, product)
        log.info("%s: %d products", self.target.id, len(by_id))
        return list(by_id.values())
