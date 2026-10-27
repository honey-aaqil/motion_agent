"""Regression tests for Phase P0 / Feature F-004: Gemini diagnostics, quota, and 503 load test."""
from __future__ import annotations
from pathlib import Path
import pytest
from src.pipeline import (
    classify_gemini_status, compute_backoff_delay, run_503_load_simulation,
    run_gemini_diagnostics, run_pipeline, validate_gemini_config,
)

def test_gemini_config_validation_and_rejections() -> None:
    with pytest.raises(TypeError):
        validate_gemini_config("not_a_dict")  # type: ignore[arg-type]
    for bad in ({"max_output_tokens": 0}, {"thinking_level": "bad"}, {"temperature": 3.0}, {"min_interval_sec": -1}):
        with pytest.raises(ValueError):
            validate_gemini_config(bad)
    valid = validate_gemini_config({"model_id": "gemini-2.5-flash", "daily_quota_cap": 20})
    assert valid["model_id"] == "gemini-2.5-flash" and valid["max_output_tokens"] == 8192 and valid["daily_quota_cap"] == 20

def test_backoff_jitter_and_rejections() -> None:
    with pytest.raises(TypeError):
        compute_backoff_delay("1")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        compute_backoff_delay(-1)
    with pytest.raises(ValueError):
        compute_backoff_delay(1, jitter=-0.5)
    assert compute_backoff_delay(0, jitter=1.5) == 2.5 and compute_backoff_delay(1, jitter=0.5) == 2.5
    assert compute_backoff_delay(7, jitter=10.0, max_delay=120.0) == 120.0

def test_gemini_status_classification_and_rejections() -> None:
    with pytest.raises(TypeError):
        classify_gemini_status("200")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        classify_gemini_status(99)
    assert classify_gemini_status(200) == {"consume_call": True, "action": "success"}
    assert classify_gemini_status(503, consecutive_503=2)["action"] == "retry_with_backoff"
    assert classify_gemini_status(503, consecutive_503=5, fallback_models=["m-pro"])["action"] == "switch_fallback"
    assert classify_gemini_status(503, consecutive_503=5, fallback_models=[])["action"] == "pause_queue"
    assert classify_gemini_status(429, is_daily_quota=True)["action"] == "quota_sleep_until_reset"
    assert classify_gemini_status(400) == {"consume_call": True, "action": "repair"}
    assert classify_gemini_status(404) == {"consume_call": False, "action": "fail_loud"}

def test_load_simulation_and_pipeline_wiring(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_503_load_simulation([])
    with pytest.raises(TypeError):
        run_503_load_simulation(["bad"])  # type: ignore[list-item]
    samples = [{"status_code": 503, "latency_ms": 1200.0, "thoughts_tokens": 0, "output_tokens": 0} for _ in range(12)]
    samples += [{"status_code": 200, "latency_ms": 800.0, "thoughts_tokens": 300, "output_tokens": 500} for _ in range(18)]
    metrics = run_503_load_simulation(samples)
    assert metrics["total_requests"] == 30 and metrics["overload_rate_503"] == 40.0 and metrics["latency_p50_ms"] >= 800.0
    diag = run_gemini_diagnostics({"daily_quota_cap": 20}, sample_results=samples)
    assert diag["status"] == "DIAGNOSTICS_READY" and "simulation" in diag
    out = run_pipeline(tmp_path, {"project_id": "P0_GEMINI", "run_gemini_diag": True})
    assert out["gemini"]["status"] == "DIAGNOSTICS_READY"

