"""Regression tests for Feature F-016: Dashboard, watchdog, auto-start (SPEC Sections 11, 12)."""
from __future__ import annotations
from pathlib import Path
import pytest
from src.pipeline import (
    check_watchdog_conditions, evaluate_alert_throttling,
    generate_autostart_task_cmd, get_machine_health, init_database,
    render_dashboard_html, run_pipeline, run_watchdog_observer,
    schedule_dead_man_switch
)

def test_invalid_inputs_raise_explicit_errors() -> None:
    for f, a in (
        (get_machine_health, (123,)), (render_dashboard_html, ("bad", [], {})),
        (render_dashboard_html, ({}, "bad", {})), (render_dashboard_html, ({}, [], "bad")),
        (check_watchdog_conditions, ("bad",)), (evaluate_alert_throttling, (123, {}, 0.0)),
        (evaluate_alert_throttling, ("c", "bad", 0.0)), (evaluate_alert_throttling, ("c", {}, "bad")),
        (schedule_dead_man_switch, (123,)), (generate_autostart_task_cmd, (123, "cmd")),
        (generate_autostart_task_cmd, ("task", 123)), (run_watchdog_observer, (123, "out.html")),
        (run_watchdog_observer, ("db.db", 123))
    ):
        with pytest.raises(TypeError):
            f(*a)  # type: ignore[arg-type]

def test_machine_health_and_dashboard_render(tmp_path: Path) -> None:
    db_p = tmp_path / "health_test.db"
    conn = init_database(db_p)
    conn.close()
    health = get_machine_health(db_p)
    assert isinstance(health, dict) and health["available_ram_mb"] > 0 and health["free_disk_gb"] > 0
    assert "process_tree_ram_mb" in health and "wal_size_mb" in health
    html = render_dashboard_html(
        {"project_id": "P01", "title": "Test Explainer", "preset": "EN"},
        [{"scene_id": "S01", "status": "DONE"}], health,
        action_needed=[{"scene_id": "S02", "issue": "Human edit needed"}]
    )
    assert isinstance(html, str) and "<!DOCTYPE html>" in html and "Motion Agent Dashboard" in html
    assert "Test Explainer" in html and "Human edit needed" in html

def test_watchdog_conditions_and_throttling(tmp_path: Path) -> None:
    db_p = tmp_path / "cond_test.db"
    conn = init_database(db_p)
    now_ts = 10000.0
    conn.execute("INSERT OR REPLACE INTO projects VALUES ('P01', 'T', 'VIDEO_NEW', ?, ?)", (now_ts, now_ts))
    conn.execute("INSERT OR REPLACE INTO scenes (scene_id, project_id, scene_index, status, calls_used, locked_until, updated_at) VALUES ('S01', 'P01', 1, 'IN_PROGRESS', 1, ?, ?)", (now_ts - 200.0, now_ts))
    for _ in range(15):
        conn.execute("INSERT INTO llm_log (project_id, model_id, task, status_code, latency_ms, attempt, error_code, created_at) VALUES ('P01', 'm', 'author', 503, 100.0, 1, '503', ?)", (now_ts,))
    conn.commit()
    alerts = check_watchdog_conditions({"free_disk_gb": 5.0, "available_ram_mb": 400.0, "wal_size_mb": 150.0}, conn=conn, now=now_ts)
    conn.close()
    assert "free_disk_under_10gb" in alerts and "ram_under_600mb" in alerts and "wal_over_128mb" in alerts
    assert "expired_lease" in alerts and "consecutive_llm_errors" in alerts
    log: dict[str, float] = {}
    assert evaluate_alert_throttling("disk_low", log, now=1000.0, cooldown_sec=14400.0) is True
    assert evaluate_alert_throttling("disk_low", log, now=2000.0, cooldown_sec=14400.0) is False
    assert evaluate_alert_throttling("disk_low", log, now=16000.0, cooldown_sec=14400.0) is True

def test_dead_man_switch_and_autostart_cmd() -> None:
    s_res = schedule_dead_man_switch("alerts_topic", delay_sec=900, cancel=False)
    assert s_res["status"] == "SCHEDULED" and s_res["delay_sec"] == 900
    c_res = schedule_dead_man_switch("alerts_topic", cancel=True)
    assert c_res["status"] == "CANCELLED"
    m_cmd = generate_autostart_task_cmd("MotionAgentWatchdog", "python scripts/watchdog_observer.py", interval_min=5)
    assert 'schtasks /Create /SC MINUTE /MO 5 /TN "MotionAgentWatchdog"' in m_cmd
    l_cmd = generate_autostart_task_cmd("MotionAgentResume", "python scripts/run.py", on_logon=True)
    assert '/SC ONLOGON /TN "MotionAgentResume"' in l_cmd

def test_watchdog_observer_and_pipeline(tmp_path: Path) -> None:
    db_p, out_h, log_p = tmp_path / "obs.db", tmp_path / "status.html", tmp_path / "last_alert.json"
    conn = init_database(db_p)
    conn.execute("INSERT OR REPLACE INTO projects VALUES ('P01', 'Obs Vid', 'VIDEO_NEW', 1.0, 1.0)")
    conn.commit()
    conn.close()
    obs_res = run_watchdog_observer(db_p, out_h, alert_log_path=log_p, push_topic="obs_test")
    assert obs_res["status"] == "OK" and out_h.is_file() and "Motion Agent Status" in out_h.read_text(encoding="utf-8")
    pipe_res = run_pipeline(tmp_path, {"project_id": "P_OBS", "run_dashboard_watchdog": True})
    assert pipe_res["dashboard_watchdog"]["status"] == "READY"
