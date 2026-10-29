"""Regression tests for Feature F-017: Editor, overrides, editor_events (SPEC Section 11)."""
from __future__ import annotations
from pathlib import Path
import pytest
from src.pipeline import (
    apply_slot_overrides, check_editor_browser_support, compute_rerender_cache_key,
    edit_scene_timeline, evaluate_editor_gates, init_database,
    prepare_scene_regeneration, record_editor_event, replace_scene_asset, run_pipeline
)

def test_invalid_inputs_raise_explicit_errors(tmp_path: Path) -> None:
    conn = init_database(tmp_path / "err.db")
    try:
        for f, a in (
            (check_editor_browser_support, (123,)), (apply_slot_overrides, ("b", {})),
            (apply_slot_overrides, ({}, "b")), (apply_slot_overrides, ({}, {}, 123)),
            (replace_scene_asset, ("b", "s", {})), (replace_scene_asset, ({}, 123, {})),
            (replace_scene_asset, ({}, "s", "b")), (replace_scene_asset, ({}, "s", {}, "b")),
            (edit_scene_timeline, ("b", "trim", "S01")), (edit_scene_timeline, ([], 123, "S01")),
            (edit_scene_timeline, ([], "trim", 123)), (prepare_scene_regeneration, ("b", {}, "p")),
            (prepare_scene_regeneration, ({}, "b", "p")), (prepare_scene_regeneration, ({}, {}, 123)),
            (compute_rerender_cache_key, ("b", {}, "h", "16:9", "en", "p")),
            (compute_rerender_cache_key, ({}, "b", "h", "16:9", "en", "p")),
            (compute_rerender_cache_key, ({}, {}, 123, "16:9", "en", "p")),
            (evaluate_editor_gates, ("b",)), (evaluate_editor_gates, ({}, "b")),
            (record_editor_event, ("b", "S01", "autofix_accept")),
            (record_editor_event, (conn, 123, "autofix_accept")), (record_editor_event, (conn, "S01", 123)),
        ):
            with pytest.raises(TypeError): f(*a)  # type: ignore[arg-type]

        for f, a, kw in (
            (apply_slot_overrides, ({"slots": {"t": {}}}, {"t": {"font": "BadFont"}}), {}),
            (apply_slot_overrides, ({"slots": {"t": {}}}, {"t": {"color": "xyz"}}), {}),
            (replace_scene_asset, ({}, "   ", {}), {}),
            (replace_scene_asset, ({}, "logo", {"license": "editorial_only"}), {}),
            (edit_scene_timeline, ([], "invalid_action", "S01"), {}),
            (edit_scene_timeline, ([{"scene_id": "S01"}], "trim", "S99"), {}),
            (edit_scene_timeline, ([{"scene_id": "S01"}], "trim", "S01"), {"duration": -2.0}),
            (edit_scene_timeline, ([{"scene_id": "S01"}], "reorder", "S01"), {"target_index": 5}),
            (prepare_scene_regeneration, ({}, {}, "   "), {}),
            (record_editor_event, (conn, "   ", "autofix_accept"), {}),
            (record_editor_event, (conn, "S01", "bad_action"), {}),
        ):
            with pytest.raises(ValueError): f(*a, **kw)  # type: ignore[arg-type]
    finally: conn.close()

def test_browser_support_and_slot_overrides() -> None:
    ch, ff = check_editor_browser_support("Mozilla Chrome/120.0 Safari"), check_editor_browser_support("Mozilla Firefox/120.0")
    assert ch["supported"] is True and ch["is_chromium"] is True and ch["warning"] is None
    assert ff["supported"] is False and ff["is_chromium"] is False and "Chromium-based" in str(ff["warning"])
    spec = {"scene_id": "S01", "slots": {"headline": {"text": "Hello", "font": "Inter", "color": "#000000"}}}
    res = apply_slot_overrides(spec, {"headline": {"text": "World", "font": "Roboto", "color": "#FF0000"}}, language="en")
    assert res["slots"]["headline"]["text"] == "World" and res["slots"]["headline"]["applies_all_languages"] is True
    assert res["overrides"]["headline"]["text"] == "World" and res["slots"]["headline"]["font"] == "Roboto"

