# 1. PACKET_HEADER
task_id: F-009            stage: REVIEW
date: 2026-10-28          tool: Antigravity

# 2. INVARIANTS_CONTRACT
- Max 2 LLM calls per scene; 503/429 never consume a call.
- Windows 11, 8 GB RAM; one heavy process at a time.
- SQLite WAL, single writer per column; no raw stderr or HTML in prompts.
- A gate that errors or sees zero boxes is FAIL, never PASS.
- Narration text is immutable; no LLM may change it.
- Protected files (SPEC.md, CONSTRAINTS.md, scripts\verify_done.py, tests\immutable\) are frozen.
- Diff budget is at most 5 files and 250 net lines per task; every public symbol in src\ must be wired to src\pipeline.py and fail a test when mutated to return None.

# 3. ARTIFACT_PAYLOAD
- `src\pipeline.py`: Post-render canary checkers (`check_canary_inv1_streams`, `check_canary_inv2_blackdetect`, `check_canary_inv3_freezedetect`, `check_canary_inv4_audio_loudness`, `check_canary_inv5_golden_drift`, `check_canary_inv6_ledger`), canary gate runner (`run_canary_gate`), and sabotage suite runner (`run_sabotage_suite`), wired directly into `run_pipeline`
- `tests\regression\test_f009_canaries.py`: Comprehensive regression tests covering valid and sabotage executions for canaries INV-1..6, explicit parameter validation errors, gate runner, and sabotage suite verification
- `scripts\render_canary_gate.py`: CLI wrapper entrypoint for running canary gate
- `scripts\run_sabotage_suite.py`: CLI wrapper entrypoint for running sabotage suite
- `PHASE_LOG.md`: Phase P2 (F-009) terminal output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-009
result: passed=48 failed=0   report_sha256: 753f4b42efd35b101a3da406155d100b44091dd206cd9e61261184dfd1eff586   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-010 (Phase P3): Templates, canonicalizer, validator, DOM gate (SPEC Sections 7, 8).
