"""Change detection between two snapshots of a target."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .models import Change, ChangeType, Product

#: Non-price attributes that produce a ``changed`` event when they differ.
WATCHED_FIELDS: tuple[str, ...] = ("name", "availability", "rating", "description")

#: Ignore float noise smaller than this when comparing prices.
PRICE_EPSILON = 0.005


def index(products: Iterable[Product]) -> dict[str, Product]:
    return {p.id: p for p in products}


def diff_snapshots(
    previous: Mapping[str, Product],
    current: Mapping[str, Product],
    detected_at: str,
    *,
    sample: bool = False,
) -> list[Change]:
    """Return the list of changes needed to go from ``previous`` to ``current``.

    * products only in ``current``   -> ``new``
    * products only in ``previous``  -> ``removed``
    * price moved                    -> ``price_up`` / ``price_down``
    * any :data:`WATCHED_FIELDS` moved -> ``changed`` (with before/after values)
    """
    changes: list[Change] = []

    for pid in sorted(current.keys() - previous.keys()):
        p = current[pid]
        changes.append(
            Change(
                ChangeType.NEW,
                p.target,
                pid,
                p.name,
                detected_at,
                new_price=p.price,
                currency=p.currency,
                sample=sample,
            )
        )

    for pid in sorted(previous.keys() - current.keys()):
        p = previous[pid]
        changes.append(
            Change(
                ChangeType.REMOVED,
                p.target,
                pid,
                p.name,
                detected_at,
                old_price=p.price,
                currency=p.currency,
                sample=sample,
            )
        )

    for pid in sorted(previous.keys() & current.keys()):
        old, new = previous[pid], current[pid]
        if old.price is not None and new.price is not None and abs(new.price - old.price) > PRICE_EPSILON:
            kind = ChangeType.PRICE_UP if new.price > old.price else ChangeType.PRICE_DOWN
            changes.append(
                Change(
                    kind,
                    new.target,
                    pid,
                    new.name,
                    detected_at,
                    old_price=old.price,
                    new_price=new.price,
                    currency=new.currency,
                    sample=sample,
                )
            )
        moved = {
            f: [getattr(old, f), getattr(new, f)]
            for f in WATCHED_FIELDS
            if getattr(old, f) != getattr(new, f)
        }
        if moved:
            changes.append(
                Change(
                    ChangeType.CHANGED,
                    new.target,
                    pid,
                    new.name,
                    detected_at,
                    old_price=old.price,
                    new_price=new.price,
                    currency=new.currency,
                    fields=moved,
                    sample=sample,
                )
            )
    return changes
