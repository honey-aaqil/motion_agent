"""Regression tests for Feature F-020 (Phase P13): Improvement program."""
import pytest
from src.pipeline import (
    audit_failure_pool, manage_improvement_rule, replay_rule_history,
    manage_exemplar_bank, retrieve_exemplars, run_model_migration_checklist, run_pipeline
)

def test_audit_failure_pool_and_bad_input():
    pool = [{"id": f"f{i}", "category": "A" if i < 3 else "B"} for i in range(5)]
    res = audit_failure_pool(pool)
    assert res["counts"]["total"] == 5 and res["percentages"]["A"] == 0.60
    assert res["recommendation"] == "FOCUS_CANONICALIZER_AND_RULES"
    res_b = audit_failure_pool([{"category": "B"}, {"category": "C"}])
    assert res_b["recommendation"] == "FOCUS_TEMPLATES_OR_PROMPTS"
    with pytest.raises(TypeError, match="failures must be a list"): audit_failure_pool("bad")
    with pytest.raises(TypeError, match="each failure must be a dict"): audit_failure_pool(["bad"])

def test_manage_improvement_rule_workflow_and_bad_input():
    reg = {}
    rdef = {"must_pass_fixture": {"ok": True}, "must_fail_fixture": {"ok": False}}
    r = manage_improvement_rule("register", "R1", rule_def=rdef, registry=reg)
    assert r["rule_id"] == "R1" and r["active"] is True and r["status"] == "REGISTERED"
    assert manage_improvement_rule("revert", "R1", registry=reg)["active"] is False
    assert manage_improvement_rule("toggle", "R1", registry=reg)["active"] is True
    with pytest.raises(ValueError, match="rule_id must be non-empty string"): manage_improvement_rule("register", "")
    with pytest.raises(ValueError, match="Invalid action"): manage_improvement_rule("bad", "R1")
    with pytest.raises(ValueError, match="must_pass_fixture and must_fail_fixture"): manage_improvement_rule("register", "R2", rule_def={})

def test_replay_rule_history_offline_and_bad_input():
    corpus = [{"scene_id": "H1", "template_id": "slam"}]
    rules = [{"rule_id": "R1", "active": True, "disallowed_template": "deprecated"}]
    rep = replay_rule_history(corpus, rules)
    assert rep["total_checked"] == 1 and rep["regressions"] == 0 and rep["clean_replay"] is True
    rep_reg = replay_rule_history(corpus, [{"rule_id": "R2", "active": True, "disallowed_template": "slam"}])
    assert rep_reg["regressions"] == 1 and rep_reg["clean_replay"] is False
    with pytest.raises(TypeError, match="history_corpus must be a list"): replay_rule_history("bad", rules)

def test_exemplar_bank_lifecycle_and_compatibility():
    bank = []
    rules = [{"rule_id": "R1", "active": True, "disallowed_template": "old_layout"}]
    ex1 = {"exemplar_id": "E1", "template_id": "slam", "aspect_ratio": "16:9", "script": "Newton physics laws"}
    res1 = manage_exemplar_bank("add", bank, exemplar=ex1, active_rules=rules)
    assert res1["active_count"] == 1 and res1["retired_count"] == 0
    with pytest.raises(ValueError, match="does not pass current rules"):
        manage_exemplar_bank("add", bank, exemplar={"template_id": "old_layout"}, active_rules=rules)
    audit = manage_exemplar_bank("audit_compatibility", bank, active_rules=[{"rule_id": "R2", "active": True, "disallowed_template": "slam"}])
    assert audit["retired_count"] == 1 and audit["retired_list"][0]["exemplar_id"] == "E1"

def test_retrieve_exemplars_ranking_and_bad_input():
    bank = [
        {"exemplar_id": "E1", "template_id": "slam", "aspect_ratio": "16:9", "script": "Newton forces motion", "retired": False},
        {"exemplar_id": "E2", "template_id": "split", "aspect_ratio": "9:16", "script": "Kinetic energy", "retired": False},
        {"exemplar_id": "E_RET", "template_id": "slam", "aspect_ratio": "16:9", "script": "Newton forces motion", "retired": True},
    ]
    ret = retrieve_exemplars(bank, {"template_id": "slam", "aspect_ratio": "16:9", "script": "Newton forces"}, top_k=2)
    assert len(ret) == 2 and ret[0]["exemplar_id"] == "E1" and "E_RET" not in [x["exemplar_id"] for x in ret]
    with pytest.raises(TypeError, match="query must be a dict"): retrieve_exemplars(bank, "bad")
    with pytest.raises(ValueError, match="top_k must be a positive integer"): retrieve_exemplars(bank, {}, top_k=0)

def test_run_model_migration_checklist():
    cfg = {"model_version": "gemini-2.5-flash"}
    smoke = [{"status": "PASS", "has_preamble": False}] * 5
    canary = {"baseline_mean_score": 90.0, "new_model_mean_score": 88.5, "semantic_error_count": 0}
    res = run_model_migration_checklist(cfg, smoke, canary)
    assert res["migration_approved"] is True and res["verdict"] == "PROCEED_REBASELINE"
    assert res["score_delta"] == pytest.approx(1.5, 0.01)
    with pytest.raises(ValueError, match="model_version"): run_model_migration_checklist({}, smoke, canary)
    res_held = run_model_migration_checklist(cfg, smoke, dict(canary, new_model_mean_score=80.0))
    assert res_held["migration_approved"] is False and res_held["verdict"] == "HOLD_MIGRATION"

def test_pipeline_wiring_improvement_program(tmp_path):
    res = run_pipeline(tmp_path, {"project_id": "P13_test", "run_improvement_program": True})
    assert "improvement_program" in res
    ip = res["improvement_program"]
    assert ip["status"] == "IMPROVEMENT_PROGRAM_READY" and "audit" in ip and "migration_status" in ip