def test_asset_replacement_and_timeline() -> None:
    spec = {"scene_id": "S01", "slots": {"bg": {"path": "old.png"}}}
    up = replace_scene_asset(spec, "bg", {"path": "new.png"}, is_user_upload=True)
    assert up["slots"]["bg"]["provenance"] == "user-supplied" and up["slots"]["bg"]["license"] == "user_supplied"
    safe = replace_scene_asset(spec, "bg", {"path": "stock.png", "license": "cc0"}, is_user_upload=False)
    assert safe["slots"]["bg"]["provenance"] == "safe_license_search"
    scenes = [{"scene_id": "S01", "duration_sec": 5.0, "audio_source": "vo1.wav"}, {"scene_id": "S02", "duration_sec": 3.0}]
    dup = edit_scene_timeline(scenes, "duplicate", "S01")
    assert len(dup) == 3 and dup[1]["scene_id"] == "S01_copy" and dup[1]["needs_audio"] is True and dup[1]["audio_source"] == "vo1.wav"
    trimmed = edit_scene_timeline(scenes, "trim", "S01", duration=4.0)
    assert trimmed[0]["duration_sec"] == 4.0 and trimmed[0]["audio_duration_sec"] == 4.0
    reordered = edit_scene_timeline(scenes, "reorder", "S01", target_index=1)
    assert reordered[0]["scene_id"] == "S02" and reordered[1]["scene_id"] == "S01"
    deleted = edit_scene_timeline(scenes, "delete", "S01")
    assert len(deleted) == 1 and deleted[0]["scene_id"] == "S02"

def test_regeneration_gates_and_cache_key() -> None:
    spec = {"scene_id": "S01", "template_id": "title_slam", "slots": {"t": {"text": "Short"}}}
    regen = prepare_scene_regeneration(spec, {"t": {"color": "#FFF"}}, "Make punchy")
    assert regen["status"] == "PENDING_USER_REVIEW" and regen["preserved_overrides"]["t"]["color"] == "#FFF" and "t" in regen["slot_contract"]
    k1 = compute_rerender_cache_key(spec, None, "a1", "16:9", "en", "default")
    k2 = compute_rerender_cache_key(spec, None, "a1", "16:9", "en", "default")
    k3 = compute_rerender_cache_key(spec, {"t": {"text": "Diff"}}, "a1", "16:9", "en", "default")
    k4 = compute_rerender_cache_key(spec, None, "a1", "9:16", "en", "default")
    assert isinstance(k1, str) and len(k1) == 64 and k1 == k2 and k1 != k3 and k1 != k4
    long_spec = {"scene_id": "S01", "slots": {"msg": {"text": "This is an extremely long slot narration text that definitely exceeds forty characters"}}}
    g_warn = evaluate_editor_gates(long_spec)
    assert g_warn["has_warnings"] is True and g_warn["fix_automatically_available"] is True and "9:16" in str(g_warn["warnings"])

def test_editor_events_and_pipeline_integration(tmp_path: Path) -> None:
    conn = init_database(tmp_path / "events.db")
    try:
        e1, e2, e3 = record_editor_event(conn, "S01", "autofix_accept"), record_editor_event(conn, "S01", "autofix_reject"), record_editor_event(conn, "S01", "regen_same_prompt")
        e4, e5, e6 = record_editor_event(conn, "S01", "text_edit", pre_edit_validator_warn=True), record_editor_event(conn, "S01", "text_edit", pre_edit_validator_warn=False), record_editor_event(conn, "S01", "asset_swap")
        assert all(isinstance(x, int) and x > 0 for x in (e1, e2, e3, e4, e5, e6))
        rows = conn.execute("SELECT event_id, action_type, is_clean_quality_pair FROM editor_events ORDER BY event_id").fetchall()
        clean_map = {r[1]: r[2] for r in rows if r[0] != e5}
        assert clean_map["autofix_accept"] == 1 and clean_map["autofix_reject"] == 1 and clean_map["regen_same_prompt"] == 1
        assert rows[3][2] == 1 and rows[4][2] == 0 and clean_map["asset_swap"] == 0
    finally: conn.close()
    pipe_res = run_pipeline(tmp_path, {"project_id": "P_EDIT", "run_editor_ops": True})
    assert pipe_res["editor_ops"]["status"] == "READY" and pipe_res["editor_ops"]["event_id"] > 0 and len(pipe_res["editor_ops"]["cache_key"]) == 64

