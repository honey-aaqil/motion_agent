"""Regression tests for Feature F-009: Render canaries INV-1..6 with sabotage fixtures."""
from __future__ import annotations
import hashlib, sqlite3, pytest
from pathlib import Path
from src.pipeline import (
    check_canary_inv1_streams, check_canary_inv2_blackdetect, check_canary_inv3_freezedetect,
    check_canary_inv4_audio_loudness, check_canary_inv5_golden_drift, check_canary_inv6_ledger,
    run_canary_gate, run_sabotage_suite, run_pipeline
)

def test_inv1_streams_valid_and_sabotage():
    assert check_canary_inv1_streams(3.0, 3.01, 3.0, 90, 30.0)["passed"] is True
    assert check_canary_inv1_streams(3.0, 3.10, 3.0, 90, 30.0)["code"] == "CANARY_INV1_FAIL"
    with pytest.raises(ValueError):
        check_canary_inv1_streams(-1.0, 3.0, 3.0, 90, 30.0)

def test_inv2_blackdetect_valid_and_sabotage():
    assert check_canary_inv2_blackdetect([{"start": 0.0, "duration": 0.10}])["passed"] is True
    assert check_canary_inv2_blackdetect([{"start": 1.0, "duration": 0.30}])["code"] == "CANARY_INV2_BLACK_DETECTED"
    with pytest.raises(ValueError):
        check_canary_inv2_blackdetect([], pic_th=-0.1)

def test_inv3_freezedetect_valid_and_sabotage():
    assert check_canary_inv3_freezedetect([{"start": 0.5, "duration": 1.2}])["passed"] is True
    assert check_canary_inv3_freezedetect([{"start": 1.0, "duration": 2.5}])["code"] == "CANARY_INV3_FREEZE_DETECTED"
    with pytest.raises(ValueError):
        check_canary_inv3_freezedetect([], max_freeze_dur=0.0)

def test_inv4_audio_loudness_valid_and_sabotage():
    assert check_canary_inv4_audio_loudness(-18.0, -1.5, -25.0, 0.5)["passed"] is True
    assert check_canary_inv4_audio_loudness(-28.0, -5.0, -45.0, 0.5)["code"] == "CANARY_INV4_AUDIO_LOUDNESS_FAIL"
    with pytest.raises(ValueError):
        check_canary_inv4_audio_loudness(-18.0, -1.0, -25.0, 0.5, loudness_range=(-10.0, -20.0))

def test_inv5_framemd5_valid_and_sabotage():
    assert check_canary_inv5_golden_drift("abc123md5", "abc123md5")["passed"] is True
    assert check_canary_inv5_golden_drift("mismatch_hash", "abc123md5")["code"] == "CANARY_INV5_GOLDEN_MISMATCH"
    with pytest.raises(ValueError):
        check_canary_inv5_golden_drift("abc", "")

def test_inv6_ledger_valid_and_sabotage(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE scenes (scene_id TEXT, project_id TEXT, scene_index INT, status TEXT, file_path TEXT, file_sha256 TEXT, file_size INT, locked_until REAL);")
    tf = tmp_path / "s1.mp4"
    tf.write_bytes(b"x" * 15000)
    f_sha = hashlib.sha256(tf.read_bytes()).hexdigest()
    conn.execute("INSERT INTO scenes VALUES ('S01', 'P1', 1, 'DONE', ?, ?, 15000, 0.0);", (str(tf), f_sha))
    assert check_canary_inv6_ledger(conn, "P1")["passed"] is True
    conn.execute("INSERT INTO scenes VALUES ('S03', 'P1', 3, 'DONE', ?, ?, 15000, 0.0);", (str(tf), f_sha))
    assert check_canary_inv6_ledger(conn, "P1")["code"] == "CANARY_INV6_LEDGER_FAIL"
    with pytest.raises(ValueError):
        check_canary_inv6_ledger(conn, "")

def test_run_canary_gate_and_sabotage_suite(tmp_path):
    c_data = {"v_dur": 3.0, "a_dur": 3.01, "exp_dur": 3.0, "nb_frames": 90, "black_intervals": [], "freeze_intervals": [], "audio": {"lufs": -18.0, "tp": -1.5, "mv": -25.0, "silence": 0.2}, "rendered_md5": "c1", "golden_md5": "c1"}
    assert run_canary_gate(tmp_path, c_data)["passed"] is True
    assert run_sabotage_suite(tmp_path)["passed"] is True
    pip = run_pipeline(tmp_path, {"project_id": "P_CANARY_TEST", "run_canaries": True, "canary_data": c_data})
    assert pip["canary_gate"]["passed"] is True and pip["sabotage_suite"]["passed"] is True
    with pytest.raises(TypeError):
        run_canary_gate("not_path", {})
