"""Regression tests for Feature F-019: Packaging and 6-hour soak (SPEC Sections 16, 17)."""
import pytest, zipfile
from pathlib import Path
from src.pipeline import (
    build_cue_sheet, generate_thumbnail_options, bundle_editable_project,
    assemble_final_package, simulate_chaos_soak_test, run_pipeline,
)

def test_f019_invalid_inputs_raise_errors(tmp_path: Path):
    with pytest.raises(TypeError): build_cue_sheet("invalid_scenes")  # type: ignore
    with pytest.raises(ValueError): build_cue_sheet([], lang="")
    with pytest.raises(ValueError): generate_thumbnail_options("", ratios=["16:9"])
    with pytest.raises(ValueError): generate_thumbnail_options("Title", ratios=["invalid_ratio"])
    with pytest.raises(ValueError): generate_thumbnail_options("Title", count_per_ratio=0)
    with pytest.raises(TypeError): bundle_editable_project("invalid_path")  # type: ignore
    with pytest.raises(TypeError): assemble_final_package(tmp_path, "not_a_dict", [])  # type: ignore
    with pytest.raises(ValueError): assemble_final_package(tmp_path, {}, [])
    with pytest.raises(ValueError): simulate_chaos_soak_test(tmp_path, scene_count=0)

def test_f019_build_cue_sheet_formats():
    scenes = [{"id": "S01", "duration": 8.0, "music": ["low ambient drone"], "sfx": ["whoosh"]}, {"id": "S02", "duration": 12.0, "music": ["drone continues"], "sfx": []}, {"id": "S03", "duration": 12.0, "music": [], "sfx": ["impact boom"]}]
    sheet = build_cue_sheet(scenes, lang="en")
    assert isinstance(sheet, dict) and sheet["events_count"] >= 3 and "start_time,end_time,event_type" in sheet["csv"] and "## Cue Sheet (EN)" in sheet["md"]

def test_f019_generate_thumbnail_options():
    thumbs = generate_thumbnail_options("Birth of a Black Hole", ratios=["16:9", "9:16"], count_per_ratio=3)
    assert len(thumbs["16:9"]) == 3 and len(thumbs["9:16"]) == 3
    assert all(t["width"] == 1280 and t["height"] == 720 and "Black Hole" in t["title"] for t in thumbs["16:9"])
    assert all(t["width"] == 1080 and t["height"] == 1920 and "Black Hole" in t["title"] for t in thumbs["9:16"])

def test_f019_bundle_editable_project(tmp_path: Path):
    for sub in ("source", "spec", "assets", "work"): (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "ledger.json").write_text('{"records": []}', encoding="utf-8")
    (tmp_path / "spec" / "project.json").write_text('{"title": "Test"}', encoding="utf-8")
    zip_path = bundle_editable_project(tmp_path)
    assert zip_path.exists() and zip_path.stat().st_size > 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert any("spec/project.json" in n.replace("\\", "/") for n in names) and any("ledger.json" in n.replace("\\", "/") for n in names)
        assert all(len(str(tmp_path / n)) < 260 for n in names)

def test_f019_assemble_final_package(tmp_path: Path):
    meta = {"slug": "black_hole", "languages": ["en", "hi", "ta"], "title": "Black Hole"}
    scenes = [{"id": "S01", "duration": 8.0, "music": ["drone"], "sfx": []}]
    pkg = assemble_final_package(tmp_path, meta, scenes, ledger_records=[])
    assert pkg["path_length_ok"] is True and pkg["videos_count"] == 6
    out_dir = Path(pkg["package_dir"])
    assert (out_dir / "credits.md").exists() and (out_dir / "editable_project.zip").exists()
    for lang in ("en", "hi", "ta"):
        assert (out_dir / f"cue_sheet_{lang}.csv").exists() and (out_dir / f"cue_sheet_{lang}.md").exists()
        assert (out_dir / lang / "16x9").exists() and (out_dir / lang / "9x16").exists()

def test_f019_simulate_chaos_soak_test(tmp_path: Path):
    soak = simulate_chaos_soak_test(tmp_path, scene_count=120)
    assert soak["passed"] is True and soak["completed_scenes"] == 120 and soak["faults_caught"] >= 6 and soak["wal_loss_count"] == 0 and soak["peak_ram_mb"] <= 2800 and soak["dead_man_alert_fired"] is True

def test_f019_pipeline_wiring(tmp_path: Path):
    res = run_pipeline(tmp_path, {"project_id": "proj_p12_test", "run_packaging_and_soak": True})
    assert res["packaging_and_soak"]["status"] == "PACKAGED_AND_SOAKED" and res["packaging_and_soak"]["videos_count"] == 6 and res["packaging_and_soak"]["soak_passed"] is True
