"""Regression tests for Feature F-018: Visual critic (shadow) and low-quota mode (SPEC 5.1, 6)."""
from __future__ import annotations
from pathlib import Path
import pytest
from src.pipeline import (
    build_visual_critic_montage, build_visual_critic_prompt, parse_visual_critic_response,
    record_visual_critic_review, evaluate_visual_critic_promotion, check_visual_critic_eligibility,
    should_activate_low_quota_mode, build_low_quota_scene_author_prompt,
    parse_low_quota_scene_author_response, evaluate_low_quota_golden_set, init_database, run_pipeline
)

def test_invalid_inputs_raise_explicit_errors(tmp_path: Path) -> None:
    conn = init_database(tmp_path / "test_f018_err.db")
    try:
        for f, a in (
            (build_visual_critic_montage, ("not_list",)), (build_visual_critic_montage, ([{"scene_id": "S1"}], 123)),
            (build_visual_critic_prompt, ("not_dict",)), (build_visual_critic_prompt, ({}, 123)),
            (parse_visual_critic_response, (123,)), (parse_visual_critic_response, ("{}", "not_bool")),
            (record_visual_critic_review, ("not_conn", "S01", {})), (record_visual_critic_review, (conn, 123, {})),
            (record_visual_critic_review, (conn, "S01", "not_dict")), (evaluate_visual_critic_promotion, ("not_dict",)),
            (check_visual_critic_eligibility, ("bad", 10)), (check_visual_critic_eligibility, (0.5, "bad")),
            (should_activate_low_quota_mode, ("bad",)), (should_activate_low_quota_mode, (10, "bad")),
            (build_low_quota_scene_author_prompt, ("not_list", {}, {})), (build_low_quota_scene_author_prompt, ([{"id": "S1"}, {"id": "S2"}], "bad", {})),
            (parse_low_quota_scene_author_response, (123, ["S01", "S02"])), (parse_low_quota_scene_author_response, ("[]", "not_list")),
            (evaluate_low_quota_golden_set, ("not_list", [])), (evaluate_low_quota_golden_set, ([], "not_list")),
        ):
            with pytest.raises(TypeError): f(*a)  # type: ignore[arg-type]

        for f, a in (
            (build_visual_critic_montage, ([],)), (build_visual_critic_montage, ([{"scene_id": "S1"}] * 5,)),
            (record_visual_critic_review, (conn, "   ", {})), (evaluate_visual_critic_promotion, ({},)),
            (check_visual_critic_eligibility, (-0.1, 10)), (check_visual_critic_eligibility, (1.5, 10)),
            (build_low_quota_scene_author_prompt, ([{"id": "S1"}], {}, {})), (parse_low_quota_scene_author_response, ("[]", [])),
            (parse_low_quota_scene_author_response, ('{"scenes": [{"scene_id": "S01"}]}', ["S01", "S02"])),
        ):
            with pytest.raises(ValueError): f(*a)  # type: ignore[arg-type]
    finally: conn.close()

def test_visual_critic_montage_and_prompt() -> None:
    m = build_visual_critic_montage([{"scene_id": "S01", "frame_pct": 50}, {"scene_id": "S02", "frame_pct": 50}], grid_size=(6, 6))
    assert m["grid"] == "6x6" and len(m["quadrants"]) == 2 and m["scene_ids"] == ["S01", "S02"] and m["quadrants"][0]["scene_id"] == "S01"
    prompt = build_visual_critic_prompt(m)
    assert "visual_critic" in prompt and "6x6" in prompt and "S01" in prompt

def test_visual_critic_parse_and_record(tmp_path: Path) -> None:
    rep = parse_visual_critic_response('{"reviews": {"S01": {"verdict": "FAIL", "score": 4.5, "issues": ["overlap"]}}}', is_shadow=True)
    assert rep["status"] == "judged" and rep["is_shadow"] is True and rep["blocks_pipeline"] is False and rep["reviews"]["S01"]["verdict"] == "FAIL"
    unjudged = parse_visual_critic_response("malformed json {", is_shadow=True)
    assert unjudged["status"] == "unjudged" and unjudged["blocks_pipeline"] is False
    conn = init_database(tmp_path / "vc.db")
    try:
        conn.execute("INSERT INTO projects VALUES ('P1', 'T', 'VIDEO_NEW', 1.0, 1.0);")
        conn.execute("INSERT INTO scenes (scene_id, project_id, scene_index, status, calls_used, locked_until, updated_at) VALUES ('S01', 'P1', 1, 'DONE', 1, 0.0, 1.0);")
        conn.commit()
        assert record_visual_critic_review(conn, "S01", rep, is_shadow=True) is True
        row = conn.execute("SELECT status, vlm_review_json FROM scenes WHERE scene_id = 'S01';").fetchone()
        assert row[0] == "DONE" and "overlap" in row[1]
    finally: conn.close()

def test_visual_critic_promotion_and_eligibility() -> None:
    pass_promo = evaluate_visual_critic_promotion({"sensitivity": 0.88, "specificity": 0.90, "position_swap_flip_rate": 0.03})
    assert pass_promo["eligible_for_promotion"] is True and pass_promo["shadow_mode"] is False
    fail_promo = evaluate_visual_critic_promotion({"sensitivity": 0.80, "specificity": 0.90, "position_swap_flip_rate": 0.08})
    assert fail_promo["eligible_for_promotion"] is False and len(fail_promo["reasons"]) == 2
    el1 = check_visual_critic_eligibility(first_pass_success_rate=0.85, daily_quota_headroom=10)
    assert el1["eligible"] is True and el1["priority"] == 0
    el_disabled = check_visual_critic_eligibility(first_pass_success_rate=0.92, daily_quota_headroom=10)
    assert el_disabled["eligible"] is False and "above_88" in el_disabled["reason"]
    el_no_quota = check_visual_critic_eligibility(first_pass_success_rate=0.80, daily_quota_headroom=2, min_quota_headroom=5)
    assert el_no_quota["eligible"] is False and "quota" in el_no_quota["reason"]

def test_low_quota_mode_and_golden_set() -> None:
    assert should_activate_low_quota_mode(remaining_quota=20, threshold=25) is True and should_activate_low_quota_mode(remaining_quota=30, threshold=25) is False
    assert should_activate_low_quota_mode(remaining_quota=30, manual_override=True) is True
    beats = [{"id": "S01", "entities": ["chart"]}, {"id": "S02", "entities": ["globe"]}]
    prompt = build_low_quota_scene_author_prompt(beats, {"palette": []}, {})
    assert "S01" in prompt and "S02" in prompt and "2 scenes" in prompt
    raw_resp = '[{"scene_id": "S01", "template_id": "t1", "slots": {"title": "chart"}}, {"scene_id": "S02", "template_id": "t2", "slots": {"title": "globe"}}]'
    parsed = parse_low_quota_scene_author_response(raw_resp, ["S01", "S02"])
    assert len(parsed) == 2 and parsed[0]["scene_id"] == "S01" and parsed[1]["scene_id"] == "S02"
    eval_res = evaluate_low_quota_golden_set(parsed, beats)
    assert eval_res["passed"] is True and eval_res["coverage_ratio"] == 1.0

def test_run_pipeline_integration(tmp_path: Path) -> None:
    res = run_pipeline(tmp_path, {"project_id": "P18_INT", "run_visual_critic_and_low_quota": True})
    assert "visual_critic_and_low_quota" in res and res["visual_critic_and_low_quota"]["status"] == "READY"
    assert res["visual_critic_and_low_quota"]["montage_scenes"] == 2 and res["visual_critic_and_low_quota"]["low_quota_active"] is True

