"""Regression tests for Phase P1 / Feature F-006: Rate governor and gateway."""
from __future__ import annotations
from pathlib import Path
import pytest
from src.pipeline import (
    assert_model_version, check_rate_governor, complete_llm_request,
    enqueue_llm_request, fail_llm_request, format_llm_status_display,
    init_database, log_llm_call, pop_next_llm_request,
    record_api_call, run_pipeline,
)

def test_rate_governor_interval_and_daily_cap(tmp_path: Path) -> None:
    conn = init_database(tmp_path / "gov.db")
    try:
        with pytest.raises(TypeError):
            record_api_call(conn, 123, "gemini-2.5-flash", 200)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            record_api_call(conn, "", "gemini-2.5-flash", 200)
        with pytest.raises(ValueError):
            record_api_call(conn, "p1", "gemini-2.5-flash", 99)

        cid = record_api_call(conn, "p1", "gemini-2.5-flash", 200, created_at=100.0)
        assert cid > 0

        chk1 = check_rate_governor(conn, now_monotonic=10.0, last_call_monotonic=0.0, now_wall=100.0, daily_quota_cap=20)
        assert chk1["allowed"] is False and chk1["action"] == "wait_rate_limit" and chk1["wait_sec"] == 5.5

        chk2 = check_rate_governor(conn, now_monotonic=16.0, last_call_monotonic=0.0, now_wall=100.0, daily_quota_cap=20)
        assert chk2["allowed"] is True and chk2["wait_sec"] == 0.0

        chk3 = check_rate_governor(conn, now_monotonic=20.0, last_call_monotonic=0.0, now_wall=100.0, daily_quota_cap=1)
        assert chk3["allowed"] is False and chk3["action"] == "QUOTA_SLEEP_UNTIL_RESET"
    finally:
        conn.close()

def test_gateway_queue_priority_and_idempotency(tmp_path: Path) -> None:
    conn = init_database(tmp_path / "gw.db")
    try:
        with pytest.raises(ValueError):
            enqueue_llm_request(conn, "p1", "   ", task="scene_author", priority=1)

        req1 = enqueue_llm_request(conn, "p1", "prompt A", task="batch_task", priority=1, now=10.0)
        assert isinstance(req1, str) and len(req1) > 0
        req1_dup = enqueue_llm_request(conn, "p1", "prompt A", task="batch_task", priority=1, now=11.0)
        assert req1 == req1_dup

        req2 = enqueue_llm_request(conn, "p1", "prompt B", task="editor_task", priority=10, now=12.0)
        assert isinstance(req2, str) and len(req2) > 0

        first_pop = pop_next_llm_request(conn)
        assert first_pop is not None and first_pop["request_id"] == req2 and first_pop["priority"] == 10

        second_pop = pop_next_llm_request(conn)
        assert second_pop is not None and second_pop["request_id"] == req1

        assert complete_llm_request(conn, req2, '{"result": "ok"}') is True
        assert fail_llm_request(conn, req1, "timeout") is True
        assert pop_next_llm_request(conn) is None
    finally:
        conn.close()

def test_model_version_assertion_and_logging(tmp_path: Path) -> None:
    conn = init_database(tmp_path / "log.db")
    try:
        with pytest.raises(ValueError, match="Model version mismatch"):
            assert_model_version("gemini-2.0-flash", "gemini-2.5-flash")
        with pytest.raises(TypeError):
            assert_model_version(123, "gemini-2.5-flash")  # type: ignore[arg-type]
        assert assert_model_version("gemini-2.5-flash", "gemini-2.5-flash") is True

        with pytest.raises(ValueError):
            log_llm_call(conn, "p1", "m", "task", 200, -1.0, 1)

        lid = log_llm_call(conn, "p1", "gemini-2.5-flash", "scene_author", 503, 120.0, 1, error_code="503_OVERLOAD")
        assert lid > 0

        disp = format_llm_status_display("waiting_llm", retry_num=2, next_try_sec=15.5)
        assert "waiting for LLM (retry 2, next try in 15.5 s)" in disp
    finally:
        conn.close()

def test_pipeline_wiring_gateway(tmp_path: Path) -> None:
    res = run_pipeline(tmp_path, {"project_id": "P1_GW", "run_gateway": True})
    assert res["gateway"]["status"] == "READY"

