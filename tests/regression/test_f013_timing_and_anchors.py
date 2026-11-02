"""Regression tests for Phase P6 / Feature F-013: Timing and sentence anchors (SPEC Section 3)."""
from __future__ import annotations
import struct
from pathlib import Path
import pytest
from src.pipeline import (
    align_sentence_anchors, build_whisper_alignment_cmd, compute_scene_timing,
    measure_audio_duration_ffprobe, resolve_cue_timing, run_pipeline, validate_uploaded_audio_files,
    validate_whisper_alignment_output
)

def test_invalid_inputs_raise_explicit_errors() -> None:
    for bad in ("bad", 123):
        with pytest.raises(TypeError):
            validate_uploaded_audio_files(bad, ["S01"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Invalid audio filename"):
        validate_uploaded_audio_files(["bad.wav"], ["S01"])
    with pytest.raises(TypeError):
        measure_audio_duration_ffprobe(123)  # type: ignore[arg-type]
    with pytest.raises(FileNotFoundError):
        measure_audio_duration_ffprobe("missing_file.wav")
    with pytest.raises((TypeError, ValueError)):
        compute_scene_timing(-1.0)
    with pytest.raises(ValueError):
        compute_scene_timing(5.0, lead_in=-0.1)
    with pytest.raises((TypeError, ValueError)):
        align_sentence_anchors(None, 5.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        align_sentence_anchors("Hello.", 5.0, lang="fr")
    for bad_cue in ("0:05", "5.0s", "12.3"):
        with pytest.raises(ValueError, match="Absolute timestamps in a cue are a validation error"):
            resolve_cue_timing(bad_cue, {}, 10.0)
    with pytest.raises(ValueError, match="Unknown anchor"):
        resolve_cue_timing("@s9.start", {"@s1.start": 0.3}, 10.0)
    with pytest.raises(ValueError):
        build_whisper_alignment_cmd("", lang="en")
    with pytest.raises(ValueError):
        build_whisper_alignment_cmd("a.wav", lang="de")

def test_validate_uploaded_audio_files() -> None:
    files = ["s01.en.wav", "S02.EN.MP3", "S03.en.m4a", "S99.en.wav", "s01.HI.WAV"]
    res = validate_uploaded_audio_files(files, expected_scenes=["S01", "S02", "S04"], expected_langs=["en", "hi"])
    assert res["valid"] is False and "S04.en" in res["missing_files"] and "S99.en.wav" in res["extra_files"]
    ok = validate_uploaded_audio_files(["S01.en.wav"], expected_scenes=["S01"], expected_langs=["en"])
    assert ok["valid"] is True and len(ok["missing_files"]) == 0

def test_timing_pads_and_sentence_anchors() -> None:
    t = compute_scene_timing(7.123, lead_in=0.3, tail=0.5)
    assert abs(t["scene_duration"] - (7.123 + 0.8)) <= 0.040
    res = align_sentence_anchors("Every black hole begins as a star.", audio_duration=5.0, lead_in=0.3, tail=0.5)
    assert res["sentence_count"] == 1 and res["anchors"]["@s1.start"] == 0.3 and res["anchors"]["@s1.end"] == 5.3
    assert res["confidence_map"]["@s1.start"] == 1.0 and res["has_low_confidence"] is False
    segs = [{"start": 0.0, "end": 2.0}, {"start": 2.2, "end": 4.5}]
    w_res = align_sentence_anchors("Sentence one. Sentence two.", audio_duration=5.0, whisper_segments=segs, lead_in=0.3, tail=0.5)
    assert w_res["sentence_count"] == 2 and w_res["anchors"]["@s2.start"] == 2.5 and w_res["has_low_confidence"] is False
    fb_res = align_sentence_anchors("Sentence one. Sentence two.", audio_duration=5.0, whisper_segments=[{"start": 0.0, "end": 4.5}], silence_intervals=[{"start": 1.9, "end": 2.1}])
    assert fb_res["sentence_count"] == 2 and fb_res["has_low_confidence"] is True and len(fb_res["low_confidence_anchors"]) >= 1

def test_cues_multilingual_and_pipeline(tmp_path: Path) -> None:
    anchors = {"@scene.start": 0.0, "@scene.end": 10.0, "@s1.start": 0.3, "@s2.start": 5.0}
    assert resolve_cue_timing("@s1.start", anchors, 10.0) == 0.3 and resolve_cue_timing("@s2.start+0.2s", anchors, 10.0) == 5.2
    assert resolve_cue_timing("@scene.end-0.5s", anchors, 10.0) == 9.5 and resolve_cue_timing("@scene.start-1.0s", anchors, 10.0) == 0.0
    hi = align_sentence_anchors("हर ब्लैक होल की शुरुआत एक तारे से होती है। दूसरा वाक्य॥", audio_duration=6.0, lang="hi")
    ta = align_sentence_anchors("ஒவ்வொரு கருந்துளையும் ஒரு விண்மீனிலிருந்தே தொடங்குகிறது. இரண்டாவது வாக்கியம்.", audio_duration=6.0, lang="ta")
    assert hi["sentence_count"] == 2 and ta["sentence_count"] == 2
    cmd = build_whisper_alignment_cmd("test.wav", model_name="small", lang="hi")
    assert "-l" in cmd and "hi" in cmd
    w_file = tmp_path / "t.wav"
    w_file.write_bytes(struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + 16000, b"WAVE", b"fmt ", 16, 1, 1, 8000, 16000, 2, 16, b"data", 16000) + b"\x00" * 16000)
    assert 0.95 <= measure_audio_duration_ffprobe(w_file) <= 1.05
    payload = {"project_id": "p6_proj", "run_timing": True, "vo_text": "S1. S2.", "audio_duration": 6.0, "uploaded_audio_files": ["S01.en.wav", "S02.en.mp3"], "expected_scenes": ["S01", "S02"], "cues": [{"id": "c1", "anchor": "@s2.start+0.2s"}], "measure_audio_file": str(w_file)}
    out = run_pipeline(tmp_path, payload)
    assert "timing" in out and out["timing"]["status"] == "TIMED" and len(out["timing"]["resolved_cues"]) == 1

def test_whisper_alignment_validation() -> None:
    with pytest.raises(TypeError):
        validate_whisper_alignment_output(123, "text")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        validate_whisper_alignment_output({}, 123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="expected_text cannot be empty"):
        validate_whisper_alignment_output({}, "")

    w_data = {
        "transcription": [
            {"timestamps": {"from": "00:00:00,000", "to": "00:00:02,500"}, "text": "Every black hole begins as a star.", "tokens": [{"text": "Every", "p": 0.98}, {"text": "star", "p": 0.95}]}
        ]
    }
    v_res = validate_whisper_alignment_output(w_data, "Every black hole begins as a star.")
    assert isinstance(v_res, dict) and v_res["valid"] is True
    assert v_res["confidence_score"] >= 0.90 and v_res["has_drift"] is False
    assert len(v_res["segments"]) == 1 and v_res["segments"][0]["duration"] == 2.5

    # Test drift detection when end timestamp exceeds audio bound or jumps backwards
    drift_data = {
        "transcription": [
            {"timestamps": {"from": "00:00:03,000", "to": "00:00:01,000"}, "text": "Reversed timestamps."}
        ]
    }
    d_res = validate_whisper_alignment_output(drift_data, "Reversed timestamps.")
    assert d_res["valid"] is False and d_res["has_drift"] is True

