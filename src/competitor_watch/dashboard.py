"""Build the compact JSON payload consumed by the static dashboard in ``site/``."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import ChangeType
from .storage import Store

MAX_CHANGES = 600


def build_payload(config: AppConfig, store: Store) -> dict[str, Any]:
    latest = store.all_latest()
    price_rows = store.read_prices()
    changes = sorted(store.read_changes(), key=lambda c: c.detected_at, reverse=True)
    runs = store.read_runs()

    # Per-product price series, compressed to change points (+ last point).
    series: dict[str, list[list[Any]]] = defaultdict(list)
    first_seen: dict[str, str] = {}
    by_target_date: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    sample_dates: set[str] = set()
    for r in sorted(price_rows, key=lambda r: r["date"]):
        if not r["price"]:
            continue
        price = float(r["price"])
        pid = r["product_id"]
        first_seen.setdefault(pid, r["date"])
        s = series[pid]
        if not s or s[-1][1] != price:
            s.append([r["date"], price])
        last_date = r["date"]
        by_target_date[r["target"]][r["date"]][pid] = price
        if r.get("sample") == "1":
            sample_dates.add(r["date"])
        series[pid + "__last"] = [[last_date, price]]

    change_counts: dict[str, int] = defaultdict(int)
    for c in changes:
        change_counts[c.product_id] += 1

    products = []
    for target_id, items in latest.items():
        for p in items:
            pts = series.get(p.id, [])
            last = series.get(p.id + "__last")
            if pts and last and pts[-1][0] != last[0][0]:
                pts = pts + last
            first_price = pts[0][1] if pts else p.price
            products.append(
                {
                    "id": p.id,
                    "target": target_id,
                    "name": p.name,
                    "url": p.url,
                    "price": p.price,
                    "currency": p.currency,
                    "category": p.category,
                    "availability": p.availability,
                    "rating": p.rating,
                    "image": p.image,
                    "first_seen": first_seen.get(p.id),
                    "history": pts,
                    "changes": change_counts.get(p.id, 0),
                    "pct_since_first": round((p.price - first_price) / first_price * 100, 2)
                    if p.price and first_price
                    else 0.0,
                }
            )

    # Price index per target: mean of (price / first observed price) * 100.
    index_series: dict[str, list[list[Any]]] = {}
    for target_id, dates in by_target_date.items():
        base: dict[str, float] = {}
        pts_out = []
        for date in sorted(dates):
            rel = []
            for pid, price in dates[date].items():
                base.setdefault(pid, price)
                rel.append(price / base[pid] * 100)
            pts_out.append([date, round(sum(rel) / len(rel), 2)])
        index_series[target_id] = pts_out

    daily: dict[str, dict[str, int]] = defaultdict(lambda: {t.value: 0 for t in ChangeType})
    for c in changes:
        daily[c.detected_at[:10]][c.type.value] += 1

    last_runs: dict[str, dict[str, Any]] = {}
    for r in runs:
        last_runs[r["target"]] = r

    targets = [
        {
            "id": t.id,
            "name": t.name,
            "site": t.site,
            "category": t.category,
            "currency": t.currency,
            "url": t.start_url,
            "count": len(latest.get(t.id, [])),
            "last_run": last_runs.get(t.id),
        }
        for t in config.targets
    ]

    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "sample_until": max(sample_dates) if sample_dates else None,
        "targets": targets,
        "products": sorted(products, key=lambda p: (p["target"], p["name"])),
        "changes": [c.to_dict() for c in changes[:MAX_CHANGES]],
        "daily": [{"date": d, **v} for d, v in sorted(daily.items())],
        "price_index": index_series,
        "runs": runs[-60:],
    }


def write_dashboard(config: AppConfig, store: Store, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "dashboard.json"
    path.write_text(
        json.dumps(build_payload(config, store), separators=(",", ":"), ensure_ascii=False), encoding="utf-8"
    )
    return path
