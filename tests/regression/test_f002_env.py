"""Regression tests for Phase P0a / Feature F-002: Environment check script."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.pipeline import run_pipeline, validate_environment


MOCK_VALID_REPORT: dict[str, Any] = {
    k: {"status": "PASS", "version": "1.0", "free_gb": 20.0, "allocated_mb": 9000, "configured": True}
    for k in (
        "node", "git", "ffmpeg", "ffprobe", "python", "playwright",
        "whisper", "sqlite", "ram", "disk", "power_plan", "page_file", "defender_exclusion",
    )
}
MOCK_VALID_REPORT["sqlite"] = {"status": "PASS", "version": "3.51.3"}


def test_validate_environment_type_error() -> None:
    """Non-dict input must raise TypeError."""
    with pytest.raises(TypeError, match="must be a dict"):
        validate_environment(None)  # type: ignore[arg-type]


def test_validate_environment_missing_keys() -> None:
    """Missing any required environment key must raise explicit ValueError."""
    with pytest.raises(ValueError, match="Missing required environment check key"):
        validate_environment({"node": {"status": "PASS"}})


def test_validate_environment_sqlite_too_old() -> None:
    """SQLite version below 3.51.3 must raise explicit RuntimeError."""
    bad = {**MOCK_VALID_REPORT, "sqlite": {"status": "FAIL", "version": "3.50.4"}}
    with pytest.raises(RuntimeError, match=r"SQLite version .* below required 3\.51\.3"):
        validate_environment(bad)


def test_validate_environment_valid_report() -> None:
    """Valid report returns structured validation dictionary with actionable todo list."""
    res = validate_environment(MOCK_VALID_REPORT)
    assert isinstance(res, dict) and res.get("valid") is True
    assert "checks" in res and "todo" in res and isinstance(res["todo"], list)


def test_validate_environment_wired_in_run_pipeline(tmp_path: Path) -> None:
    """validate_environment must be reachable and return value retained in run_pipeline."""
    payload = {"project_id": "proj_env_test", "env_report": MOCK_VALID_REPORT}
    out = run_pipeline(tmp_path, payload)
    assert isinstance(out, dict) and out.get("env") is not None and out["env"]["valid"] is True

    bad_payload = {"project_id": "proj_env_test", "env_report": {**MOCK_VALID_REPORT, "sqlite": "3.50.4"}}
    with pytest.raises(RuntimeError):
        run_pipeline(tmp_path, bad_payload)


def test_check_env_script_json_output() -> None:
    """powershell scripts/check_env.ps1 -JsonOut must return parseable JSON with all keys."""
    script_path = Path("scripts/check_env.ps1")
    assert script_path.exists(), "scripts/check_env.ps1 does not exist yet"
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path), "-JsonOut"]
    res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert res.returncode == 0, f"check_env.ps1 failed: {res.stderr}"

    data = json.loads(res.stdout)
    required = [
        "node", "git", "ffmpeg", "ffprobe", "python", "playwright",
        "whisper", "sqlite", "ram", "disk", "power_plan", "page_file", "defender_exclusion",
    ]
    for key in required:
        assert key in data and isinstance(data[key], dict) and "status" in data[key]


def test_check_env_script_human_output_and_todo() -> None:
    """powershell scripts/check_env.ps1 (default) outputs summary and human to-do items."""
    script_path = Path("scripts/check_env.ps1")
    assert script_path.exists(), "scripts/check_env.ps1 does not exist yet"
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
    res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert res.returncode == 0
    assert "Environment Check" in res.stdout
    assert "Actionable To-Do" in res.stdout or "All checks passed" in res.stdout
