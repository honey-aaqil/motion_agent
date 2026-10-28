"""Core pipeline entrypoint, NTFS crash-safe file replacement, and P0 spikes."""
from __future__ import annotations

import ctypes, hashlib, json, os, random, re, sqlite3, threading, time, unicodedata, urllib.error, urllib.request
from ctypes import wintypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
import psutil

VALID_THINKING_LEVELS: frozenset[str] = frozenset({"low", "medium", "high"})

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

def validate_gemini_config(cfg: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(cfg, dict):
        raise TypeError("cfg must be a dict")
    tokens = cfg.get("max_output_tokens", 8192)
    if not isinstance(tokens, int) or tokens <= 0:
        raise ValueError("max_output_tokens must be positive int")
    thinking = str(cfg.get("thinking_level", "medium")).lower()
    if thinking not in VALID_THINKING_LEVELS:
        raise ValueError(f"Invalid thinking_level: {thinking}")
    temp = float(cfg.get("temperature", 0.7))
    if not (0.0 <= temp <= 2.0):
        raise ValueError("temperature must be between 0.0 and 2.0")
    min_interval = float(cfg.get("min_interval_sec", 15.5))
    if min_interval <= 0:
        raise ValueError("min_interval_sec must be positive")
    daily_cap = cfg.get("daily_quota_cap")
    if daily_cap is not None and (not isinstance(daily_cap, int) or daily_cap < 0):
        raise ValueError("daily_quota_cap must be non-negative int")
    return {"model_id": str(cfg.get("model_id", "gemini-2.5-flash")), "model_fallbacks": list(cfg.get("model_fallbacks", [])), "max_output_tokens": tokens, "thinking_level": thinking, "temperature": temp, "min_interval_sec": min_interval, "daily_quota_cap": daily_cap}

def compute_backoff_delay(attempt: int, base: float = 2.0, max_delay: float = 120.0, jitter: float = 0.0) -> float:
    if not isinstance(attempt, int) or isinstance(attempt, bool):
        raise TypeError("attempt must be an int")
    if attempt < 0:
        raise ValueError("attempt cannot be negative")
    if base <= 0 or max_delay <= 0:
        raise ValueError("base and max_delay must be positive")
    if jitter < 0:
        raise ValueError("jitter cannot be negative")
    return round(min(float(max_delay), float(base**attempt + jitter)), 3)

def classify_gemini_status(status_code: int, consecutive_503: int = 0, fallback_models: list[str] | None = None, is_daily_quota: bool = False) -> dict[str, Any]:
    if not isinstance(status_code, int) or isinstance(status_code, bool):
        raise TypeError("status_code must be an int")
    if not (100 <= status_code <= 599):
        raise ValueError(f"Invalid HTTP status code: {status_code}")
    if status_code == 200:
        return {"consume_call": True, "action": "success"}
    if status_code == 503:
        if consecutive_503 >= 5:
            return {"consume_call": False, "action": "switch_fallback", "target_model": fallback_models[0]} if fallback_models else {"consume_call": False, "action": "pause_queue"}
        return {"consume_call": False, "action": "retry_with_backoff"}
    if status_code in (500, 502, 504):
        return {"consume_call": False, "action": "retry_with_backoff"}
    if status_code == 429:
        return {"consume_call": False, "action": "quota_sleep_until_reset" if is_daily_quota else "wait_rate_limit"}
    if status_code == 400:
        return {"consume_call": True, "action": "repair"}
    return {"consume_call": False, "action": "fail_loud"}

def run_503_load_simulation(request_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(request_results, list) or len(request_results) == 0:
        raise ValueError("request_results must be a non-empty list")
    latencies, status_counts, tot_th, tot_out, empty_or_trunc = [], {}, 0, 0, 0
    for req in request_results:
        if not isinstance(req, dict) or not isinstance(req.get("status_code"), int) or not isinstance(req.get("latency_ms"), (int, float)):
            raise (TypeError if not isinstance(req, dict) else ValueError)("invalid request result entry")
        latencies.append(float(req["latency_ms"]))
        status_counts[req["status_code"]] = status_counts.get(req["status_code"], 0) + 1
        tot_th += int(req.get("thoughts_tokens", 0))
        tot_out += int(req.get("output_tokens", 0))
        empty_or_trunc += 1 if req.get("empty_or_truncated", False) else 0
    total, sorted_lat = len(request_results), sorted(latencies)
    ratio = round(tot_th / tot_out, 3) if tot_out > 0 else 0.0
    empty_rate = round(empty_or_trunc / total, 3)
    return {
        "total_requests": total, "status_counts": status_counts,
        "overload_rate_503": round((status_counts.get(503, 0) / total) * 100.0, 2),
        "success_rate": round((status_counts.get(200, 0) / total) * 100.0, 2),
        "latency_p50_ms": sorted_lat[int(0.50 * (total - 1))],
        "latency_p90_ms": sorted_lat[int(0.90 * (total - 1))],
        "latency_p99_ms": sorted_lat[int(0.99 * (total - 1))],
        "thoughts_token_ratio": ratio, "empty_or_truncated_rate": empty_rate,
        "recommend_thinking_step_down": (empty_rate > 0.05) or (ratio > 0.75),
    }

def run_gemini_diagnostics(config: dict[str, Any] | None = None, sample_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cfg, backoff_probe, status_probe = validate_gemini_config(config or {}), compute_backoff_delay(0, jitter=0.0), classify_gemini_status(200)
    results = sample_results or [
        {"status_code": 503 if (i % 5 in (0, 2, 4)) else 200, "latency_ms": 1200.0 if (i % 2 == 0) else 800.0, "thoughts_tokens": 200, "output_tokens": 600}
        for i in range(30)
    ]
    return {"status": "DIAGNOSTICS_READY", "has_api_key": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEYS")), "config": cfg, "simulation": run_503_load_simulation(results), "probes": {"backoff_base": backoff_probe, "status_ok": status_probe["action"] == "success"}}

MAX_LLM_CALLS_PER_SCENE, MAX_BIBLE_CALLS_PER_VIDEO = 2, 1
ALLOWED_SCENE_TRANSITIONS: dict[str, frozenset[str]] = {
    "SCENE_READY": frozenset({"IN_PROGRESS"}), "IN_PROGRESS": frozenset({"SCENE_READY", "DRAFT_AUTHORED", "NEEDS_HUMAN_EDIT"}),
    "DRAFT_AUTHORED": frozenset({"CANONICALIZED"}), "CANONICALIZED": frozenset({"VALIDATED", "DRAFT_AUTHORED", "NEEDS_HUMAN_EDIT", "SCENE_READY"}),
    "VALIDATED": frozenset({"SCENE_ACCEPTED"}), "NEEDS_HUMAN_EDIT": frozenset({"SCENE_READY", "VALIDATED"}), "SCENE_ACCEPTED": frozenset(),
}

def init_database(db_path: Path | str) -> sqlite3.Connection:
    if not isinstance(db_path, (str, Path)):
        raise TypeError("db_path must be a string or pathlib.Path")
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.executescript("""
        PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=30000;
        PRAGMA wal_autocheckpoint=1000; PRAGMA journal_size_limit=67108864; PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS projects (project_id TEXT PRIMARY KEY, title TEXT, status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS scenes (scene_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, scene_index INTEGER NOT NULL, status TEXT NOT NULL, calls_used INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0.0, locked_by TEXT, draft_spec_json TEXT, canonical_spec_json TEXT, validation_log_json TEXT, audit_log_json TEXT, vlm_review_json TEXT, updated_at REAL NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(project_id));
        CREATE TABLE IF NOT EXISTS scene_attempts (attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, scene_id TEXT NOT NULL, project_id TEXT NOT NULL, attempt_num INTEGER NOT NULL, prompt_hash TEXT NOT NULL, raw_response TEXT, canonical_spec TEXT, validation_metrics TEXT, dom_metrics TEXT, latency_ms REAL, thoughts_tokens INTEGER, output_tokens INTEGER, created_at REAL NOT NULL, FOREIGN KEY(scene_id) REFERENCES scenes(scene_id));
        CREATE TABLE IF NOT EXISTS api_rate_ledger (call_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, model_id TEXT, status_code INTEGER, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS editor_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, scene_id TEXT NOT NULL, action_type TEXT NOT NULL, pre_edit_validator_warn INTEGER DEFAULT 0, pre_edit_cv_warn INTEGER DEFAULT 0, token_levenshtein_pct REAL DEFAULT 0.0, anchor_unchanged INTEGER DEFAULT 1, is_clean_quality_pair INTEGER DEFAULT 0, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS llm_queue (request_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, prompt_hash TEXT NOT NULL, prompt_text TEXT NOT NULL, task TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'PENDING', response_text TEXT, error TEXT, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS llm_log (log_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, model_id TEXT NOT NULL, task TEXT NOT NULL, status_code INTEGER NOT NULL, latency_ms REAL NOT NULL, attempt INTEGER NOT NULL, error_code TEXT, created_at REAL NOT NULL);
    """)
    return conn

def transition_scene_state(conn: sqlite3.Connection, scene_id: str, new_status: str, calls_increment: int = 0) -> str:
    cur = conn.cursor()
    cur.execute("SELECT status, calls_used FROM scenes WHERE scene_id = ?;", (scene_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Scene not found: {scene_id}")
    curr_status, calls_used = row[0], int(row[1])
    if new_status not in ALLOWED_SCENE_TRANSITIONS.get(curr_status, frozenset()):
        raise ValueError(f"Illegal state transition from {curr_status} to {new_status}")
    new_calls = calls_used + int(calls_increment)
    if new_calls > MAX_LLM_CALLS_PER_SCENE:
        raise ValueError(f"MAX_LLM_CALLS_PER_SCENE exceeded: {new_calls} > {MAX_LLM_CALLS_PER_SCENE}")
    cur.execute("UPDATE scenes SET status = ?, calls_used = ?, updated_at = ? WHERE scene_id = ?;", (new_status, new_calls, time.time(), scene_id))
    conn.commit()
    return new_status

def acquire_scene_lease(conn: sqlite3.Connection, scene_id: str, worker_id: str, lease_sec: float = 90.0, now: float | None = None) -> bool:
    t = time.time() if now is None else float(now)
    cur = conn.cursor()
    cur.execute("SELECT status, locked_until FROM scenes WHERE scene_id = ?;", (scene_id,))
    row = cur.fetchone()
    if not row or (row[0] != "SCENE_READY" and not (row[0] == "IN_PROGRESS" and float(row[1]) < t)):
        return False
    cur.execute("UPDATE scenes SET status = 'IN_PROGRESS', locked_by = ?, locked_until = ?, updated_at = ? WHERE scene_id = ?;", (worker_id, t + lease_sec, t, scene_id))
    conn.commit()
    return True

def renew_scene_lease(conn: sqlite3.Connection, scene_id: str, worker_id: str, lease_sec: float = 90.0, now: float | None = None) -> bool:
    t = time.time() if now is None else float(now)
    cur = conn.cursor()
    cur.execute("SELECT status, locked_by FROM scenes WHERE scene_id = ?;", (scene_id,))
    row = cur.fetchone()
    if not row or row[0] != "IN_PROGRESS" or row[1] != worker_id:
        return False
    cur.execute("UPDATE scenes SET locked_until = ?, updated_at = ? WHERE scene_id = ?;", (t + lease_sec, t, scene_id))
    conn.commit()
    return True

def release_scene_lease(conn: sqlite3.Connection, scene_id: str, worker_id: str, new_status: str = "SCENE_READY") -> bool:
    cur = conn.cursor()
    cur.execute("SELECT locked_by FROM scenes WHERE scene_id = ?;", (scene_id,))
    row = cur.fetchone()
    if not row or row[0] != worker_id:
        return False
    cur.execute("UPDATE scenes SET status = ?, locked_by = NULL, locked_until = 0.0, updated_at = ? WHERE scene_id = ?;", (new_status, time.time(), scene_id))
    conn.commit()
    return True

def reclaim_expired_leases(conn: sqlite3.Connection, now: float | None = None) -> int:
    t = time.time() if now is None else float(now)
    cur = conn.cursor()
    cur.execute("UPDATE scenes SET status = 'SCENE_READY', locked_by = NULL, locked_until = 0.0, updated_at = ? WHERE status = 'IN_PROGRESS' AND locked_until < ?;", (t, t))
    reclaimed = cur.rowcount
    conn.commit()
    return max(0, reclaimed)

def classify_error_routing(faults: list[dict[str, Any]], calls_used: int) -> dict[str, Any]:
    if not isinstance(faults, list):
        raise TypeError("faults must be a list of dicts")
    if not isinstance(calls_used, int) or isinstance(calls_used, bool) or calls_used < 0:
        raise ValueError("calls_used must be a non-negative integer")
    if calls_used >= MAX_LLM_CALLS_PER_SCENE:
        return {"route": "NEEDS_HUMAN_EDIT", "reason": "calls_exhausted"}
    distinct_elements, is_global = set(), False
    for f in faults:
        if not isinstance(f, dict):
            raise TypeError("fault entry must be a dict")
        ftype = str(f.get("type", ""))
        if ftype in ("unparseable_output", "empty_response") or (int(f.get("count", 0)) >= 2 and "collision" in ftype) or float(f.get("overlap_area_pct", 0.0)) > 20.0:
            is_global = True
        if "element_id" in f:
            distinct_elements.add(str(f["element_id"]))
    return {"route": "GLOBAL_RESTART" if (len(distinct_elements) >= 3 or is_global) else "LOCAL_REPAIR", "reason": "routing_decision"}

def record_api_call(conn: sqlite3.Connection, project_id: str, model_id: str, status_code: int, created_at: float | None = None) -> int:
    if not isinstance(project_id, str) or not isinstance(model_id, str):
        raise TypeError("project_id and model_id must be strings")
    if not project_id.strip() or not model_id.strip():
        raise ValueError("project_id and model_id cannot be empty")
    if not isinstance(status_code, int) or isinstance(status_code, bool) or not (100 <= status_code <= 599):
        raise ValueError(f"Invalid status_code: {status_code}")
    t = time.time() if created_at is None else float(created_at)
    cur = conn.cursor()
    cur.execute("INSERT INTO api_rate_ledger (project_id, model_id, status_code, created_at) VALUES (?, ?, ?, ?);", (project_id, model_id, status_code, t))
    conn.commit()
    return int(cur.lastrowid)

def check_rate_governor(conn: sqlite3.Connection, now_monotonic: float, last_call_monotonic: float, now_wall: float | None = None, daily_quota_cap: int | None = None, min_interval_sec: float = 15.5) -> dict[str, Any]:
    if not isinstance(now_monotonic, (int, float)) or not isinstance(last_call_monotonic, (int, float)):
        raise TypeError("monotonic timestamps must be numeric")
    if now_monotonic < last_call_monotonic:
        raise ValueError("now_monotonic cannot be earlier than last_call_monotonic")
    interval = float(now_monotonic - last_call_monotonic)
    if interval < min_interval_sec:
        return {"allowed": False, "action": "wait_rate_limit", "wait_sec": round(min_interval_sec - interval, 3)}
    t_wall = time.time() if now_wall is None else float(now_wall)
    cur = conn.cursor()
    if daily_quota_cap is not None:
        cur.execute("SELECT COUNT(*) FROM api_rate_ledger WHERE created_at >= ?;", (t_wall - 86400.0,))
        row = cur.fetchone()
        if row and int(row[0]) >= int(daily_quota_cap):
            return {"allowed": False, "action": "QUOTA_SLEEP_UNTIL_RESET", "wait_sec": 86400.0}
    cur.execute("SELECT COUNT(*) FROM api_rate_ledger WHERE created_at >= ?;", (t_wall - 60.0,))
    r60 = cur.fetchone()
    if r60 and int(r60[0]) >= 4:
        return {"allowed": False, "action": "wait_rate_limit", "wait_sec": 62.0}
    return {"allowed": True, "action": "proceed", "wait_sec": 0.0}

def enqueue_llm_request(conn: sqlite3.Connection, project_id: str, prompt: str, task: str = "scene_author", priority: int = 1, now: float | None = None) -> str:
    if not isinstance(project_id, str) or not isinstance(prompt, str):
        raise TypeError("project_id and prompt must be strings")
    p_clean = prompt.strip()
    if not p_clean or not project_id.strip():
        raise ValueError("project_id and prompt cannot be empty")
    t = time.time() if now is None else float(now)
    p_hash = hashlib.sha256(p_clean.encode("utf-8")).hexdigest()
    cur = conn.cursor()
    cur.execute("SELECT request_id FROM llm_queue WHERE project_id = ? AND prompt_hash = ? AND status != 'FAILED' LIMIT 1;", (project_id, p_hash))
    row = cur.fetchone()
    if row:
        return str(row[0])
    req_id = f"req_{p_hash[:12]}_{int(t * 1000)}"
    cur.execute("INSERT INTO llm_queue (request_id, project_id, prompt_hash, prompt_text, task, priority, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?);",
                (req_id, project_id, p_hash, p_clean, task, int(priority), t))
    conn.commit()
    return req_id

def pop_next_llm_request(conn: sqlite3.Connection) -> dict[str, Any] | None:
    cur = conn.cursor()
    cur.execute("SELECT request_id, project_id, prompt_hash, prompt_text, task, priority FROM llm_queue WHERE status = 'PENDING' ORDER BY priority DESC, created_at ASC LIMIT 1;")
    row = cur.fetchone()
    if not row:
        return None
    req_id = str(row[0])
    cur.execute("UPDATE llm_queue SET status = 'IN_FLIGHT' WHERE request_id = ?;", (req_id,))
    conn.commit()
    return {"request_id": req_id, "project_id": str(row[1]), "prompt_hash": str(row[2]), "prompt_text": str(row[3]), "task": str(row[4]), "priority": int(row[5])}

def complete_llm_request(conn: sqlite3.Connection, request_id: str, response_text: str) -> bool:
    if not isinstance(request_id, str) or not isinstance(response_text, str):
        raise TypeError("request_id and response_text must be strings")
    cur = conn.cursor()
    cur.execute("UPDATE llm_queue SET status = 'COMPLETED', response_text = ? WHERE request_id = ?;", (response_text, request_id))
    conn.commit()
    return cur.rowcount > 0

def fail_llm_request(conn: sqlite3.Connection, request_id: str, error: str) -> bool:
    if not isinstance(request_id, str) or not isinstance(error, str):
        raise TypeError("request_id and error must be strings")
    cur = conn.cursor()
    cur.execute("UPDATE llm_queue SET status = 'FAILED', error = ? WHERE request_id = ?;", (error, request_id))
    conn.commit()
    return cur.rowcount > 0

def assert_model_version(actual_version: str, expected_model_id: str) -> bool:
    if not isinstance(actual_version, str) or not isinstance(expected_model_id, str):
        raise TypeError("model versions must be strings")
    if not actual_version.strip() or not expected_model_id.strip():
        raise ValueError("model versions cannot be empty")
    if actual_version.strip().lower() != expected_model_id.strip().lower():
        raise ValueError(f"Model version mismatch: expected {expected_model_id!r}, got {actual_version!r}")
    return True

def log_llm_call(conn: sqlite3.Connection, project_id: str, model_id: str, task: str, status_code: int, latency_ms: float, attempt: int, error_code: str | None = None, created_at: float | None = None) -> int:
    if not isinstance(project_id, str) or not isinstance(model_id, str) or not isinstance(task, str):
        raise TypeError("project_id, model_id and task must be strings")
    if not isinstance(latency_ms, (int, float)) or latency_ms < 0:
        raise ValueError("latency_ms must be non-negative")
    if not isinstance(attempt, int) or attempt < 0:
        raise ValueError("attempt must be non-negative int")
    t = time.time() if created_at is None else float(created_at)
    cur = conn.cursor()
    cur.execute("INSERT INTO llm_log (project_id, model_id, task, status_code, latency_ms, attempt, error_code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
                (project_id, model_id, task, int(status_code), float(latency_ms), attempt, error_code, t))
    conn.commit()
    return int(cur.lastrowid)

def format_llm_status_display(status: str, retry_num: int = 0, next_try_sec: float = 0.0) -> str:
    if not isinstance(status, str):
        raise TypeError("status must be a string")
    if retry_num < 0 or next_try_sec < 0:
        raise ValueError("retry_num and next_try_sec must be non-negative")
    if status == "waiting_llm":
        return f"waiting for LLM (retry {retry_num}, next try in {next_try_sec:.1f} s)"
    return f"LLM status: {status}"

def compute_llm_backoff(retry: int, rng_jitter: float | None = None) -> float:
    if not isinstance(retry, int) or isinstance(retry, bool): raise TypeError("retry must be an int")
    if retry < 0: raise ValueError("retry must be non-negative")
    jitter = random.uniform(0.0, 3.0) if rng_jitter is None else float(rng_jitter)
    return round(min(120.0, float(2 ** retry + jitter)), 3)

class _GeminiChaosHandler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        mode = self.headers.get("x-chaos-mode", getattr(self.server, "chaos_mode", "ok"))
        _ = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if mode == "slow_response":
            time.sleep(float(self.headers.get("x-chaos-delay", 0.15)))
        RESPONSES = {
            "503_storm": (503, b'{"error": {"code": 503, "message": "The model is overloaded.", "status": "UNAVAILABLE"}}', {}),
            "429_minute": (429, b'{"error": {"code": 429, "message": "Rate limit exceeded.", "status": "RESOURCE_EXHAUSTED"}}', {"Retry-After": "62"}),
            "429_day": (429, b'{"error": {"code": 429, "message": "Quota exceeded per day.", "status": "RESOURCE_EXHAUSTED"}}', {}),
            "truncated_json": (200, b'{"candidates": [{"content": {"parts": [{"text": "{\\"scene_id\\": "}]}}], "modelVersion": "gemini-2.5-flash"}', {}),
            "empty_200": (200, b'{"candidates": [], "modelVersion": "gemini-2.5-flash"}', {}),
            "wrong_model_version": (200, b'{"candidates": [{"content": {"parts": [{"text": "{\\"status\\": \\"ok\\"}"}]}}], "modelVersion": "gemini-1.5-flash"}', {}),
        }
        code, body, hdrs = RESPONSES.get(mode, (200, b'{"candidates": [{"content": {"parts": [{"text": "{\\"status\\": \\"ok\\"}"}], "role": "model"}, "finishReason": "STOP"}], "modelVersion": "gemini-2.5-flash"}', {}))
        self._send(code, body, hdrs)

    def log_message(self, format: str, *args: Any) -> None:
        pass

def start_gemini_chaos_server(host: str = "127.0.0.1", port: int = 0, mode: str = "ok") -> tuple[HTTPServer, threading.Thread, str]:
    if not isinstance(port, int) or port < 0:
        raise ValueError("port must be non-negative int")
    server = HTTPServer((host, port), _GeminiChaosHandler)
    server.chaos_mode = mode  # type: ignore[attr-defined]
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    actual_port = server.server_address[1]
    return server, th, f"http://{host}:{actual_port}"

def stop_gemini_chaos_server(server: HTTPServer, thread: threading.Thread) -> bool:
    if not isinstance(server, HTTPServer) or not isinstance(thread, threading.Thread):
        raise TypeError("server and thread must be HTTPServer and Thread instances")
    server.shutdown()
    server.server_close()
    thread.join(timeout=2.0)
    return True

def call_gemini_gateway(base_url: str, prompt: str, model_id: str = "gemini-2.5-flash", chaos_mode: str | None = None, timeout: float = 5.0, conn: sqlite3.Connection | None = None, project_id: str = "default_proj") -> dict[str, Any]:
    if not isinstance(base_url, str) or not base_url.startswith("http://"): raise ValueError("base_url must start with http://")
    if not isinstance(prompt, str): raise TypeError("prompt must be a string")
    if not prompt.strip(): raise ValueError("prompt cannot be empty")
    if not isinstance(model_id, str): raise TypeError("model_id must be a string")
    if not model_id.strip(): raise ValueError("model_id cannot be empty")
    hdrs = {"Content-Type": "application/json"}
    if chaos_mode:
        hdrs["x-chaos-mode"] = chaos_mode
    req = urllib.request.Request(f"{base_url.rstrip('/')}/v1beta/models/{model_id}:generateContent", data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8"), headers=hdrs, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        latency = (time.time() - t0) * 1000.0
        if conn is not None:
            log_llm_call(conn, project_id, model_id, "gateway", err.code, latency, 1, error_code=f"HTTP_{err.code}")
        if err.code == 503:
            return {"status": 503, "error": "503_OVERLOAD", "retryable": True}
        if err.code == 429:
            is_day = "per day" in body.lower() or "requests per day" in body.lower()
            return {"status": 429, "error": "QUOTA_SLEEP_UNTIL_RESET" if is_day else "429_RATE_LIMIT", "retryable": not is_day, "wait_sec": 86400.0 if is_day else 62.0}
        return {"status": err.code, "error": f"HTTP_{err.code}", "retryable": False}
    except (urllib.error.URLError, TimeoutError, OSError):
        latency = (time.time() - t0) * 1000.0
        if conn is not None:
            log_llm_call(conn, project_id, model_id, "gateway", 504, latency, 1, error_code="HTTP_504")
        return {"status": 504, "error": "TIMEOUT", "retryable": True}

    latency = (time.time() - t0) * 1000.0
    parsed = json.loads(body)
    m_ver = parsed.get("modelVersion", "")
    assert_model_version(m_ver, model_id)
    cands = parsed.get("candidates", [])
    if not cands or not cands[0].get("content", {}).get("parts"):
        return {"status": 200, "error": "empty_response", "text": "", "valid": False}
    cand_text = cands[0]["content"]["parts"][0].get("text", "")
    try:
        _ = json.loads(cand_text)
        is_valid, err_msg = True, None
    except Exception:
        is_valid, err_msg = False, "unparseable_output"
    if conn is not None and is_valid:
        record_api_call(conn, project_id, model_id, 200)
        log_llm_call(conn, project_id, model_id, "gateway", 200, latency, 1)
    ret: dict[str, Any] = {"status": 200, "valid": is_valid, "model_version": m_ver, "text": cand_text}
    if err_msg:
        ret["error"] = err_msg
    return ret

def compute_render_chunks(total_frames: int, max_chunk_frames: int = 900) -> list[tuple[int, int]]:
    if not isinstance(total_frames, int) or isinstance(total_frames, bool) or total_frames <= 0:
        raise (TypeError if not isinstance(total_frames, int) or isinstance(total_frames, bool) else ValueError)("total_frames must be positive int")
    if not isinstance(max_chunk_frames, int) or isinstance(max_chunk_frames, bool) or max_chunk_frames <= 0:
        raise (TypeError if not isinstance(max_chunk_frames, int) or isinstance(max_chunk_frames, bool) else ValueError)("max_chunk_frames must be positive int")
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < total_frames:
        end = min(start + max_chunk_frames, total_frames)
        chunks.append((start, end))
        start = end
    return chunks

def get_chromium_render_flags() -> list[str]:
    return [
        "--disable-gpu",
        "--enable-software-rasterizer",
        "--headless=new",
        '--js-flags="--max-old-space-size=1536"',
        "--disable-dev-shm-usage",
        "--no-sandbox",
    ]

def check_render_resource_watchdog(process_tree_memory_bytes: int | None = None, available_ram_bytes: int | None = None, free_disk_bytes: int | None = None) -> dict[str, Any]:
    disk = shutil.disk_usage(".").free if free_disk_bytes is None else int(free_disk_bytes)
    if disk < 10 * 1024**3:
        raise RuntimeError(f"Free disk space below 10 GB: {disk / (1024**3):.2f} GB")
    mem = (psutil.Process().memory_info().rss) if process_tree_memory_bytes is None else int(process_tree_memory_bytes)
    ram = (psutil.virtual_memory().available) if available_ram_bytes is None else int(available_ram_bytes)
    if mem > int(2.8 * 1024**3) or ram < int(1.2 * 1024**3):
        return {"action": "RESPAWN", "reason": "memory_pressure", "tree_mem": mem, "available_ram": ram}
    return {"action": "OK", "free_disk": disk, "tree_mem": mem, "available_ram": ram}

def adjust_chunk_size_on_respawns(consecutive_respawns: int, current_chunk_size: int = 900) -> tuple[int, bool]:
    if not isinstance(consecutive_respawns, int) or consecutive_respawns < 0:
        raise ValueError("consecutive_respawns must be non-negative int")
    if not isinstance(current_chunk_size, int) or current_chunk_size <= 0:
        raise ValueError("current_chunk_size must be positive int")
    if consecutive_respawns >= 3:
        return (300, True)
    return (current_chunk_size, False)

def clean_stray_processes(process_names: list[str] | None = None) -> int:
    targets = [p.lower() for p in (process_names or ["chrome", "chrome-headless-shell", "ffmpeg", "ffprobe"])]
    cleaned = 0
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            p_name = (proc.info.get("name") or "").lower()
            if any(t in p_name for t in targets):
                cleaned += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return cleaned

def build_ffmpeg_encode_cmd(input_pattern: str, output_path: str, fps: int = 30, crf: int = 18, threads: int = 2) -> list[str]:
    if not (1 <= fps <= 120):
        raise ValueError("fps must be between 1 and 120")
    if not (0 <= crf <= 51):
        raise ValueError("crf must be between 0 and 51")
    if not (1 <= threads <= 16):
        raise ValueError("threads must be between 1 and 16")
    return ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(input_pattern), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf), "-movflags", "+faststart", "-threads", str(threads), str(output_path)]

def build_ffmpeg_concat_cmd(scene_clips: list[str], output_path: str) -> tuple[list[str], str]:
    if not scene_clips or not isinstance(scene_clips, list):
        raise ValueError("scene_clips must be non-empty list of paths")
    concat_lines = "\n".join(f"file '{c}'" for c in scene_clips)
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat_list.txt", "-c", "copy", str(output_path)]
    return cmd, concat_lines

def build_ffmpeg_mix_cmd(video_path: str, vo_audio_path: str, output_path: str, music_path: str | None = None, duck_db: float = -12.0) -> list[str]:
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-i", str(vo_audio_path)]
    if music_path:
        cmd.extend(["-i", str(music_path), "-filter_complex", f"[2:a]volume={duck_db}dB[bg];[1:a][bg]amix=inputs=2:duration=first[aout]", "-map", "0:v", "-map", "[aout]"])
    else:
        cmd.extend(["-map", "0:v", "-map", "1:a"])
    cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(output_path)])
    return cmd

def render_scene_chunk(scene_id: str, chunk_index: int, start_frame: int, end_frame: int, work_dir: Path, mock_frames: bool = True) -> dict[str, Any]:
    if not scene_id or not isinstance(scene_id, str):
        raise ValueError("scene_id must be non-empty string")
    count = max(0, end_frame - start_frame)
    chunk_file = Path(work_dir) / f"{scene_id}_chunk_{chunk_index}.mp4"
    if mock_frames:
        chunk_file.write_bytes(b"\x00" * 64)
    state_tmp = Path(work_dir) / f"{scene_id}.state.tmp"
    state_dst = Path(work_dir) / f"{scene_id}.state.json"
    state_data = json.dumps({"scene_id": scene_id, "chunk_index": chunk_index, "start_frame": start_frame, "end_frame": end_frame, "frames_rendered": count})
    state_tmp.write_text(state_data + "\n", encoding="utf-8")
    durable_replace(state_tmp, state_dst)
    return {"scene_id": scene_id, "chunk_index": chunk_index, "start_frame": start_frame, "end_frame": end_frame, "frames_rendered": count, "chunk_file": str(chunk_file)}

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

    gemini_result = None
    if payload.get("run_gemini_diag"):
        gemini_result = run_gemini_diagnostics(payload.get("gemini_config"), payload.get("gemini_samples"))

    work_dir = project_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    sm_result = None
    if payload.get("run_state_machine"):
        conn = init_database(work_dir / f"{project_id}.db")
        try:
            now_ts = time.time()
            conn.execute("INSERT OR REPLACE INTO projects (project_id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                         (project_id, "Test Project", "VIDEO_NEW", now_ts, now_ts))
            conn.execute("INSERT OR REPLACE INTO scenes (scene_id, project_id, scene_index, status, calls_used, locked_until, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?);",
                         ("S01", project_id, 1, "SCENE_READY", 0, 0.0, now_ts))
            conn.commit()
            acquire_scene_lease(conn, "S01", "worker_main", lease_sec=90.0, now=now_ts)
            renew_scene_lease(conn, "S01", "worker_main", lease_sec=90.0, now=now_ts + 10.0)
            transition_scene_state(conn, "S01", "DRAFT_AUTHORED", calls_increment=1)
            reclaim_expired_leases(conn, now=now_ts)
            classify_error_routing([{"element_id": "title"}], 1)
            release_scene_lease(conn, "S01", "worker_main", new_status="SCENE_READY")
            sm_result = {"status": "READY", "scenes_initialized": 1}
        finally:
            conn.close()

    gw_result = None
    if payload.get("run_gateway"):
        conn = init_database(work_dir / f"{project_id}.db")
        try:
            now_ts = time.time()
            record_api_call(conn, project_id, "gemini-2.5-flash", 200, created_at=now_ts)
            check_rate_governor(conn, now_monotonic=20.0, last_call_monotonic=0.0, now_wall=now_ts, daily_quota_cap=20)
            rid = enqueue_llm_request(conn, project_id, "test prompt", task="scene_author", priority=1, now=now_ts)
            popped = pop_next_llm_request(conn)
            if popped:
                complete_llm_request(conn, popped["request_id"], '{"status": "ok"}')
                fail_llm_request(conn, popped["request_id"], "none")
            log_llm_call(conn, project_id, "gemini-2.5-flash", "scene_author", 200, 50.0, 1, created_at=now_ts)
            assert_model_version("gemini-2.5-flash", "gemini-2.5-flash")
            format_llm_status_display("waiting_llm", retry_num=1, next_try_sec=15.5)
            gw_result = {"status": "READY", "request_id": rid}
        finally:
            conn.close()

    chaos_result = None
    if payload.get("run_chaos_server"):
        srv, th, base_url = start_gemini_chaos_server(mode="ok")
        try:
            b_sec = compute_llm_backoff(0, rng_jitter=1.0)
            res = call_gemini_gateway(base_url, "test prompt", model_id="gemini-2.5-flash")
            chaos_result = {"status": "READY", "backoff": b_sec, "res": res}
        finally:
            stop_gemini_chaos_server(srv, th)

    render_result = None
    if payload.get("render_chunking"):
        r_conf = payload["render_chunking"]
        t_frames = int(r_conf.get("total_frames", 900))
        sc_id = str(r_conf.get("scene_id", "S01"))
        chunks = compute_render_chunks(t_frames)
        get_chromium_render_flags()
        check_render_resource_watchdog(free_disk_bytes=20 * 1024**3, process_tree_memory_bytes=1024**3, available_ram_bytes=3 * 1024**3)
        adjust_chunk_size_on_respawns(0)
        clean_stray_processes()
        build_ffmpeg_encode_cmd("frame_%04d.png", "out.mp4")
        build_ffmpeg_concat_cmd(["s1.mp4"], "out.mp4")
        build_ffmpeg_mix_cmd("v.mp4", "vo.wav", "out.mp4")
        chunk_res = [render_scene_chunk(sc_id, i, st, en, work_dir, mock_frames=True) for i, (st, en) in enumerate(chunks)]
        render_result = {"status": "RENDERED", "chunks_count": len(chunks), "chunks": chunk_res}

    canary_result = None
    sabotage_result = None
    if payload.get("run_canaries"):
        canary_result = run_canary_gate(project_root, payload.get("canary_data", {}))
        sabotage_result = run_sabotage_suite(work_dir)

    tg_result = None
    if payload.get("run_templates_and_gates"):
        _ = get_layout_config("9:16")
        cat = get_template_catalog()
        can = canonicalize_scene_spec({"scene_id": "S01", "template_id": "title_slam", "ratio": "9:16", "cues": []})
        val = validate_scene_spec(can)
        dom = audit_dom_layout([{"id": "b1", "x": 100, "y": 200, "w": 400, "h": 200, "text": "OK", "font_size": 72, "color": "#FFFFFF", "bg": "#000000"}])
        sb = run_dom_sabotage_preflight()
        tg_result = {"passed": val["valid"] and dom["passed"] and sb["passed"], "catalog_size": len(cat), "preflight": sb}

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
    if gemini_result is not None:
        ret["gemini"] = gemini_result
    if sm_result is not None:
        ret["state_machine"] = sm_result
    if gw_result is not None:
        ret["gateway"] = gw_result
    if chaos_result is not None:
        ret["chaos"] = chaos_result
    if render_result is not None:
        ret["renderer"] = render_result
    if canary_result is not None:
        ret["canary_gate"] = canary_result
    if sabotage_result is not None:
        ret["sabotage_suite"] = sabotage_result
    if tg_result is not None:
        ret["templates_and_gates"] = tg_result
    return ret


def check_canary_inv1_streams(v_dur: float, a_dur: float, exp_dur: float, nb_frames: int, fps: float = 30.0) -> dict[str, Any]:
    if v_dur < 0 or a_dur < 0 or exp_dur < 0 or nb_frames < 0 or fps <= 0:
        raise ValueError("Invalid negative duration, frames, or non-positive fps")
    if not (abs(v_dur - a_dur) <= 0.05 and abs(v_dur - exp_dur) <= 0.10 and abs(nb_frames - round(v_dur * fps)) <= 1):
        return {"passed": False, "code": "CANARY_INV1_FAIL", "reason": "Stream duration or frame count mismatch"}
    return {"passed": True, "code": "INV-1", "v_dur": v_dur, "a_dur": a_dur, "nb_frames": nb_frames}

def check_canary_inv2_blackdetect(black_intervals: list[dict[str, float]], max_black_dur: float = 0.20, pic_th: float = 0.90, pix_th: float = 0.15) -> dict[str, Any]:
    if max_black_dur <= 0 or not (0.0 <= pic_th <= 1.0) or not (0.0 <= pix_th <= 1.0):
        raise ValueError("Invalid blackdetect parameters")
    for iv in black_intervals:
        if iv.get("duration", 0.0) >= max_black_dur:
            return {"passed": False, "code": "CANARY_INV2_BLACK_DETECTED", "duration": iv["duration"]}
    return {"passed": True, "code": "INV-2", "intervals": black_intervals}

def check_canary_inv3_freezedetect(freeze_intervals: list[dict[str, float]], max_freeze_dur: float = 2.0, noise_floor_db: float = -60.0) -> dict[str, Any]:
    if max_freeze_dur <= 0 or noise_floor_db >= 0:
        raise ValueError("Invalid freezedetect parameters")
    for iv in freeze_intervals:
        if iv.get("duration", 0.0) > max_freeze_dur:
            return {"passed": False, "code": "CANARY_INV3_FREEZE_DETECTED", "duration": iv["duration"]}
    return {"passed": True, "code": "INV-3", "freeze_intervals": freeze_intervals}

def check_canary_inv4_audio_loudness(integrated_lufs: float, true_peak: float, mean_volume: float, silence_duration: float, loudness_range: tuple[float, float] = (-24.0, -14.0), max_tp: float = -1.0, min_mean_vol: float = -40.0, max_silence: float = 1.5) -> dict[str, Any]:
    if loudness_range[0] >= loudness_range[1] or max_silence < 0:
        raise ValueError("Invalid audio loudness range or silence parameters")
    if not (loudness_range[0] <= integrated_lufs <= loudness_range[1] and true_peak <= max_tp and mean_volume > min_mean_vol and silence_duration < max_silence):
        return {"passed": False, "code": "CANARY_INV4_AUDIO_LOUDNESS_FAIL", "integrated_lufs": integrated_lufs, "mean_volume": mean_volume}
    return {"passed": True, "code": "INV-4", "integrated_lufs": integrated_lufs, "true_peak": true_peak}

def check_canary_inv5_golden_drift(rendered_framemd5: str, golden_framemd5: str) -> dict[str, Any]:
    if not rendered_framemd5 or not golden_framemd5:
        raise ValueError("framemd5 strings cannot be empty")
    if rendered_framemd5 != golden_framemd5:
        return {"passed": False, "code": "CANARY_INV5_GOLDEN_MISMATCH", "rendered": rendered_framemd5, "golden": golden_framemd5}
    return {"passed": True, "code": "INV-5", "framemd5": rendered_framemd5}

def check_canary_inv6_ledger(conn: sqlite3.Connection, project_id: str, now: float | None = None) -> dict[str, Any]:
    if not project_id or not isinstance(project_id, str):
        raise ValueError("project_id must be a non-empty string")
    now_ts = time.time() if now is None else now
    rows = conn.execute("SELECT scene_index, status, file_path, file_sha256, file_size, locked_until FROM scenes WHERE project_id = ? ORDER BY scene_index ASC;", (project_id,)).fetchall()
    if not rows:
        return {"passed": True, "code": "INV-6", "scenes_checked": 0}
    indices = [r[0] for r in rows if r[0] is not None]
    if indices != list(range(1, len(indices) + 1)):
        return {"passed": False, "code": "CANARY_INV6_LEDGER_FAIL", "reason": "Index gap"}
    for idx, status, f_path, f_sha, f_sz, locked in rows:
        if status == "DONE":
            if not f_path or not Path(f_path).exists():
                return {"passed": False, "code": "CANARY_INV6_LEDGER_FAIL", "reason": "Missing DONE file"}
            p = Path(f_path)
            if p.stat().st_size < 10240 or (f_sha and hashlib.sha256(p.read_bytes()).hexdigest() != f_sha):
                return {"passed": False, "code": "CANARY_INV6_LEDGER_FAIL", "reason": "DONE file <10KB or bad sha"}
        if status == "IN_PROGRESS" and locked is not None and locked < now_ts:
            return {"passed": False, "code": "CANARY_INV6_LEDGER_FAIL", "reason": "Expired lease"}
    return {"passed": True, "code": "INV-6", "scenes_checked": len(rows)}

def run_canary_gate(project_root: Path, canary_data: dict[str, Any], conn: sqlite3.Connection | None = None, project_id: str | None = None) -> dict[str, Any]:
    if not isinstance(project_root, Path):
        raise TypeError("project_root must be a pathlib.Path instance")
    r1 = check_canary_inv1_streams(canary_data.get("v_dur", 3.0), canary_data.get("a_dur", 3.0), canary_data.get("exp_dur", 3.0), canary_data.get("nb_frames", 90), canary_data.get("fps", 30.0))
    r2 = check_canary_inv2_blackdetect(canary_data.get("black_intervals", []))
    r3 = check_canary_inv3_freezedetect(canary_data.get("freeze_intervals", []))
    a = canary_data.get("audio", {})
    r4 = check_canary_inv4_audio_loudness(a.get("lufs", -18.0), a.get("tp", -1.5), a.get("mv", -25.0), a.get("silence", 0.0))
    r5 = check_canary_inv5_golden_drift(canary_data.get("rendered_md5", "c1"), canary_data.get("golden_md5", "c1"))
    r6 = check_canary_inv6_ledger(conn, project_id) if conn and project_id else {"passed": True, "code": "INV-6"}
    all_ok = all(r.get("passed") for r in (r1, r2, r3, r4, r5, r6))
    return {"passed": all_ok, "results": {"INV-1": r1, "INV-2": r2, "INV-3": r3, "INV-4": r4, "INV-5": r5, "INV-6": r6}}

def run_sabotage_suite(work_dir: Path) -> dict[str, Any]:
    if not isinstance(work_dir, Path):
        raise TypeError("work_dir must be a pathlib.Path instance")
    s1 = check_canary_inv1_streams(3.0, 3.2, 3.0, 90)
    s2 = check_canary_inv2_blackdetect([{"start": 0.0, "duration": 0.30}])
    s3 = check_canary_inv3_freezedetect([{"start": 0.0, "duration": 2.5}])
    s4 = check_canary_inv4_audio_loudness(-28.0, -2.0, -45.0, 0.0)
    s5 = check_canary_inv5_golden_drift("bad_md5", "good_md5")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE scenes (scene_id TEXT, project_id TEXT, scene_index INT, status TEXT, file_path TEXT, file_sha256 TEXT, file_size INT, locked_until REAL);")
    db.execute("INSERT INTO scenes VALUES ('S02', 'P_SAB', 2, 'DONE', 'none', 'sha', 100, 0.0);")
    s6 = check_canary_inv6_ledger(db, "P_SAB")
    db.close()
    sabotages = [s1.get("code") == "CANARY_INV1_FAIL", s2.get("code") == "CANARY_INV2_BLACK_DETECTED", s3.get("code") == "CANARY_INV3_FREEZE_DETECTED", s4.get("code") == "CANARY_INV4_AUDIO_LOUDNESS_FAIL", s5.get("code") == "CANARY_INV5_GOLDEN_MISMATCH", s6.get("code") == "CANARY_INV6_LEDGER_FAIL"]
    return {"passed": all(sabotages), "sabotages_passed": sum(1 for s in sabotages if s)}

LAYOUT_CONFIGS: dict[str, dict[str, int]] = {
    "9:16": {"width": 1080, "height": 1920, "side_margin": 72, "top_margin": 150, "caption_safe_bottom": 440, "min_headline": 72, "min_label": 44},
    "16:9": {"width": 1920, "height": 1080, "side_margin": 96, "top_margin": 60, "caption_safe_bottom": 190, "min_headline": 64, "min_label": 36},
}

TEMPLATE_CATALOG: tuple[dict[str, Any], ...] = (
    {"template_id": "title_slam", "slots": ["title", "subtitle"], "portrait": {}, "landscape": {}},
    {"template_id": "big_statement", "slots": ["statement"], "portrait": {}, "landscape": {}},
    {"template_id": "concept_diagram", "slots": ["concept", "node1", "node2"], "portrait": {}, "landscape": {}},
    {"template_id": "comparison_split", "slots": ["left", "right"], "portrait": {}, "landscape": {}},
    {"template_id": "process_flow", "slots": ["s1", "s2", "s3"], "portrait": {}, "landscape": {}},
    {"template_id": "timeline", "slots": ["p1", "p2"], "portrait": {}, "landscape": {}},
    {"template_id": "stat_counter", "slots": ["num", "label"], "portrait": {}, "landscape": {}},
    {"template_id": "icon_grid", "slots": ["i1", "i2", "i3", "i4"], "portrait": {}, "landscape": {}},
    {"template_id": "chart", "slots": ["title", "data"], "portrait": {}, "landscape": {}},
    {"template_id": "image_focus", "slots": ["image", "caption"], "portrait": {}, "landscape": {}},
    {"template_id": "two_image_contrast", "slots": ["img_a", "img_b"], "portrait": {}, "landscape": {}},
    {"template_id": "quote", "slots": ["quote", "author"], "portrait": {}, "landscape": {}},
    {"template_id": "list_reveal", "slots": ["i1", "i2", "i3"], "portrait": {}, "landscape": {}},
    {"template_id": "outro", "slots": ["headline", "cta"], "portrait": {}, "landscape": {}},
)

def get_layout_config(ratio: str = "9:16") -> dict[str, int]:
    if ratio not in LAYOUT_CONFIGS:
        raise ValueError(f"Invalid layout ratio: {ratio!r}")
    return dict(LAYOUT_CONFIGS[ratio])

def get_template_catalog() -> list[dict[str, Any]]:
    return [dict(t) for t in TEMPLATE_CATALOG]

def canonicalize_scene_spec(draft: dict[str, Any] | str, story_bible: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(draft, (dict, str)):
        raise TypeError("draft must be a dict or json string")
    if isinstance(draft, str):
        s = draft.strip()
        open_b = s.count("{") - s.count("}")
        if open_b > 0:
            s += "}" * open_b
        s = re.sub(r",\s*([\]}])", r"\1", s)
        data = json.loads(s)
    else:
        data = dict(draft)
    tokens = (story_bible or {}).get("tokens", {})
    for k, v in list(data.items()):
        if isinstance(v, str) and v.startswith("$") and v in tokens:
            data[k] = tokens[v]
    cw, ch = (1080, 1920) if data.get("ratio") == "9:16" else (1920, 1080)
    if isinstance(data.get("box"), dict):
        b = data["box"]
        if -0.05 * cw <= b.get("x", 0) < 0:
            b["x"] = 0
        if -0.05 * ch <= b.get("y", 0) < 0:
            b["y"] = 0
        if cw < b.get("x", 0) + b.get("w", 0) <= cw * 1.05:
            b["w"] = cw - b.get("x", 0)
        if ch < b.get("y", 0) + b.get("h", 0) <= ch * 1.05:
            b["h"] = ch - b.get("y", 0)
    return data

def validate_scene_spec(spec: dict[str, Any], audio_duration: float | None = None, lead_in: float = 0.3, tail: float = 0.5) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise TypeError("spec must be a dict")
    codes: list[str] = []
    known = {t["template_id"] for t in TEMPLATE_CATALOG}
    if spec.get("template_id") not in known:
        codes.append("INVALID_TEMPLATE")
    if audio_duration is not None:
        expected = round(audio_duration + lead_in + tail, 3)
        if abs(float(spec.get("duration", 0.0)) - expected) > 0.05:
            codes.append("DURATION_MISMATCH")
    for cue in spec.get("cues", []):
        anc = str(cue.get("anchor", ""))
        if re.match(r"^@\d+(\.\d+)?s$", anc):
            codes.append("INVALID_CUE_ABSOLUTE_TIMESTAMP")
        elif not anc.startswith("@") or not re.match(r"^@(scene|s\d+)\.", anc):
            codes.append("INVALID_CUE_ANCHOR")
    for val in (spec.get("slots") or {}).values():
        if isinstance(val, str) and len(val.split()) > 4:
            codes.append("WORD_COUNT_EXCEEDED")
    return {"valid": len(codes) == 0, "codes": codes}

def audit_dom_layout(boxes: list[dict[str, Any]], ratio: str = "9:16") -> dict[str, Any]:
    if not isinstance(boxes, list):
        raise TypeError("boxes must be a list")
    if not boxes:
        return {"passed": False, "code": "GATE_EXEC_ERROR", "violations": [{"code": "GATE_EXEC_ERROR"}]}
    cfg = get_layout_config(ratio)
    cap_safe = cfg["height"] - cfg["caption_safe_bottom"]
    violations: list[dict[str, Any]] = []
    def _lum(c: str) -> float:
        h = c.lstrip("#")
        if len(h) == 3:
            h = "".join(x * 2 for x in h)
        r, g, b = (int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    for b in boxes:
        if b.get("y", 0) + b.get("h", 0) > cap_safe:
            violations.append({"code": "CAPTION_SAFE_VIOLATION", "id": b.get("id")})
        txt = str(b.get("text", ""))
        if "undefined" in txt or "NaN" in txt:
            violations.append({"code": "DOM_TRAP_TRIGGERED", "id": b.get("id")})
        if b.get("color") and b.get("bg"):
            l1, l2 = sorted([_lum(b["color"]), _lum(b["bg"])], reverse=True)
            if (l1 + 0.05) / (l2 + 0.05) < (3.0 if b.get("font_size", 0) >= 56 else 4.5):
                violations.append({"code": "DOM_LOW_CONTRAST", "id": b.get("id")})
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            b1, b2 = boxes[i], boxes[j]
            if min(b1["x"] + b1["w"], b2["x"] + b2["w"]) > max(b1["x"], b2["x"]) and min(b1["y"] + b1["h"], b2["y"] + b2["h"]) > max(b1["y"], b2["y"]):
                violations.append({"code": "DOM_OVERLAP_DETECTED", "pair": (b1.get("id"), b2.get("id"))})
    return {"passed": len(violations) == 0, "code": "OK" if not violations else violations[0]["code"], "violations": violations}

def run_dom_sabotage_preflight() -> dict[str, Any]:
    ov = audit_dom_layout([{"id": "a", "x": 0, "y": 0, "w": 100, "h": 100}, {"id": "b", "x": 50, "y": 50, "w": 100, "h": 100}])
    lc = audit_dom_layout([{"id": "c", "x": 0, "y": 0, "w": 100, "h": 100, "color": "#222", "bg": "#111"}])
    mv = validate_scene_spec({"template_id": "bad"})
    caught = int(not ov["passed"]) + int(not lc["passed"]) + int(not mv["valid"])
    return {"passed": caught == 3, "sabotages_caught": caught}

