"""Load and validate the YAML target configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when the configuration file is invalid."""


@dataclass(frozen=True, slots=True)
class FieldSpec:
    selector: str
    attr: str | None = None
    map: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TargetConfig:
    id: str
    name: str
    site: str
    start_url: str
    item_selector: str
    fields: dict[str, FieldSpec]
    category: str = ""
    currency: str = "USD"
    max_pages: int = 1
    next_page_selector: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class Settings:
    user_agent: str = "competitor-watch/1.0"
    min_delay_seconds: float = 1.5
    timeout_seconds: float = 20.0
    max_retries: int = 3
    backoff_factor: float = 1.0


@dataclass(frozen=True, slots=True)
class AppConfig:
    settings: Settings
    targets: list[TargetConfig] = field(default_factory=list)


REQUIRED_TARGET_KEYS = ("id", "name", "site", "start_url", "item_selector", "fields")
REQUIRED_FIELDS = ("name", "url", "price")


def _parse_target(raw: dict[str, Any]) -> TargetConfig:
    missing = [k for k in REQUIRED_TARGET_KEYS if k not in raw]
    if missing:
        raise ConfigError(f"target {raw.get('id', '?')!r} is missing keys: {missing}")
    fields_raw = raw["fields"]
    if not isinstance(fields_raw, dict):
        raise ConfigError(f"target {raw['id']!r}: 'fields' must be a mapping")
    missing_fields = [f for f in REQUIRED_FIELDS if f not in fields_raw]
    if missing_fields:
        raise ConfigError(f"target {raw['id']!r} must define fields: {missing_fields}")
    fields = {
        name: FieldSpec(selector=spec["selector"], attr=spec.get("attr"), map=spec.get("map"))
        for name, spec in fields_raw.items()
    }
    return TargetConfig(
        id=str(raw["id"]),
        name=str(raw["name"]),
        site=str(raw["site"]),
        start_url=str(raw["start_url"]),
        item_selector=str(raw["item_selector"]),
        fields=fields,
        category=str(raw.get("category", "")),
        currency=str(raw.get("currency", "USD")),
        max_pages=int(raw.get("max_pages", 1)),
        next_page_selector=raw.get("next_page_selector"),
        enabled=bool(raw.get("enabled", True)),
    )


def load_config(path: str | Path) -> AppConfig:
    """Parse ``targets.yaml`` into typed config objects."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    settings = Settings(**(data.get("settings") or {}))
    targets = [_parse_target(t) for t in data.get("targets") or []]
    ids = [t.id for t in targets]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ConfigError(f"duplicate target ids: {sorted(dupes)}")
    return AppConfig(settings=settings, targets=targets)
