"""Regression tests for Phase P1 / Feature F-005: SQLite schema, state machine, and leases."""
from __future__ import annotations
from pathlib import Path
import pytest, sqlite3
from src.pipeline import (
    acquire_scene_lease, classify_error_routing, init_database,
    reclaim_expired_leases, release_scene_lease, renew_scene_lease,
    run_pipeline, transition_scene_state,
)

def test_init_database_and_schema_pragmas(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        init_database(12345)  # type: ignore[arg-type]
    conn = init_database(tmp_path / "app.db")
    try:
        cur = conn.cursor()
        exp_jm = "wal" if sqlite3.sqlite_version_info >= (3, 50, 7) else "truncate"
        assert str(cur.execute("PRAGMA journal_mode;").fetchone()[0]).lower() == exp_jm
        assert int(cur.execute("PRAGMA foreign_keys;").fetchone()[0]) == 1
        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
        for t in ("projects", "scenes", "scene_attempts", "api_rate_ledger", "editor_events"):
            assert t in tables
    finally:
        conn.close()

def test_scene_state_transitions_and_rejections(tmp_path: Path) -> None:
    conn = init_database(tmp_path / "trans.db")
    try:
        conn.execute("INSERT INTO projects VALUES ('p1', 'P1', 'VIDEO_NEW', 1.0, 1.0);")
        conn.execute("INSERT INTO scenes (scene_id, project_id, scene_index, status, calls_used, locked_until, updated_at) VALUES ('S01', 'p1', 1, 'SCENE_READY', 0, 0.0, 1.0);")
        conn.commit()
        with pytest.raises(ValueError, match="Illegal state transition"):
            transition_scene_state(conn, "S01", "SCENE_ACCEPTED")
        with pytest.raises(ValueError, match="Scene not found"):
            transition_scene_state(conn, "S99", "IN_PROGRESS")
        assert transition_scene_state(conn, "S01", "IN_PROGRESS") == "IN_PROGRESS"
        assert transition_scene_state(conn, "S01", "DRAFT_AUTHORED", calls_increment=1) == "DRAFT_AUTHORED"
        assert transition_scene_state(conn, "S01", "CANONICALIZED") == "CANONICALIZED"
        assert transition_scene_state(conn, "S01", "DRAFT_AUTHORED", calls_increment=1) == "DRAFT_AUTHORED"
        with pytest.raises(ValueError, match="MAX_LLM_CALLS_PER_SCENE exceeded"):
            transition_scene_state(conn, "S01", "CANONICALIZED", calls_increment=1)
    finally:
        conn.close()

def test_lease_lifecycle_and_reclaim(tmp_path: Path) -> None:
    conn = init_database(tmp_path / "lease.db")
    try:
        conn.execute("INSERT INTO projects VALUES ('p1', 'P1', 'VIDEO_NEW', 1.0, 1.0);")
        conn.execute("INSERT INTO scenes (scene_id, project_id, scene_index, status, calls_used, locked_until, updated_at) VALUES ('S01', 'p1', 1, 'SCENE_READY', 0, 0.0, 1.0);")
        conn.commit()
        assert acquire_scene_lease(conn, "S01", "w1", lease_sec=90.0, now=100.0) is True
        assert acquire_scene_lease(conn, "S01", "w2", lease_sec=90.0, now=120.0) is False
        assert renew_scene_lease(conn, "S01", "w2", lease_sec=90.0, now=130.0) is False
        assert renew_scene_lease(conn, "S01", "w1", lease_sec=90.0, now=130.0) is True
        assert reclaim_expired_leases(conn, now=150.0) == 0
        assert reclaim_expired_leases(conn, now=230.0) == 1
        assert acquire_scene_lease(conn, "S01", "w2", lease_sec=90.0, now=231.0) is True
        assert release_scene_lease(conn, "S01", "w2") is True
    finally:
        conn.close()

def test_error_routing_and_rejections() -> None:
    with pytest.raises(TypeError):
        classify_error_routing("bad", 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        classify_error_routing([], -1)
    assert classify_error_routing([], 2)["route"] == "NEEDS_HUMAN_EDIT"
    assert classify_error_routing([{"element_id": "t"}], 1)["route"] == "LOCAL_REPAIR"
    assert classify_error_routing([{"type": "box_collision", "count": 2}], 0)["route"] == "GLOBAL_RESTART"
    assert classify_error_routing([{"element_id": f"e{i}"} for i in range(3)], 0)["route"] == "GLOBAL_RESTART"
    assert classify_error_routing([{"type": "unparseable_output"}], 0)["route"] == "GLOBAL_RESTART"

def test_pipeline_wiring_state_machine(tmp_path: Path) -> None:
    res = run_pipeline(tmp_path, {"project_id": "P1_SM", "run_state_machine": True})
    assert res["state_machine"]["status"] == "READY"

