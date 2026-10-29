"""Core data models."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


def product_id(target_id: str, url: str) -> str:
    """Stable, short identifier derived from the target and canonical product URL."""
    digest = hashlib.sha1(f"{target_id}|{url}".encode()).hexdigest()
    return digest[:12]


@dataclass(slots=True)
class Product:
    """A single product observed on a target site at a point in time."""

    id: str
    target: str
    name: str
    url: str
    price: float | None
    currency: str
    category: str = ""
    availability: str | None = None
    rating: float | None = None
    reviews: int | None = None
    description: str | None = None
    image: str | None = None
    scraped_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Product:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


class ChangeType(StrEnum):
    NEW = "new"
    REMOVED = "removed"
    PRICE_UP = "price_up"
    PRICE_DOWN = "price_down"
    CHANGED = "changed"


@dataclass(slots=True)
class Change:
    """A detected difference between two snapshots of the same target."""

    type: ChangeType
    target: str
    product_id: str
    name: str
    detected_at: str
    old_price: float | None = None
    new_price: float | None = None
    currency: str = ""
    fields: dict[str, list[Any]] = field(default_factory=dict)
    sample: bool = False

    @property
    def pct_change(self) -> float | None:
        if self.old_price and self.new_price is not None:
            return round((self.new_price - self.old_price) / self.old_price * 100, 2)
        return None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["pct_change"] = self.pct_change
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Change:
        data = {k: v for k, v in data.items() if k != "pct_change"}
        data["type"] = ChangeType(data["type"])
        return cls(**data)
