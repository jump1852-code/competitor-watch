from pathlib import Path

import pytest

from competitor_watch.config import ConfigError, load_config


def test_repo_config_is_valid(config):
    assert len(config.targets) >= 4
    assert {"books-travel", "ws-laptops"} <= {t.id for t in config.targets}
    assert config.settings.min_delay_seconds >= 1, "be polite to demo sites"
    for t in config.targets:
        assert {"name", "url", "price"} <= t.fields.keys()


def test_missing_required_field_raises(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "targets:\n  - {id: x, name: X, site: s, start_url: 'https://e.x', item_selector: div,"
        " fields: {name: {selector: a}}}\n"
    )
    with pytest.raises(ConfigError, match="must define fields"):
        load_config(p)


def test_duplicate_ids_raise(tmp_path: Path):
    block = (
        "  - {id: x, name: X, site: s, start_url: 'https://e.x', item_selector: div,"
        " fields: {name: {selector: a}, url: {selector: a, attr: href}, price: {selector: p}}}\n"
    )
    p = tmp_path / "c.yaml"
    p.write_text("targets:\n" + block + block)
    with pytest.raises(ConfigError, match="duplicate"):
        load_config(p)
