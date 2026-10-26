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


def run_pipeline(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate project payload and execute an atomic state heartbeat write."""
    if not isinstance(project_root, Path):
        raise TypeError("project_root must be a pathlib.Path instance")
    if not isinstance(payload, dict) or not payload.get("project_id"):
        raise ValueError("payload must be a dict containing a non-empty 'project_id'")

    project_id = str(payload["project_id"]).strip()
    if not project_id:
        raise ValueError("project_id cannot be whitespace")

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
    return {
        "project_id": project_id,
        "stage": "VIDEO_NEW",
        "state_file": str(final_path),
    }
