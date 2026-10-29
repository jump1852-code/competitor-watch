"""Orchestrates one monitoring run: scrape -> diff -> persist."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from .config import AppConfig, TargetConfig
from .detect import diff_snapshots, index
from .fetcher import PoliteFetcher
from .models import Change
from .scraper import CssScraper, Fetcher
from .storage import Store

log = logging.getLogger(__name__)


@dataclass(slots=True)
class TargetResult:
    target: str
    status: str
    products: int = 0
    changes: int = 0
    error: str | None = None


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def run_target(target: TargetConfig, fetcher: Fetcher, store: Store, now: str | None = None) -> TargetResult:
    now = now or utc_now()
    started = time.perf_counter()
    try:
        products = CssScraper(target, fetcher).scrape(scraped_at=now)
        if not products:
            raise RuntimeError("0 products parsed — selectors may be out of date")
    except Exception as exc:  # one broken site must not stop the run
        log.exception("target %s failed", target.id)
        result = TargetResult(target.id, "error", error=str(exc))
        store.append_run(
            {
                "run_at": now,
                "target": target.id,
                "status": "error",
                "error": str(exc),
                "duration_s": round(time.perf_counter() - started, 2),
            }
        )
        return result

    previous = store.load_latest(target.id)
    changes: list[Change] = []
    if previous is None:
        log.info("%s: first run — recording baseline, no changes emitted", target.id)
    else:
        changes = diff_snapshots(index(previous), index(products), now)

    store.save_latest(target.id, products, now)
    store.record_prices(now[:10], products)
    store.append_changes(changes)
    store.append_run(
        {
            "run_at": now,
            "target": target.id,
            "status": "ok",
            "products": len(products),
            "changes": len(changes),
            "duration_s": round(time.perf_counter() - started, 2),
        }
    )
    log.info("%s: %d products, %d changes", target.id, len(products), len(changes))
    return TargetResult(target.id, "ok", len(products), len(changes))


def run_all(
    config: AppConfig, store: Store, only: list[str] | None = None, fetcher: Fetcher | None = None
) -> list[TargetResult]:
    fetcher = fetcher or PoliteFetcher(config.settings)
    now = utc_now()
    results = []
    for target in config.targets:
        if not target.enabled or (only and target.id not in only):
            continue
        results.append(run_target(target, fetcher, store, now))
    return results
