import json
import shutil
from pathlib import Path

from competitor_watch.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_build_command_on_repo_data(tmp_path: Path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    out = tmp_path / "site"
    assert (
        main(["--config", str(ROOT / "config/targets.yaml"), "--data", str(data), "build", "--out", str(out)])
        == 0
    )
    payload = json.loads((out / "dashboard.json").read_text())
    assert payload["products"] and payload["targets"]
