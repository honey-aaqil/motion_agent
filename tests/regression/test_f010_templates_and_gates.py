"""Regression tests for F-010: Templates, canonicalizer, validator, DOM gate."""
from __future__ import annotations
from pathlib import Path
import pytest
from src.pipeline import (
    get_layout_config, get_template_catalog, canonicalize_scene_spec,
    validate_scene_spec, audit_dom_layout, run_dom_sabotage_preflight, run_pipeline,
    generate_film_storyboard, generate_preview_stills
)

TEMPLATES = {"title_slam", "big_statement", "concept_diagram", "comparison_split", "process_flow", "timeline", "stat_counter", "icon_grid", "chart", "image_focus", "two_image_contrast", "quote", "list_reveal", "outro"}

def test_f010_invalid_inputs_and_catalog() -> None:
    with pytest.raises(ValueError):
        get_layout_config("4:3")
    with pytest.raises(TypeError):
        canonicalize_scene_spec(12345)
    with pytest.raises(TypeError):
        validate_scene_spec("bad")
    with pytest.raises(TypeError):
        audit_dom_layout("bad")
    # Zero boxes counts as FAIL with GATE_EXEC_ERROR
    z = audit_dom_layout([], ratio="9:16")
    assert z["passed"] is False and z["code"] == "GATE_EXEC_ERROR"
    # Catalog and layout
    cat = get_template_catalog()
    assert TEMPLATES.issubset({t["template_id"] for t in cat})
    c9, c16 = get_layout_config("9:16"), get_layout_config("16:9")
    assert c9["caption_safe_bottom"] == 440 and c16["caption_safe_bottom"] == 190

def test_f010_canonicalizer_and_validator() -> None:
    raw = '{"scene_id": "S01", "template_id": "title_slam", "ratio": "9:16", "bg": "$bg_hex", "cues": [{"target": "t", "anchor": "@s1.start+0.2s"}], "box": {"x": -20, "y": 0, "w": 1100, "h": 500}'
    can = canonicalize_scene_spec(raw, {"tokens": {"$bg_hex": "#0B0F19"}})
    assert can["bg"] == "#0B0F19" and can["box"]["x"] == 0 and can["box"]["w"] == 1080
    valid_spec = {"scene_id": "S01", "template_id": "title_slam", "ratio": "9:16", "duration": 3.8, "slots": {"title": "Market Crash"}, "cues": [{"target": "title", "anchor": "@s1.start+0.2s"}]}
    assert validate_scene_spec(valid_spec, audio_duration=3.0)["valid"] is True
    # Invalids: bad duration, absolute cue timestamp, >4 words
    assert validate_scene_spec(valid_spec, audio_duration=4.0)["valid"] is False
    assert validate_scene_spec(dict(valid_spec, cues=[{"target": "t", "anchor": "@1.5s"}]), audio_duration=3.0)["valid"] is False
    assert validate_scene_spec(dict(valid_spec, slots={"title": "one two three four five"}), audio_duration=3.0)["valid"] is False

def test_f010_dom_gate_and_pipeline(tmp_path: Path) -> None:
    # Safe zone breach
    assert audit_dom_layout([{"id": "t", "x": 100, "y": 1500, "w": 800, "h": 100, "text": "Hi", "font_size": 80, "color": "#FFF", "bg": "#000"}], ratio="9:16")["passed"] is False
    # Overlap
    assert audit_dom_layout([{"id": "a", "x": 100, "y": 100, "w": 300, "h": 200, "text": "A", "font_size": 72, "color": "#FFF", "bg": "#000"}, {"id": "b", "x": 150, "y": 150, "w": 300, "h": 200, "text": "B", "font_size": 72, "color": "#FFF", "bg": "#000"}])["passed"] is False
    # Low contrast (< 4.5:1)
    assert audit_dom_layout([{"id": "a", "x": 100, "y": 200, "w": 300, "h": 100, "text": "Low", "font_size": 48, "color": "#222", "bg": "#111"}])["passed"] is False
    # Trap undefined
    assert audit_dom_layout([{"id": "a", "x": 100, "y": 200, "w": 300, "h": 100, "text": "undefined", "font_size": 72, "color": "#FFF", "bg": "#000"}])["passed"] is False
    # Sabotage preflight
    sb = run_dom_sabotage_preflight()
    assert sb["passed"] is True and sb["sabotages_caught"] == 3
    # Pipeline wiring
    pipe = run_pipeline(tmp_path, {"project_id": "P_F010_PIPE", "run_templates_and_gates": True})
    assert pipe.get("templates_and_gates", {}).get("passed") is True

def test_f010_film_storyboard_and_preview_stills(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        generate_film_storyboard("bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported ratio"):
        generate_film_storyboard([], ratio="4:3")
    with pytest.raises(TypeError):
        generate_preview_stills("bad", tmp_path)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        generate_preview_stills([], "not_a_path")  # type: ignore[arg-type]

    scenes = [
        {"id": "S01", "template_id": "title_slam", "slots": {"title": "Quantum Reality"}, "duration": 4.0},
        {"id": "S02", "template_id": "concept_diagram", "slots": {"title": "Wave Particle"}, "duration": 6.0},
    ]
    sb16 = generate_film_storyboard(scenes, ratio="16:9")
    assert isinstance(sb16, dict) and "<!DOCTYPE html>" in sb16["html"]
    assert "openfilm" in sb16["html"].lower() and sb16["scene_count"] == 2 and sb16["ratio"] == "16:9"

    stills = generate_preview_stills(scenes, tmp_path, ratios=["16:9", "9:16"])
    assert stills["status"] == "PREVIEWS_GENERATED"
    assert stills["scene_count"] == 2 and stills["all_passed"] is True
    assert len(stills["stills"]) == 4  # 2 scenes * 2 ratios
    for s_info in stills["stills"]:
        p = Path(s_info["path"])
        assert p.is_file() and p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    pipe = run_pipeline(tmp_path, {"project_id": "P_SB_TEST", "run_storyboard_and_previews": True, "scenes": scenes})
    assert "storyboard_and_previews" in pipe
    assert pipe["storyboard_and_previews"]["status"] == "READY"
    assert pipe["storyboard_and_previews"]["preview_stills"]["all_passed"] is True
