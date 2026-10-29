from dataclasses import replace

import pytest

from competitor_watch.scraper import CssScraper, next_page_url, parse_listing, parse_price

TS = "2026-01-01T00:00:00+00:00"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("£51.77", 51.77),
        ("$1,299.00", 1299.0),
        (" 416.99 ", 416.99),
        ("Free", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def _target(config, tid):
    return next(t for t in config.targets if t.id == tid)


def test_parse_books_listing(config, books_html):
    target = _target(config, "books-travel")
    url = target.start_url
    products = parse_listing(books_html, url, target, TS)
    assert len(products) == 11
    first = products[0]
    assert first.name == "It's Only the Himalayas"
    assert first.price == 45.17 and first.currency == "GBP"
    assert first.rating == 2
    assert first.availability == "In stock"
    assert first.url.startswith("https://books.toscrape.com/catalogue/")
    assert first.image and first.image.startswith("https://books.toscrape.com/media/")
    assert len({p.id for p in products}) == len(products)


def test_parse_webscraper_listing(config, laptops_html):
    target = _target(config, "ws-laptops")
    products = parse_listing(laptops_html, target.start_url, target, TS)
    assert len(products) == 6
    assert all(p.price and p.price > 0 for p in products)
    assert all(
        p.url.startswith("https://webscraper.io/test-sites/e-commerce/static/product/") for p in products
    )
    assert all(isinstance(p.reviews, int) for p in products)
    assert next_page_url(laptops_html, target.start_url, target) == target.start_url + "?page=2"


def _pages(target, html, n):
    """Fake a paginated site: page i links to page i+1."""
    pages = {}
    for i in range(1, n + 1):
        url = target.start_url if i == 1 else f"{target.start_url}?page={i}"
        pages[url] = html.replace('laptops?page=2" rel="next"', f'laptops?page={i + 1}" rel="next"')
    return pages


def test_scraper_stops_at_max_pages_and_dedupes(config, laptops_html, fake_fetcher_cls):
    target = _target(config, "ws-laptops")
    fetcher = fake_fetcher_cls(_pages(target, laptops_html, 10))
    products = CssScraper(target, fetcher).scrape(TS)
    assert len(fetcher.calls) == target.max_pages == 3
    assert len(products) == 6  # identical items on every page are de-duplicated


def test_scraper_breaks_pagination_cycles(config, laptops_html, fake_fetcher_cls):
    target = replace(_target(config, "ws-laptops"), max_pages=50)
    # page 2 links back to page 2 -> must stop instead of looping
    pages = {target.start_url: laptops_html, f"{target.start_url}?page=2": laptops_html}
    fetcher = fake_fetcher_cls(pages)
    CssScraper(target, fetcher).scrape(TS)
    assert fetcher.calls == [target.start_url, f"{target.start_url}?page=2"]
