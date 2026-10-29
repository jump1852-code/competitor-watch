"""Generate clearly-labelled SAMPLE history so the dashboard looks alive on day one.

The public demo sites never change their prices, so a freshly deployed tracker
would show flat lines. This module walks *backwards* from the real, current
snapshot and synthesises N days of plausible history (price moves, stock-outs,
delistings and launches). Every generated row/change carries ``sample: true``
and the dashboard shades that period, so it is never mistaken for real data.
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from .detect import diff_snapshots, index
from .models import Product
from .storage import Store


def _ts(d: date) -> str:
    return datetime.combine(d, time(2, 0), tzinfo=UTC).isoformat()


def generate(store: Store, days: int = 45, seed: int = 1852, force: bool = False) -> int:
    existing = store.read_prices()
    if any(r.get("sample") == "1" for r in existing) and not force:
        raise RuntimeError("sample history already present (use --force to regenerate)")
    rng = random.Random(seed)
    latest = store.all_latest()
    if not latest:
        raise RuntimeError("no snapshots found — run `competitor-watch run` first")

    real_changes = [c for c in store.read_changes() if not c.sample]
    rows: list[dict[str, Any]] = [r for r in existing if r.get("sample") != "1"]
    sample_changes = []
    today = min(datetime.fromisoformat(products[0].scraped_at).date() for products in latest.values())
    dates = [today - timedelta(days=i) for i in range(days, 0, -1)]

    for _target_id, current in latest.items():
        # price[d][pid] built backwards from today's real price.
        price_path: dict[str, list[float | None]] = {}
        for p in current:
            path: list[float | None] = []
            price = p.price
            for _ in dates:
                if price is not None and rng.random() < 0.035:
                    price = round(price / (1 + rng.choice([-1, 1]) * rng.uniform(0.03, 0.15)), 2)
                path.append(price)
            price_path[p.id] = list(reversed(path))

        launched = {p.id: rng.randint(5, days - 3) for p in rng.sample(current, k=max(1, len(current) // 12))}
        gaps: dict[str, tuple[int, int]] = {}
        for p in rng.sample(current, k=max(1, len(current) // 15)):
            start = rng.randint(3, days - 8)
            gaps[p.id] = (start, start + rng.randint(2, 6))
        stockouts: dict[str, tuple[int, int]] = {}
        for p in rng.sample(current, k=max(1, len(current) // 10)):
            start = rng.randint(2, days - 5)
            stockouts[p.id] = (start, start + rng.randint(1, 4))

        prev: dict[str, Product] | None = None
        for i, d in enumerate(dates):
            snap: list[Product] = []
            for p in current:
                if p.id in launched and i < launched[p.id]:
                    continue
                if p.id in gaps and gaps[p.id][0] <= i < gaps[p.id][1]:
                    continue
                avail = p.availability
                if p.availability and p.id in stockouts and stockouts[p.id][0] <= i < stockouts[p.id][1]:
                    avail = "Out of stock"
                snap.append(replace(p, price=price_path[p.id][i], availability=avail, scraped_at=_ts(d)))
            cur = index(snap)
            if prev is not None:
                sample_changes += diff_snapshots(prev, cur, _ts(d), sample=True)
            rows += [
                {
                    "date": d.isoformat(),
                    "target": s.target,
                    "product_id": s.id,
                    "price": "" if s.price is None else f"{s.price:.2f}",
                    "currency": s.currency,
                    "sample": 1,
                }
                for s in snap
            ]
            prev = cur
        # Bridge from the last sample day to the real baseline.
        assert prev is not None
        first_real = datetime.fromisoformat(current[0].scraped_at)
        sample_changes += diff_snapshots(prev, index(current), first_real.isoformat(), sample=True)

    store.write_prices(rows)
    store.rewrite_changes(sorted(sample_changes + real_changes, key=lambda c: c.detected_at))
    return len(sample_changes)
