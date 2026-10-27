"""Regression tests for Phase P1 / Feature F-007: Mock Gemini chaos server."""
from __future__ import annotations
from pathlib import Path
import pytest
from src.pipeline import (
    acquire_scene_lease, check_rate_governor, compute_llm_backoff,
    call_gemini_gateway, init_database, reclaim_expired_leases,
    run_pipeline, start_gemini_chaos_server, stop_gemini_chaos_server,
    transition_scene_state,
)

def test_compute_llm_backoff() -> None:
    for bad in ("bad", True, [1]):
        with pytest.raises(TypeError): compute_llm_backoff(bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError): compute_llm_backoff(-1)
    assert compute_llm_backoff(0, rng_jitter=0.5) == 1.5
    assert compute_llm_backoff(1, rng_jitter=1.0) == 3.0
    assert compute_llm_backoff(2, rng_jitter=0.0) == 4.0
    assert compute_llm_backoff(10, rng_jitter=0.0) == 120.0
    assert 1.0 <= compute_llm_backoff(0) <= 4.0

def test_mock_gemini_server_and_gateway_modes(tmp_path: Path) -> None:
    with pytest.raises(ValueError): start_gemini_chaos_server(port=-1)
    with pytest.raises(TypeError): stop_gemini_chaos_server("srv", "th")  # type: ignore[arg-type]
    for b_url, prompt, m_id in (("ftp://bad", "test", "m"), ("http://x", "   ", "m"), ("http://x", "p", "  ")):
        with pytest.raises(ValueError): call_gemini_gateway(b_url, prompt, model_id=m_id)
    for b_url, prompt, m_id in (("http://x", 123, "m"), ("http://x", "p", 123)):
        with pytest.raises(TypeError): call_gemini_gateway(b_url, prompt, model_id=m_id)  # type: ignore[arg-type]

    srv, th, base_url = start_gemini_chaos_server(mode="ok")
    conn = init_database(tmp_path / "chaos.db")
    try:
        r_ok = call_gemini_gateway(base_url, "hello", model_id="gemini-2.5-flash", conn=conn, project_id="p1")
        assert r_ok["status"] == 200 and r_ok["valid"] is True and r_ok["model_version"] == "gemini-2.5-flash"
        r_503 = call_gemini_gateway(base_url, "hello", chaos_mode="503_storm", conn=conn, project_id="p1")
        assert r_503["status"] == 503 and r_503["retryable"] is True and r_503["error"] == "503_OVERLOAD"
        assert conn.cursor().execute("SELECT COUNT(*) FROM api_rate_ledger;").fetchone()[0] == 1
        r_429m = call_gemini_gateway(base_url, "hello", chaos_mode="429_minute", conn=conn, project_id="p1")
        assert r_429m["status"] == 429 and r_429m["retryable"] is True and r_429m["wait_sec"] == 62.0
        r_429d = call_gemini_gateway(base_url, "hello", chaos_mode="429_day", conn=conn, project_id="p1")
        assert r_429d["status"] == 429 and r_429d["retryable"] is False and r_429d["error"] == "QUOTA_SLEEP_UNTIL_RESET"
        r_trunc = call_gemini_gateway(base_url, "hello", chaos_mode="truncated_json")
        assert r_trunc["status"] == 200 and r_trunc["valid"] is False and r_trunc["error"] == "unparseable_output"
        r_empty = call_gemini_gateway(base_url, "hello", chaos_mode="empty_200")
        assert r_empty["status"] == 200 and r_empty["valid"] is False and r_empty["error"] == "empty_response"
        r_slow_to = call_gemini_gateway(base_url, "hello", chaos_mode="slow_response", timeout=0.05, conn=conn, project_id="p1")
        assert r_slow_to["status"] == 504 and r_slow_to["retryable"] is True and r_slow_to["error"] == "TIMEOUT"
        r_slow_ok = call_gemini_gateway(base_url, "hello", chaos_mode="slow_response", timeout=1.5, conn=conn, project_id="p1")
        assert r_slow_ok["status"] == 200 and r_slow_ok["valid"] is True
        with pytest.raises(ValueError, match="Model version mismatch"):
            call_gemini_gateway(base_url, "hello", chaos_mode="wrong_model_version", model_id="gemini-2.5-flash")
    finally:
        conn.close()
        assert stop_gemini_chaos_server(srv, th) is True

def test_full_state_machine_chaos_replay(tmp_path: Path) -> None:
    conn = init_database(tmp_path / "replay.db")
    try:
        t0 = 1000.0
        conn.execute("INSERT INTO projects VALUES ('p1', 't', 'NEW', ?, ?);", (t0, t0))
        conn.execute("INSERT INTO scenes (scene_id, project_id, scene_index, status, calls_used, locked_until, updated_at) VALUES ('S01', 'p1', 1, 'SCENE_READY', 0, 0.0, ?);", (t0,))
        conn.commit()
        assert acquire_scene_lease(conn, "S01", "w1", lease_sec=90.0, now=t0) is True
        transition_scene_state(conn, "S01", "DRAFT_AUTHORED", calls_increment=1)
        transition_scene_state(conn, "S01", "CANONICALIZED")
        assert conn.cursor().execute("SELECT calls_used FROM scenes WHERE scene_id = 'S01';").fetchone()[0] == 1
        assert check_rate_governor(conn, now_monotonic=20.0, last_call_monotonic=0.0, now_wall=t0, daily_quota_cap=0)["action"] == "QUOTA_SLEEP_UNTIL_RESET"
        assert check_rate_governor(conn, now_monotonic=20.0, last_call_monotonic=0.0, now_wall=t0 + 86401.0, daily_quota_cap=20)["allowed"] is True
        transition_scene_state(conn, "S01", "NEEDS_HUMAN_EDIT")
        transition_scene_state(conn, "S01", "SCENE_READY")
        assert acquire_scene_lease(conn, "S01", "w_dead", lease_sec=90.0, now=t0) is True
        assert reclaim_expired_leases(conn, now=t0 + 95.0) == 1
        assert conn.cursor().execute("SELECT status, calls_used FROM scenes WHERE scene_id = 'S01';").fetchone() == ("SCENE_READY", 1)
        assert acquire_scene_lease(conn, "S01", "w_live", lease_sec=90.0, now=t0 + 96.0) is True
        transition_scene_state(conn, "S01", "DRAFT_AUTHORED", calls_increment=1)
        transition_scene_state(conn, "S01", "CANONICALIZED")
        transition_scene_state(conn, "S01", "VALIDATED")
        transition_scene_state(conn, "S01", "SCENE_ACCEPTED")
        assert conn.cursor().execute("SELECT calls_used, status FROM scenes WHERE scene_id = 'S01';").fetchone() == (2, "SCENE_ACCEPTED")
    finally:
        conn.close()

def test_pipeline_wiring_chaos(tmp_path: Path) -> None:
    res = run_pipeline(tmp_path, {"project_id": "P1_CHAOS", "run_chaos_server": True})
    assert res["chaos"]["status"] == "READY"
