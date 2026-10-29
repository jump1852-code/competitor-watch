import json

from bs4 import BeautifulSoup

from competitor_watch.config import AppConfig
from competitor_watch.dashboard import build_payload
from competitor_watch.pipeline import run_target
from competitor_watch.sample import generate
from competitor_watch.storage import Store


def _setup(config, books_html, fake_fetcher_cls):
    target = next(t for t in config.targets if t.id == "books-travel")
    return target, fake_fetcher_cls({target.start_url: books_html})


def test_first_run_is_baseline_then_changes_detected(tmp_path, config, books_html, fake_fetcher_cls):
    store = Store(tmp_path)
    target, fetcher = _setup(config, books_html, fake_fetcher_cls)

    r1 = run_target(target, fetcher, store, now="2026-01-01T02:00:00+00:00")
    assert (r1.status, r1.products, r1.changes) == ("ok", 11, 0)

    # Simulate the site changing: a price drop, a stock-out and a delisting.
    soup = BeautifulSoup(books_html.replace("£45.17", "£39.99"), "html.parser")
    pods = soup.select("article.product_pod")
    pods[1].select_one("p.availability").string = "Out of stock"
    pods[-1].decompose()
    fetcher.pages[target.start_url] = str(soup)
    r2 = run_target(target, fetcher, store, now="2026-01-02T02:00:00+00:00")
    assert r2.status == "ok"
    kinds = sorted(c.type.value for c in store.read_changes())
    assert kinds == ["changed", "price_down", "removed"]

    rows = store.read_prices()
    assert {r["date"] for r in rows} == {"2026-01-01", "2026-01-02"}
    assert len(store.read_runs()) == 2


def test_rerun_same_day_upserts_prices(tmp_path, config, books_html, fake_fetcher_cls):
    store = Store(tmp_path)
    target, fetcher = _setup(config, books_html, fake_fetcher_cls)
    run_target(target, fetcher, store, now="2026-01-01T02:00:00+00:00")
    run_target(target, fetcher, store, now="2026-01-01T09:00:00+00:00")
    assert len(store.read_prices()) == 11


def test_failed_target_is_isolated(tmp_path, config, fake_fetcher_cls):
    store = Store(tmp_path)
    target = config.targets[0]
    result = run_target(target, fake_fetcher_cls({target.start_url: "<html></html>"}), store)
    assert result.status == "error" and "0 products" in (result.error or "")
    assert store.load_latest(target.id) is None


def test_sample_history_and_dashboard_payload(tmp_path, config: AppConfig, books_html, fake_fetcher_cls):
    store = Store(tmp_path)
    target, fetcher = _setup(config, books_html, fake_fetcher_cls)
    run_target(target, fetcher, store, now="2026-03-01T02:00:00+00:00")
    n = generate(store, days=20, seed=1)
    assert n > 0
    assert all(c.sample for c in store.read_changes())
    # The sample walk must end exactly at today's real prices.
    latest = {p.id: p.price for p in store.load_latest(target.id) or []}
    today_rows = [r for r in store.read_prices() if r["date"] == "2026-03-01"]
    assert {r["product_id"]: float(r["price"]) for r in today_rows} == latest

    payload = build_payload(config, store)
    assert payload["sample_until"] == "2026-02-28"
    assert len(payload["products"]) == 11
    assert payload["price_index"]["books-travel"][-1][0] == "2026-03-01"
    json.dumps(payload)  # serialisable
