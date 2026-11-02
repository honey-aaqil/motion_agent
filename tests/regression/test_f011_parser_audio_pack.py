"""Regression tests for Feature F-011: Parser, VO round trip, Audio Pack (SPEC 9, 16)."""
from pathlib import Path
import pytest
from src.pipeline import (
    normalize_sacred_vo, parse_av_script, rebuild_vo_text,
    generate_audio_pack, export_audio_pack, run_pipeline,
    validate_sacred_vo_gate
)

SAMPLE_SCRIPT = (
    "| Scene / Time | VISUAL | AUDIO |\n|---|---|---|\n"
    "| **S01 · 0:00-0:08** | Black screen. Dot grows. Kinetic text \"BIRTH OF A BLACK HOLE\" slams at 0:05. Style: cinematic. | "
    "**MUSIC:** low ambient drone, rising. **SFX:** deep whoosh at 0:05. **VO (EN):** \"Every black hole begins as a star.\" "
    "**VO (HI):** \"हर ब्लैक होल की शुरुआत एक तारे से होती है।\" **VO (TA):** \"ஒவ்வொரு கருந்துளையும் ஒரு விண்மீனிலிருந்தே தொடங்குகிறது.\" |\n"
    "| **S02 · 0:08-0:20** | Split diagram. Label \"BALANCE\" in center. | **MUSIC:** drone continues. **VO (EN):** \"For millions of years, gravity pulls inward.\" |\n"
    "| **S03 · 0:20-0:32** | Counter shows \"20x mass\". | **SFX:** impact boom. **VO (EN):** \"When fuel runs out, gravity wins.\" |\n"
)

def test_invalid_inputs_raise_explicit_errors() -> None:
    for bad in (12345, None):
        with pytest.raises((TypeError, ValueError)):
            normalize_sacred_vo(bad)  # type: ignore[arg-type]
    for bad in (None, "   \n\t  "):
        with pytest.raises((TypeError, ValueError)):
            parse_av_script(bad)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        rebuild_vo_text("not_a_list")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        rebuild_vo_text([], lang="bad_lang")
    with pytest.raises(TypeError):
        generate_audio_pack("bad")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        export_audio_pack({}, "not_a_path")  # type: ignore[arg-type]

def test_sacred_vo_normalization_and_roundtrip() -> None:
    raw = "\ufeffहर \u200Dब्लैक होल\r\nकी शुरुआत एक तारे से होती है।\r\n"
    norm = normalize_sacred_vo(raw)
    assert not norm.startswith("\ufeff") and "\r\n" not in norm and "\u200D" in norm
    scenes = [
        {"id": "S01", "vo": {"en": "Sentence 1.", "hi": norm, "ta": "வாக்கியம் 1."}},
        {"id": "S02", "vo": {"en": "Sentence 2.", "hi": "दूसरा वाक्य।", "ta": "வாக்கியம் 2."}},
    ]
    assert rebuild_vo_text(scenes, "en") == "Sentence 1.\nSentence 2."
    assert rebuild_vo_text(scenes, "hi") == f"{norm}\nदूसरा वाक्य।"

def test_parse_appendix_a_fixture() -> None:
    res = parse_av_script(SAMPLE_SCRIPT)
    assert res["total_scenes"] == 3
    s1, s2, s3 = res["scenes"]
    assert s1["id"] == "S01" and s1["timecode_hint"] == "0:00-0:08"
    assert "BIRTH OF A BLACK HOLE" in s1["onscreen_text"]
    assert "Every black hole" in s1["vo"]["en"] and "हर ब्लैक होल" in s1["vo"]["hi"]
    assert any("drone" in m for m in s1["music"]) and any("whoosh" in s for s in s1["sfx"])
    assert "BALANCE" in s2["onscreen_text"] and "drone continues" in s2["music"][0]
    assert "20x mass" in s3["onscreen_text"] and "impact boom" in s3["sfx"][0]

def test_uncertain_lines_raise_questions() -> None:
    res = parse_av_script("| S01 | Note | VO: Text |\nUnrecognized unformatted prose line")
    assert len(res["uncertain_questions"]) >= 1
    assert "question" in res["uncertain_questions"][0] and "line" in res["uncertain_questions"][0]

def test_audio_pack_generation_and_export(tmp_path: Path) -> None:
    parsed = parse_av_script(SAMPLE_SCRIPT)
    pack = generate_audio_pack(parsed["scenes"])
    assert "scenes" in pack and len(pack["project_music_prompts"]) >= 1
    s1_audio = pack["scenes"]["S01"]["en"]
    assert s1_audio["tts_direction"]["character"] and s1_audio["estimated_duration_sec"] > 0
    assert pack["project_music_prompts"][0]["no_vocals"] is True
    exp = export_audio_pack(pack, tmp_path)
    assert exp["status"] == "EXPORTED" and exp["files_written"] >= 3
    assert (tmp_path / "audio_pack" / "audio_pack.json").is_file()

def test_pipeline_integration(tmp_path: Path) -> None:
    res = run_pipeline(tmp_path, {"project_id": "P4_TEST", "run_parser_and_audio_pack": True, "script_text": SAMPLE_SCRIPT})
    assert res["project_id"] == "P4_TEST"
    assert res["parser_audio_pack"]["parsed"]["total_scenes"] == 3
    assert (tmp_path / "audio_pack" / "audio_pack.json").exists()

def test_sacred_vo_gate_invariance() -> None:
    with pytest.raises(TypeError):
        validate_sacred_vo_gate(123, [])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        validate_sacred_vo_gate("script", "not_a_list")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="parsed_scenes cannot be empty"):
        validate_sacred_vo_gate("script", [])
    
    parsed = parse_av_script(SAMPLE_SCRIPT)
    res = validate_sacred_vo_gate(SAMPLE_SCRIPT, parsed["scenes"])
    assert isinstance(res, dict) and res["passed"] is True
    assert res["nfc_normalized"] is True
    assert res["scene_count"] == 3
    assert res["total_vo_lines"] >= 3
    
    import unicodedata
    decomposed = unicodedata.normalize("NFD", "Café résumé")
    bad_scenes = [{"id": "S01", "vo": {"en": decomposed}}]
    bad_res = validate_sacred_vo_gate("dummy", bad_scenes)
    assert bad_res["passed"] is False and bad_res["nfc_normalized"] is False
