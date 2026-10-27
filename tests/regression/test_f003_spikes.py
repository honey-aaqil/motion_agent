"""Regression tests for Phase P0 / Feature F-003: Spikes."""
from __future__ import annotations
from pathlib import Path
import pytest
from src.pipeline import (
    check_process_memory_budget, compute_scene_duration, normalize_vo_text,
    run_pipeline, split_sentences, validate_audio_filename, verify_utf8_roundtrip,
)

def test_audio_filename_validation() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        validate_audio_filename(123)  # type: ignore[arg-type]
    for bad in ("foo.wav", "S00.en.wav", "S01.fr.wav", "S1.en.ogg", "scene01.en.wav"):
        with pytest.raises(ValueError, match="Invalid audio filename"):
            validate_audio_filename(bad)
    assert validate_audio_filename("S01.en.wav") == {"scene_num": 1, "lang": "en", "ext": "wav"}
    assert validate_audio_filename("s02.HI.MP3") == {"scene_num": 2, "lang": "hi", "ext": "mp3"}
    assert validate_audio_filename("S12.TA.m4a") == {"scene_num": 12, "lang": "ta", "ext": "m4a"}

def test_vo_text_normalization_and_split() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        normalize_vo_text(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be a string"):
        split_sentences(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="cannot be empty"):
        split_sentences("   \t  ")
    raw = "\ufeffहर ब्लैक होल की शुरुआत\r\nएक तारे से होती है। दूसरा वाक्य॥ तीसरा?"
    norm = normalize_vo_text(raw)
    assert not norm.startswith("\ufeff") and "\r" not in norm
    sentences = split_sentences(norm)
    assert len(sentences) == 3 and sentences[1] == "दूसरा वाक्य" and sentences[2] == "तीसरा"

def test_duration_and_utf8_roundtrip(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        compute_scene_duration(-1.0)
    with pytest.raises(TypeError, match="must be numeric"):
        compute_scene_duration("5.0")  # type: ignore[arg-type]
    assert compute_scene_duration(10.0, lead_in=0.3, tail=0.5) == 10.8

    with pytest.raises(TypeError, match="must be a string"):
        verify_utf8_roundtrip(None, tmp_path / "test.db")  # type: ignore[arg-type]
    hi = "हर ब्लैक होल की शुरुआत एक तारे से होती है।"
    ta = "ஒவ்வொரு கருந்துளையும் ஒரு விண்மீனிலிருந்தே தொடங்குகிறது।"
    assert verify_utf8_roundtrip(hi, tmp_path / "hi.db") is True
    assert verify_utf8_roundtrip(ta, tmp_path / "ta.db") is True

def test_memory_and_pipeline_wiring(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        check_process_memory_budget(max_tree_gb=-1.0)
    stats = check_process_memory_budget()
    assert isinstance(stats, dict) and isinstance(stats["tree_gb"], float) and isinstance(stats["within_budget"], bool)

    payload = {
        "project_id": "p0_spike_proj", "run_spikes": True,
        "vo_text": "हर ब्लैक होल की शुरुआत एक तारे से होती है।",
        "audio_file": "S01.hi.wav", "audio_duration": 8.0,
    }
    out = run_pipeline(tmp_path, payload)
    assert "spikes" in out and out["spikes"]["audio"]["scene_num"] == 1
    assert out["spikes"]["scene_duration"] == 8.8 and out["spikes"]["utf8_ok"] is True
    assert "within_budget" in out["spikes"]["memory"]
