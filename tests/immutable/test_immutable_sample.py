"""Sample immutable governance and pipeline contract test (read-only after lock)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.pipeline import run_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_immutable_governance_files_present_and_bounded() -> None:
    """Verify CONSTRAINTS.md has at most 5 numbered rules and feature_list.json is valid."""
    constraints_path = REPO_ROOT / "CONSTRAINTS.md"
    assert constraints_path.exists()
    text = constraints_path.read_text(encoding="utf-8")
    numbered_rules = [
        line for line in text.splitlines() if line.strip()[:2] in {"1.", "2.", "3.", "4.", "5.", "6."}
    ]
    assert len(numbered_rules) == 5

    fl_path = REPO_ROOT / "feature_list.json"
    data = json.loads(fl_path.read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert len(data["features"]) >= 1


def test_immutable_pipeline_rejects_bad_input(tmp_path: Path) -> None:
    """Verify run_pipeline raises explicit errors on invalid inputs and writes state on valid input."""
    with pytest.raises(ValueError):
        run_pipeline(tmp_path, {})

    with pytest.raises(ValueError):
        run_pipeline(tmp_path, {"project_id": "   "})

    result = run_pipeline(tmp_path, {"project_id": "S01_DEMO"})
    assert result["project_id"] == "S01_DEMO"
    assert result["stage"] == "VIDEO_NEW"
    assert Path(result["state_file"]).exists()
