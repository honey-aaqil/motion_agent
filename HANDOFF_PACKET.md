# 1. PACKET_HEADER
task_id: F-020            stage: REVIEW
date: 2026-11-01          tool: Antigravity

# 2. INVARIANTS_CONTRACT
- Max 2 LLM calls per scene; 503/429 never consume a call.
- Windows 11, 8 GB RAM; one heavy process at a time.
- SQLite WAL, single writer per column; no raw stderr or HTML in prompts.
- A gate that errors or sees zero boxes is FAIL, never PASS.
- Narration text is immutable; no LLM may change it.
- Protected files (SPEC.md, CONSTRAINTS.md, scripts\verify_done.py, tests\immutable\) are frozen.
- Diff budget is at most 5 files and 250 net lines per task; every public symbol in src\ must be wired to src\pipeline.py and fail a test when mutated to return None.

# 3. ARTIFACT_PAYLOAD
- `src\pipeline.py`: Improvement program implementation (`audit_failure_pool`, `manage_improvement_rule`, `replay_rule_history`, `manage_exemplar_bank`, `retrieve_exemplars`, `run_model_migration_checklist`), wired into `run_pipeline`
- `tests\regression\test_f020_improvement_program.py`: Regression tests for failure pool categorization & recommendation, rule mining & 1-step rollback, offline history replay (0 regressions), exemplar bank lifecycle & compatibility retirement, exemplar retrieval ranking, and model migration checklist.
- `PHASE_LOG.md`: Phase P13 (F-020) verification output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-020
result: passed=108 failed=0   report_sha256: 628bc39bc77057f0901009823e4495561c7d77da16ed833849cb90224530ade2   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Phase 6 Complete: Stage S4 Audio-Timing Synchronization with silence interval fallbacks, duration validation, and whisper.cpp alignment output validation (validate_whisper_alignment_output); wired into pipeline, /api/audio, and test_whisper_alignment_validation; 114/114 tests passing. Ready for Phase 7 (Stage S5 Dual-Ratio Chromium & FFmpeg rendering pipeline).
