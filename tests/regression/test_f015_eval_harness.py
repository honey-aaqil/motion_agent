"""Regression tests for Feature F-015: Evaluation harness and gates (SPEC Section 13)."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from src.pipeline import (
    check_goodhart_guards, compute_judge_calibration, compute_local_visual_metrics,
    compute_wcag_contrast, evaluate_contact_sheet_gate, evaluate_ship_block_gate,
    evaluate_stage1_gate, generate_human_contact_sheet, init_database,
    load_eval_dataset, mcnemar_exact_mid_p, paired_bootstrap_ci,
    record_scene_trial, run_pipeline
)

def test_invalid_inputs_raise_explicit_errors(tmp_path: Path) -> None:
    for f, a in (
        (load_eval_dataset, (123,)), (record_scene_trial, ("not_conn", {})),
        (mcnemar_exact_mid_p, (1, "bad")), (paired_bootstrap_ci, ("bad", [1.0])),
        (evaluate_stage1_gate, ("bad", 0.5, 0)), (evaluate_ship_block_gate, ("bad", 0.0, 0, 0.0)),
        (compute_wcag_contrast, (123, "#000000")), (compute_local_visual_metrics, ("not_list",)),
        (check_goodhart_guards, ("bad", {})), (compute_judge_calibration, ("bad", [1])),
        (evaluate_contact_sheet_gate, ("bad", 0, 0, 0, False)), (generate_human_contact_sheet, ("bad", [], []))
    ):
        with pytest.raises(TypeError):
            f(*a)  # type: ignore[arg-type]
    for exc, f, a in (
        (FileNotFoundError, load_eval_dataset, (tmp_path / "missing.jsonl",)),
        (ValueError, mcnemar_exact_mid_p, (-1, 0)),
        (ValueError, paired_bootstrap_ci, ([1.0], [1.0, 2.0])),
        (ValueError, paired_bootstrap_ci, ([], [])),
        (ValueError, compute_wcag_contrast, ("#12", "#FFF")),
        (ValueError, compute_judge_calibration, ([1, 0], [1]))
    ):
        with pytest.raises(exc):
            f(*a)  # type: ignore[arg-type]

def test_dataset_and_trials_sqlite(tmp_path: Path) -> None:
    d_file = tmp_path / "golden_release_v1.jsonl"
    d_file.write_text("\n".join(json.dumps({"scene_id": f"S{i:02d}", "hard_subset": (i % 2 == 0)}) for i in range(1, 11)) + "\n", encoding="utf-8")
    assert len(load_eval_dataset(d_file)) == 10 and len(load_eval_dataset(d_file, subset="hard")) == 5
    conn = init_database(tmp_path / "test.db")
    try:
        t_id = record_scene_trial(conn, {"run_id": "r1", "scene_id": "S01", "is_baseline": 1, "first_pass_validator_success": 1, "final_acceptance": 1})
        assert isinstance(t_id, int) and t_id > 0
        assert conn.execute("SELECT run_id, is_baseline FROM scene_trials WHERE trial_id = ?", (t_id,)).fetchone() == ("r1", 1)
    finally:
        conn.close()

def test_statistical_gates_and_bootstrap() -> None:
    assert mcnemar_exact_mid_p(0, 0) == 1.0 and mcnemar_exact_mid_p(10, 0) < 0.01 and mcnemar_exact_mid_p(5, 5) == 1.0
    mean_d, lb, ub, var = paired_bootstrap_ci([0.0]*20, [1.0]*20, n_resamples=500, seed=1)
    assert mean_d == 1.0 and lb == 1.0 and ub == 1.0 and var == 0.0
    assert evaluate_stage1_gate(0.9, 0.7, 0)["aborted"] is True and evaluate_stage1_gate(0.9, 0.85, 2)["aborted"] is True and evaluate_stage1_gate(0.9, 0.85, 0)["aborted"] is False
    assert evaluate_ship_block_gate(0.12, 0.02, 0, 0.1) == "SHIP" and evaluate_ship_block_gate(-0.06, -0.1, 0, 0.0) == "BLOCK"
    assert evaluate_ship_block_gate(0.05, -0.01, 2, 0.0) == "BLOCK" and evaluate_ship_block_gate(0.05, -0.01, 0, 0.3) == "BLOCK" and evaluate_ship_block_gate(0.03, -0.02, 0, 0.0) == "NEUTRAL"

def test_local_visual_metrics_and_goodhart() -> None:
    assert compute_wcag_contrast("#FFFFFF", "#000000") >= 20.0 and compute_wcag_contrast("#000000", "#000000") == 1.0
    boxes = [{"id": "b1", "box": [0, 0, 100, 100], "fg_hex": "#FFFFFF", "bg_hex": "#000000"}, {"id": "b2", "box": [50, 50, 100, 100], "fg_hex": "#888888", "bg_hex": "#888888"}]
    res = compute_local_visual_metrics(boxes)
    assert res["overlap_count"] == 1 and res["contrast_passed"] is False and res["clutter_score"] > 0
    assert compute_local_visual_metrics([{"id": "b1", "box": [0, 0, 40, 40], "fg_hex": "#FFFFFF", "bg_hex": "#000000"}])["overlap_count"] == 0
    w = check_goodhart_guards({"mean_words_per_slot": 10.0}, {"mean_words_per_slot": 7.0, "top_assets_share": 0.35})
    assert len(w) == 2 and check_goodhart_guards({"mean_words_per_slot": 10.0}, {"mean_words_per_slot": 9.5, "top_assets_share": 0.2}) == []

def test_judge_calibration_and_contact_sheet() -> None:
    gt, preds = [1]*10 + [0]*10, [1]*10 + [0]*10
    calib = compute_judge_calibration(gt, preds, swapped_preds=preds)
    assert calib["sensitivity"] == 1.0 and calib["specificity"] == 1.0 and calib["kappa"] == 1.0 and calib["passed"] is True
    assert compute_judge_calibration(gt, [0]*10 + [1]*10)["passed"] is False
    html = generate_human_contact_sheet([{"id": "d1"}], [{"id": "c1"}], [{"id": "h1"}])
    assert "<table" in html and "d1" in html and "h1" in html
    assert evaluate_contact_sheet_gate(1, 5, 0, 0, False)["blocked"] is True and evaluate_contact_sheet_gate(2, 0, 3, 0, False)["blocked"] is True
    assert evaluate_contact_sheet_gate(2, 0, 0, 2, False)["blocked"] is True and evaluate_contact_sheet_gate(2, 0, 0, 0, True)["blocked"] is True and evaluate_contact_sheet_gate(5, 2, 0, 0, False)["blocked"] is False

def test_pipeline_eval_wiring(tmp_path: Path) -> None:
    out = run_pipeline(tmp_path, {"project_id": "p8_eval", "run_eval_harness": True})
    assert out.get("eval_harness", {}).get("status") == "EVALUATED" and "stage1" in out["eval_harness"]

