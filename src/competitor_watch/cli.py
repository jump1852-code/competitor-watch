"""Command line interface: ``competitor-watch run | build | seed``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .dashboard import write_dashboard
from .pipeline import run_all
from .sample import generate
from .storage import Store


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="competitor-watch", description=__doc__)
    p.add_argument("--config", default="config/targets.yaml", type=Path)
    p.add_argument("--data", default="data", type=Path, help="data directory")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="scrape all targets, detect changes, persist history")
    run.add_argument("--only", nargs="*", help="limit to these target ids")
    run.add_argument("--fail-on-error", action="store_true", help="exit 1 if any target fails")

    build = sub.add_parser("build", help="build site/data/dashboard.json")
    build.add_argument("--out", default="site/data", type=Path)

    seed = sub.add_parser("seed", help="generate labelled SAMPLE history behind the real data")
    seed.add_argument("--days", type=int, default=45)
    seed.add_argument("--force", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    store = Store(args.data)

    if args.cmd == "run":
        results = run_all(config, store, only=args.only)
        ok = [r for r in results if r.status == "ok"]
        print(
            f"{len(ok)}/{len(results)} targets ok · "
            f"{sum(r.products for r in ok)} products · {sum(r.changes for r in ok)} changes"
        )
        for r in results:
            if r.status != "ok":
                print(f"  ✗ {r.target}: {r.error}", file=sys.stderr)
        return 1 if args.fail_on_error and len(ok) != len(results) else 0
    if args.cmd == "build":
        path = write_dashboard(config, store, args.out)
        print(f"wrote {path}")
        return 0
    if args.cmd == "seed":
        n = generate(store, days=args.days, force=args.force)
        print(f"generated {n} sample changes over {args.days} days")
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
