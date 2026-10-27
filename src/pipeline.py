"""Core pipeline entrypoint, NTFS crash-safe file replacement, and P0 spikes."""
from __future__ import annotations

import ctypes, os, re, sqlite3, time, unicodedata
from ctypes import wintypes
from pathlib import Path
from typing import Any
import psutil

MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH = 0x1, 0x8
REQUIRED_ENV_KEYS: tuple[str, ...] = (
    "node", "git", "ffmpeg", "ffprobe", "python", "playwright",
    "whisper", "sqlite", "ram", "disk", "power_plan", "page_file", "defender_exclusion",
)
MIN_SQLITE_VERSION: tuple[int, int, int] = (3, 51, 3)
AUDIO_RE = re.compile(r"^S(\d{2,})\.(en|hi|ta)\.(wav|mp3|m4a)$", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"[.?!…।॥]+")

if os.name == "nt":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    _k32.MoveFileExW.restype = wintypes.BOOL
else:
    _k32 = None

def durable_replace(tmp_path: str | Path, dst_path: str | Path, timeout: float = 15.0) -> Path:
    src, dst = Path(tmp_path), Path(dst_path)
    if not src.exists():
        raise FileNotFoundError(f"Temporary source file does not exist: {src}")
    deadline, flags = time.monotonic() + timeout, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
    while True:
        if _k32 is not None:
            if _k32.MoveFileExW(str(src), str(dst), flags):
                return dst
            err = ctypes.get_last_error()
            if err in (5, 32) and time.monotonic() < deadline:
                time.sleep(0.05); continue
            raise ctypes.WinError(err)
        os.replace(src, dst); return dst

def _parse_version_tuple(v: str) -> tuple[int, ...]:
    parts = [int(p) for p in re.findall(r"\d+", str(v))]
    return tuple(parts[:3]) if parts else (0, 0, 0)

def validate_environment(env_report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(env_report, dict):
        raise TypeError("env_report must be a dict")
    for key in REQUIRED_ENV_KEYS:
        if key not in env_report:
            raise ValueError(f"Missing required environment check key: {key}")
    sqlite_entry = env_report["sqlite"]
    v_str = str(sqlite_entry.get("version", "")) if isinstance(sqlite_entry, dict) else str(sqlite_entry)
    if _parse_version_tuple(v_str) < MIN_SQLITE_VERSION:
        raise RuntimeError(f"SQLite version {v_str} is below required 3.51.3")
    todo = [f"{k}: {item.get('note') or item.get('status')}" for k, item in env_report.items()
            if isinstance(item, dict) and item.get("status") in ("FAIL", "WARN")]
    return {"valid": len(todo) == 0, "checks": env_report, "todo": todo}

def validate_audio_filename(filename: str) -> dict[str, Any]:
    if not isinstance(filename, str):
        raise TypeError("filename must be a string")
    m = AUDIO_RE.match(filename.strip())
    if not m:
        raise ValueError(f"Invalid audio filename: {filename!r}")
    num = int(m.group(1))
    if num < 1:
        raise ValueError(f"Invalid audio filename: Scene number must be >= 1: {num}")
    return {"scene_num": num, "lang": m.group(2).lower(), "ext": m.group(3).lower()}

def normalize_vo_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if text.startswith("\ufeff"):
        text = text[1:]
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))

def split_sentences(text: str) -> list[str]:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("VO text cannot be empty")
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(cleaned) if s.strip()]

def compute_scene_duration(audio_duration: float, lead_in: float = 0.3, tail: float = 0.5) -> float:
    if not isinstance(audio_duration, (int, float)):
        raise TypeError("audio_duration must be numeric")
    if audio_duration < 0:
        raise ValueError("audio_duration cannot be negative")
    return round(float(audio_duration) + lead_in + tail, 3)

def verify_utf8_roundtrip(text: str, db_path: Path | None = None) -> bool:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    norm = normalize_vo_text(text)
    src_bytes = norm.encode("utf-8")
    db_file = db_path or Path("work") / "utf8_test.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("CREATE TABLE IF NOT EXISTS roundtrip (id INTEGER PRIMARY KEY, content TEXT);")
        conn.execute("INSERT INTO roundtrip (content) VALUES (?);", (norm,))
        conn.commit()
        cur = conn.execute("SELECT content FROM roundtrip ORDER BY id DESC LIMIT 1;")
        row = cur.fetchone()
        read_text = row[0] if row else ""
    finally:
        conn.close()
    return read_text.encode("utf-8") == src_bytes

def check_process_memory_budget(max_tree_gb: float = 2.8, min_available_gb: float = 1.2) -> dict[str, Any]:
    if max_tree_gb <= 0 or min_available_gb <= 0:
        raise ValueError("Memory limits must be positive")
    current_proc = psutil.Process(os.getpid())
    tree_rss = current_proc.memory_info().rss
    for child in current_proc.children(recursive=True):
        try:
            tree_rss += child.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    tree_gb = round(tree_rss / (1024**3), 3)
    available_gb = round(psutil.virtual_memory().available / (1024**3), 3)
    return {"tree_gb": tree_gb, "available_gb": available_gb, "within_budget": (tree_gb <= max_tree_gb) and (available_gb >= min_available_gb)}

def run_pipeline(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(project_root, Path):
        raise TypeError("project_root must be a pathlib.Path instance")
    if not isinstance(payload, dict) or not payload.get("project_id"):
        raise ValueError("payload must be a dict containing a non-empty 'project_id'")
    project_id = str(payload["project_id"]).strip()
    if not project_id:
        raise ValueError("project_id cannot be whitespace")

    env_result = validate_environment(payload["env_report"]) if "env_report" in payload else None
    spikes_result = None
    if payload.get("run_spikes"):
        vo_raw = str(payload.get("vo_text", ""))
        audio_name = str(payload.get("audio_file", "S01.en.wav"))
        audio_dur = float(payload.get("audio_duration", 0.0))
        audio_info = validate_audio_filename(audio_name)
        norm_vo = normalize_vo_text(vo_raw)
        sentences = split_sentences(norm_vo)
        scene_dur = compute_scene_duration(audio_dur)
        utf8_ok = verify_utf8_roundtrip(norm_vo, project_root / "work" / "utf8_test.db")
        mem = check_process_memory_budget()
        spikes_result = {"audio": audio_info, "norm_vo": norm_vo, "sentences": sentences, "scene_duration": scene_dur, "utf8_ok": utf8_ok, "memory": mem}

    work_dir = project_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = work_dir / f"{project_id}.state.tmp"
    dst_file = work_dir / f"{project_id}.state.json"
    with open(tmp_file, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'{{"project_id": "{project_id}", "stage": "VIDEO_NEW"}}\n')
        fh.flush()
        os.fsync(fh.fileno())
    final_path = durable_replace(tmp_file, dst_file)
    ret: dict[str, Any] = {"project_id": project_id, "stage": "VIDEO_NEW", "state_file": str(final_path)}
    if env_result is not None:
        ret["env"] = env_result
    if spikes_result is not None:
        ret["spikes"] = spikes_result
    return ret
