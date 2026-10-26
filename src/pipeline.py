"""Core pipeline entrypoint and NTFS crash-safe file replacement primitive."""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

MOVEFILE_REPLACE_EXISTING = 0x1
MOVEFILE_WRITE_THROUGH = 0x8

REQUIRED_ENV_KEYS: tuple[str, ...] = (
    "node", "git", "ffmpeg", "ffprobe", "python", "playwright",
    "whisper", "sqlite", "ram", "disk", "power_plan", "page_file", "defender_exclusion",
)
MIN_SQLITE_VERSION: tuple[int, int, int] = (3, 51, 3)

if os.name == "nt":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    _k32.MoveFileExW.restype = wintypes.BOOL
else:
    _k32 = None


def durable_replace(tmp_path: str | Path, dst_path: str | Path, timeout: float = 15.0) -> Path:
    """Atomically replace dst_path with tmp_path using MoveFileExW on Windows."""
    src = Path(tmp_path)
    dst = Path(dst_path)
    if not src.exists():
        raise FileNotFoundError(f"Temporary source file does not exist: {src}")

    deadline = time.monotonic() + timeout
    flags = MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH

    while True:
        if _k32 is not None:
            if _k32.MoveFileExW(str(src), str(dst), flags):
                return dst
            err = ctypes.get_last_error()
            if err in (5, 32) and time.monotonic() < deadline:
                time.sleep(0.05)
                continue
            raise ctypes.WinError(err)
        else:
            os.replace(src, dst)
            return dst


def _parse_version_tuple(v: str) -> tuple[int, ...]:
    cleaned = "".join(ch if (ch.isdigit() or ch == ".") else " " for ch in v).strip()
    parts = [int(p) for p in cleaned.split() if p.isdigit()]
    if not parts and "." in v:
        parts = [int(p) for p in v.split(".") if p.isdigit()]
    return tuple(parts[:3])


def validate_environment(env_report: dict[str, Any]) -> dict[str, Any]:
    """Validate environment status report against P0a requirements."""
    if not isinstance(env_report, dict):
        raise TypeError("env_report must be a dict")
    for key in REQUIRED_ENV_KEYS:
        if key not in env_report:
            raise ValueError(f"Missing required environment check key: {key}")

    sqlite_entry = env_report["sqlite"]
    v_str = str(sqlite_entry.get("version", "")) if isinstance(sqlite_entry, dict) else str(sqlite_entry)
    v_tuple = _parse_version_tuple(v_str)
    if v_tuple < MIN_SQLITE_VERSION:
        raise RuntimeError(f"SQLite version {v_str} is below required 3.51.3")

    todo: list[str] = []
    for k, item in env_report.items():
        if isinstance(item, dict) and item.get("status") in ("FAIL", "WARN"):
            todo.append(f"{k}: {item.get('note') or item.get('status')}")

    return {"valid": len(todo) == 0, "checks": env_report, "todo": todo}


def run_pipeline(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate project payload and execute an atomic state heartbeat write."""
    if not isinstance(project_root, Path):
        raise TypeError("project_root must be a pathlib.Path instance")
    if not isinstance(payload, dict) or not payload.get("project_id"):
        raise ValueError("payload must be a dict containing a non-empty 'project_id'")

    project_id = str(payload["project_id"]).strip()
    if not project_id:
        raise ValueError("project_id cannot be whitespace")

    env_result: dict[str, Any] | None = None
    if "env_report" in payload:
        env_result = validate_environment(payload["env_report"])

    work_dir = project_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = work_dir / f"{project_id}.state.tmp"
    dst_file = work_dir / f"{project_id}.state.json"

    content = f'{{"project_id": "{project_id}", "stage": "VIDEO_NEW"}}\n'
    with open(tmp_file, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())

    final_path = durable_replace(tmp_file, dst_file)
    ret: dict[str, Any] = {
        "project_id": project_id,
        "stage": "VIDEO_NEW",
        "state_file": str(final_path),
    }
    if env_result is not None:
        ret["env"] = env_result
    return ret
