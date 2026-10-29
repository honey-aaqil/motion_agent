"""Regression tests for Feature F-014: StoryBible, Scene Author, repair/restart routing (SPEC 5, 6)."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from src.pipeline import (
    build_repair_or_restart_prompt, build_scene_author_prompt, build_story_bible_prompt,
    create_default_story_bible, evaluate_thinking_step_down, extract_scene_exit_state,
    init_database, record_scene_attempt, run_pipeline, validate_repair_entity_retention
)

def test_invalid_inputs_raise_explicit_errors(tmp_path: Path) -> None:
    for f, a in ((create_default_story_bible, (123,)), (build_story_bible_prompt, (12345,)), (extract_scene_exit_state, ("bad",)), (build_scene_author_prompt, ("bad", {}, {})), (validate_repair_entity_retention, ("bad", {}, {})), (evaluate_thinking_step_down, ("bad",)), (record_scene_attempt, ("not_conn", "S01", "p1", 1, "h", "r", {}, {}, {}))):
        with pytest.raises(TypeError):
            f(*a)  # type: ignore[arg-type]
    with pytest.raises((TypeError, ValueError)):
        build_story_bible_prompt("")
    with pytest.raises(ValueError):
        extract_scene_exit_state({})
    with pytest.raises(ValueError):
        build_scene_author_prompt({}, {}, {})
    with pytest.raises(ValueError, match="Invalid route"):
        build_repair_or_restart_prompt("UNKNOWN_ROUTE", {}, [], {}, {}, {})
    with pytest.raises(TypeError):
        build_repair_or_restart_prompt("LOCAL_REPAIR", "not_dict", [], {}, {}, {})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Invalid current_level"):
        evaluate_thinking_step_down([], current_level="ultra")

def test_story_bible_and_exit_state() -> None:
    sb = create_default_story_bible()
    assert sb["tokens"]["$bg_hex"] == "#0B0F19" and sb["type_scale"]["heading_size"] == 72 and len(sb["motifs"]) >= 1
    p_bible = build_story_bible_prompt("Black hole explainer", catalog_ids=["title_slam", "quote"])
    assert "Black hole explainer" in p_bible and "title_slam" in p_bible
    spec = {"template_id": "concept_diagram", "entities": [{"id": "star", "box": [0, 0, 1, 1]}], "transition_out": "fade"}
    exit_state = extract_scene_exit_state(spec)
    assert exit_state["template_id"] == "concept_diagram" and exit_state["transition_out"] == "fade" and len(exit_state["persistent_entities"]) == 1 and len(json.dumps(exit_state).split()) <= 80

def test_scene_author_and_repair_restart_routing() -> None:
    sb, beat = create_default_story_bible(), {"id": "S01", "onscreen_text": ["Star"], "vo": {"en": "Star forms."}, "entities": ["star", "gravity"]}
    p_author = build_scene_author_prompt(beat, sb, asset_map={"star": "star.png"}, prev_exit_state={"template_id": "outro"})
    assert "S01" in p_author and "star.png" in p_author and "outro" in p_author
    p_repair = build_repair_or_restart_prompt("LOCAL_REPAIR", {"slots": {"t": "bad"}}, [{"type": "text_overflow", "element_id": "t"}], beat, sb, {})
    assert "LOCAL_REPAIR" in p_repair and "text_overflow" in p_repair and "t" in p_repair
    p_restart = build_repair_or_restart_prompt("GLOBAL_RESTART", {"secret": "omit_me"}, [{"type": "collision", "count": 2}], beat, sb, {})
    assert "GLOBAL_RESTART" in p_restart and "collision" in p_restart and "omit_me" not in p_restart

def test_repair_retention_and_thinking_step_down() -> None:
    beat = {"id": "S01", "entities": ["star", "gravity"], "vo": {"en": "Star collapses into a black hole."}}
    att1 = {"slots": {"t": "star and gravity"}, "entities": ["star", "gravity"]}
    assert validate_repair_entity_retention(att1, {"slots": {"t": "none"}, "entities": []}, beat)["passed"] is False
    assert validate_repair_entity_retention(att1, {"slots": {"t": "star collapsing"}, "entities": ["star"]}, beat)["passed"] is True
    err_h = [{"status_code": 200, "thoughts_tokens": 100, "output_tokens": 100, "empty_or_truncated": True}]
    assert evaluate_thinking_step_down(err_h, current_level="high") == "medium"
    assert evaluate_thinking_step_down(err_h, current_level="medium") == "low"
    assert evaluate_thinking_step_down(err_h, current_level="low") == "low"
    assert evaluate_thinking_step_down([{"status_code": 200, "thoughts_tokens": 100, "output_tokens": 500, "empty_or_truncated": False}], current_level="high") == "high"
    assert evaluate_thinking_step_down([{"status_code": 200, "thoughts_tokens": 800, "output_tokens": 200, "rejected": True, "empty_or_truncated": False}], current_level="high") == "medium"

def test_record_scene_attempt_and_pipeline(tmp_path: Path) -> None:
    conn = init_database(tmp_path / "app.db")
    try:
        conn.execute("INSERT INTO projects VALUES ('p7', 'P7 Title', 'VIDEO_NEW', 1.0, 1.0);")
        conn.execute("INSERT INTO scenes (scene_id, project_id, scene_index, status, calls_used, locked_until, updated_at) VALUES ('S01', 'p7', 1, 'SCENE_READY', 0, 0.0, 1.0);")
        conn.commit()
        att_id = record_scene_attempt(conn, "S01", "p7", 1, "hash123", '{"res": 1}', {"template_id": "quote"}, {"valid": True}, {"passed": True}, 45.0, 100, 200)
        assert isinstance(att_id, int) and att_id > 0
        row = conn.execute("SELECT attempt_num, prompt_hash, thoughts_tokens FROM scene_attempts WHERE attempt_id = ?", (att_id,)).fetchone()
        assert row[0] == 1 and row[1] == "hash123" and row[2] == 100
    finally:
        conn.close()
    beat = {"id": "S01", "entities": ["star"], "vo": {"en": "Star"}}
    out = run_pipeline(tmp_path, {"project_id": "p7_run", "run_authoring": True, "scene_beat": beat, "manifest_summary": "Manifest"})
    assert out.get("authoring", {}).get("status") == "AUTHORED" and "story_bible" in out["authoring"]

