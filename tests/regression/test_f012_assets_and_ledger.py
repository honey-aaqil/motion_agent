"""Regression tests for Phase P5 / Feature F-012: Assets, ledger, and license filter."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from src.pipeline import (
    AssetLedger, detect_action_needed, filter_asset_license,
    generate_credits_markdown, remove_background_cached, run_pipeline,
)

def test_license_filter_contracts_and_rules() -> None:
    with pytest.raises(TypeError, match="must be a dict"):
        filter_asset_license("invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="missing required 'license_id'"):
        filter_asset_license({"source": "pexels"})
    with pytest.raises(ValueError, match="cannot be empty"):
        filter_asset_license({"license_id": "   "})
    for ok in ("CC0", "public domain", "CC-BY-4.0", "Pexels", "Pixabay", "Unsplash", "Mixkit", "Coverr", "OFL", "MIT", "ISC", "Apache-2.0"):
        res = filter_asset_license({"license_id": ok, "source": "openverse"})
        assert res["status"] == "ACCEPTED" and res["accepted"] is True
    for bad in ({"license_id": "CC-BY-NC-4.0"}, {"license_id": "CC-BY-ND"}, {"license_id": "CC-BY-SA-4.0"}, {"license_id": "GPL-3.0"},
                {"license_id": "Unknown"}, {"license_id": "CC0", "watermarked": True}, {"license_id": "Pexels", "editorial_only": True},
                {"license_id": "CC-BY", "commercial_ok": False}, {"license_id": "MIT", "derivatives_ok": False}):
        rej = filter_asset_license(bad)
        assert rej["status"] == "REJECTED" and rej["accepted"] is False and rej["reason"]

def test_action_needed_detection() -> None:
    with pytest.raises(TypeError, match="must be a list"):
        detect_action_needed("bad")  # type: ignore[arg-type]
    records = [
        {"id": "a1", "scene": "S01", "slot": "bg", "source": "user_upload", "vision_verdict": "RISKY", "status": "ACCEPTED"},
        {"id": "a2", "scene": "S02", "slot": "hero", "source": "pexels", "vision_verdict": "RECOGNIZABLE_PERSON_OR_TRADEMARK", "status": "ACCEPTED"},
        {"id": "a3", "scene": "S03", "slot": "icon", "source": "simple_icons", "vision_verdict": "SAFE", "status": "ACCEPTED"},
    ]
    slots = {"S04_chart": [{"license_id": "CC-BY-NC"}, {"license_id": "unknown"}]}
    actions = detect_action_needed(records, slot_candidates=slots)
    assert len(actions) == 3
    issues = {a["issue"] for a in actions}
    assert issues == {"risky_uploaded_file", "recognizable_person_or_trademark", "no_safe_alternative_exists"}

def test_asset_ledger_crud_and_export(tmp_path: Path) -> None:
    ledger = AssetLedger()
    with pytest.raises(TypeError, match="must be a dict"):
        ledger.add_asset("bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="missing 'id'"):
        ledger.add_asset({"scene": "S01"})
    rec1 = {"id": "A1", "scene": "S01", "slot": "img", "type": "image", "source": "unsplash", "url": "https://u.com/1", "author": "Jane", "license_id": "Unsplash", "license_url": "https://u.com/l", "attribution_required": False, "commercial_ok": True, "derivatives_ok": True, "retrieval_time": 1.0, "sha256": "h1", "local_path": "a.jpg", "vision_verdict": "SAFE", "status": "ACCEPTED"}
    rec2 = {"id": "A2", "scene": "S01", "slot": "snd", "type": "audio", "source": "mixkit", "url": "https://m.com/1", "author": "Bob", "license_id": "Mixkit", "license_url": "https://m.com/l", "attribution_required": False, "commercial_ok": True, "derivatives_ok": True, "retrieval_time": 2.0, "sha256": "h2", "local_path": "b.mp3", "vision_verdict": "SAFE", "status": "ACCEPTED"}
    assert ledger.add_asset(rec1)["id"] == "A1"
    ledger.add_asset(rec2)
    assert ledger.get_asset("A1")["author"] == "Jane" and ledger.get_asset("A9") is None
    assert len(ledger.list_assets(scene="S01")) == 2 and len(ledger.list_assets(status="REJECTED")) == 0
    summ = ledger.get_license_summary()
    assert summ["total_assets"] == 2 and summ["accepted_count"] == 2 and summ["all_compliant"] is True
    assert "Unsplash" in summ["license_ids"] and "Mixkit" in summ["license_ids"]
    p = ledger.export_ledger(tmp_path)
    assert p.exists() and p.name == "assets_ledger.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert len(data["assets"]) == 2 and data["assets"][0]["id"] == "A1"

def test_credits_markdown_generation() -> None:
    with pytest.raises(TypeError, match="must be a list"):
        generate_credits_markdown("bad")  # type: ignore[arg-type]
    records = [
        {"id": "A1", "scene": "S01", "slot": "diag", "type": "image", "source": "wikimedia", "url": "https://w.org/d", "author": "Alice", "license_id": "CC-BY-4.0", "license_url": "https://cc/4", "attribution_required": True, "status": "ACCEPTED"},
        {"id": "A2", "scene": "S02", "slot": "vid", "type": "video", "source": "pexels", "url": "https://p.com/v", "author": "Bob", "license_id": "Pexels", "license_url": "https://p.com/l", "attribution_required": False, "status": "ACCEPTED"},
    ]
    md = generate_credits_markdown(records, project_title="Quantum")
    assert "# Credits and Attributions" in md and "Alice" in md and "CC-BY-4.0" in md and "Bob" in md

def test_background_removal_caching(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="must be bytes"):
        remove_background_cached("bad", tmp_path)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="cannot be empty"):
        remove_background_cached(b"", tmp_path)
    sample = b"SAMPLE_PNG_DATA"
    r1 = remove_background_cached(sample, tmp_path)
    assert r1["cached"] is False and Path(r1["output_path"]).exists() and r1["sha256"]
    r2 = remove_background_cached(sample, tmp_path)
    assert r2["cached"] is True and r2["sha256"] == r1["sha256"] and r2["output_path"] == r1["output_path"]

def test_pipeline_wiring_assets_and_ledger(tmp_path: Path) -> None:
    ast_item = {"id": "A10", "scene": "S01", "slot": "ico", "type": "icon", "source": "iconify", "url": "https://i.dev/1", "author": "Dev", "license_id": "MIT", "license_url": "https://mit.org", "attribution_required": False, "commercial_ok": True, "derivatives_ok": True, "retrieval_time": 1.0, "sha256": "s1", "local_path": "i.svg", "vision_verdict": "SAFE"}
    out = run_pipeline(tmp_path, {"project_id": "P5_ASSETS", "run_assets_and_ledger": True, "assets": [ast_item], "bg_remove_sample": b"PIPELINE_BYTES"})
    assert "assets_and_ledger" in out
    res = out["assets_and_ledger"]
    assert res["status"] == "READY" and res["total_assets"] == 1 and Path(res["ledger_path"]).exists() and Path(res["credits_path"]).exists() and res["bg_removal"]["cached"] is False

