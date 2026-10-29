"""File-based storage: everything lives in plain JSON/CSV inside the repo.

Layout::

    data/
      latest/<target>.json     # most recent snapshot per target
      history/prices.csv       # one row per product per run (long format)
      changes.jsonl            # append-only change log
      runs.json                # run metadata (status, counts, duration)

Plain files keep the project dependency-free, diff-able in pull requests and
free to host: GitHub *is* the database.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import Change, Product

PRICE_COLUMNS = ("date", "target", "product_id", "price", "currency", "sample")
MAX_RUNS = 2000


class Store:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.latest_dir = self.root / "latest"
        self.prices_csv = self.root / "history" / "prices.csv"
        self.changes_log = self.root / "changes.jsonl"
        self.runs_file = self.root / "runs.json"

    def ensure(self) -> None:
        self.latest_dir.mkdir(parents=True, exist_ok=True)
        self.prices_csv.parent.mkdir(parents=True, exist_ok=True)

    # -- snapshots --------------------------------------------------------
    def load_latest(self, target: str) -> list[Product] | None:
        path = self.latest_dir / f"{target}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Product.from_dict(p) for p in data["products"]]

    def save_latest(self, target: str, products: Iterable[Product], scraped_at: str) -> None:
        self.ensure()
        payload = {
            "target": target,
            "scraped_at": scraped_at,
            "products": [p.to_dict() for p in sorted(products, key=lambda p: p.name.lower())],
        }
        (self.latest_dir / f"{target}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def all_latest(self) -> dict[str, list[Product]]:
        out: dict[str, list[Product]] = {}
        if self.latest_dir.exists():
            for path in sorted(self.latest_dir.glob("*.json")):
                products = self.load_latest(path.stem)
                if products is not None:
                    out[path.stem] = products
        return out

    # -- price history ----------------------------------------------------
    def read_prices(self) -> list[dict[str, str]]:
        if not self.prices_csv.exists():
            return []
        with self.prices_csv.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def write_prices(self, rows: list[dict[str, Any]]) -> None:
        self.ensure()
        rows = sorted(rows, key=lambda r: (r["date"], r["target"], r["product_id"]))
        with self.prices_csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=PRICE_COLUMNS)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, "") for k in PRICE_COLUMNS})

    def record_prices(self, date: str, products: Iterable[Product], *, sample: bool = False) -> None:
        """Upsert the price rows for ``date`` (re-running on the same day replaces them)."""
        products = list(products)
        targets = {p.target for p in products}
        rows: list[dict[str, Any]] = [
            r for r in self.read_prices() if not (r["date"] == date and r["target"] in targets)
        ]
        rows += [
            {
                "date": date,
                "target": p.target,
                "product_id": p.id,
                "price": "" if p.price is None else f"{p.price:.2f}",
                "currency": p.currency,
                "sample": int(sample),
            }
            for p in products
        ]
        self.write_prices(rows)

    # -- change log -------------------------------------------------------
    def append_changes(self, changes: Iterable[Change]) -> int:
        self.ensure()
        n = 0
        with self.changes_log.open("a", encoding="utf-8") as fh:
            for c in changes:
                fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
                n += 1
        return n

    def read_changes(self) -> list[Change]:
        if not self.changes_log.exists():
            return []
        return [
            Change.from_dict(json.loads(line))
            for line in self.changes_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def rewrite_changes(self, changes: Iterable[Change]) -> None:
        self.ensure()
        self.changes_log.write_text(
            "".join(json.dumps(c.to_dict(), ensure_ascii=False) + "\n" for c in changes),
            encoding="utf-8",
        )

    # -- runs -------------------------------------------------------------
    def read_runs(self) -> list[dict[str, Any]]:
        if not self.runs_file.exists():
            return []
        runs: list[dict[str, Any]] = json.loads(self.runs_file.read_text(encoding="utf-8"))
        return runs

    def append_run(self, run: dict[str, Any]) -> None:
        self.ensure()
        runs = ([*self.read_runs(), run])[-MAX_RUNS:]
        self.runs_file.write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")
