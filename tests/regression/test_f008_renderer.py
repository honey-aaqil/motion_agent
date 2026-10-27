"""Regression tests for Feature F-008: Deterministic renderer and chunking (SPEC Section 12)."""
from __future__ import annotations

from pathlib import Path
import pytest

from src.pipeline import (
    adjust_chunk_size_on_respawns,
    build_ffmpeg_concat_cmd,
    build_ffmpeg_encode_cmd,
    build_ffmpeg_mix_cmd,
    check_render_resource_watchdog,
    clean_stray_processes,
    compute_render_chunks,
    get_chromium_render_flags,
    render_scene_chunk,
    run_pipeline,
)

def test_compute_render_chunks_and_rejections() -> None:
    for bad in (0, -5, "900", 3.14):
        with pytest.raises((ValueError, TypeError)):
            compute_render_chunks(bad)  # type: ignore[arg-type]
    with pytest.raises((ValueError, TypeError)):
        compute_render_chunks(900, max_chunk_frames=0)
    assert compute_render_chunks(900) == [(0, 900)]
    assert compute_render_chunks(1800) == [(0, 900), (900, 1800)]
    assert compute_render_chunks(950) == [(0, 900), (900, 950)]
    assert compute_render_chunks(700, max_chunk_frames=300) == [(0, 300), (300, 600), (600, 700)]

def test_chromium_flags_and_resource_watchdog() -> None:
    flags = get_chromium_render_flags()
    assert isinstance(flags, list)
    assert any("--disable-gpu" in f for f in flags)
    assert any("--max-old-space-size=1536" in f for f in flags)

    with pytest.raises(RuntimeError, match="Free disk space below 10 GB"):
        check_render_resource_watchdog(free_disk_bytes=9 * 1024**3)

    resp_mem = check_render_resource_watchdog(process_tree_memory_bytes=3 * 1024**3, free_disk_bytes=20 * 1024**3)
    assert resp_mem["action"] == "RESPAWN"

    resp_ram = check_render_resource_watchdog(available_ram_bytes=1024**3, free_disk_bytes=20 * 1024**3)
    assert resp_ram["action"] == "RESPAWN"

    ok = check_render_resource_watchdog(process_tree_memory_bytes=1024**3, available_ram_bytes=3 * 1024**3, free_disk_bytes=20 * 1024**3)
    assert ok["action"] == "OK"

    assert adjust_chunk_size_on_respawns(0) == (900, False)
    assert adjust_chunk_size_on_respawns(2) == (900, False)
    assert adjust_chunk_size_on_respawns(3) == (300, True)
    assert adjust_chunk_size_on_respawns(5) == (300, True)

def test_ffmpeg_commands_and_process_cleanup() -> None:
    for bad in (-1, 0, 150):
        with pytest.raises(ValueError):
            build_ffmpeg_encode_cmd("in_%04d.png", "out.mp4", fps=bad)
    with pytest.raises(ValueError):
        build_ffmpeg_encode_cmd("in_%04d.png", "out.mp4", crf=60)
    with pytest.raises(ValueError):
        build_ffmpeg_encode_cmd("in_%04d.png", "out.mp4", threads=0)

    enc_cmd = build_ffmpeg_encode_cmd("in_%04d.png", "out.mp4", fps=30, crf=19, threads=2)
    assert "libx264" in enc_cmd and "yuv420p" in enc_cmd and "+faststart" in enc_cmd

    with pytest.raises(ValueError):
        build_ffmpeg_concat_cmd([], "out.mp4")
    concat_cmd, concat_txt = build_ffmpeg_concat_cmd(["s1.mp4", "s2.mp4"], "final.mp4")
    assert "concat" in concat_cmd and "file 's1.mp4'" in concat_txt

    mix_cmd = build_ffmpeg_mix_cmd("v.mp4", "vo.wav", "out.mp4", music_path="bgm.mp3")
    assert "192k" in mix_cmd and "48000" in mix_cmd

    cleaned = clean_stray_processes(["non_existent_mock_proc_xyz_123"])
    assert isinstance(cleaned, int)

def test_render_scene_chunk_and_pipeline_wiring(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        render_scene_chunk("", 0, 0, 100, tmp_path)
    res = render_scene_chunk("S01", 0, 0, 30, tmp_path, mock_frames=True)
    assert res["frames_rendered"] == 30
    assert (tmp_path / "S01_chunk_0.mp4").exists()
    assert (tmp_path / "S01.state.json").exists()

    payload = {"project_id": "P_RENDER", "render_chunking": {"total_frames": 950, "scene_id": "S02"}}
    out = run_pipeline(tmp_path, payload)
    assert "renderer" in out and out["renderer"]["chunks_count"] == 2

