# 1. PACKET_HEADER
task_id: F-018            stage: REVIEW
date: 2026-10-29          tool: Antigravity

# 2. INVARIANTS_CONTRACT
- Max 2 LLM calls per scene; 503/429 never consume a call.
- Windows 11, 8 GB RAM; one heavy process at a time.
- SQLite WAL, single writer per column; no raw stderr or HTML in prompts.
- A gate that errors or sees zero boxes is FAIL, never PASS.
- Narration text is immutable; no LLM may change it.
- Protected files (SPEC.md, CONSTRAINTS.md, scripts\verify_done.py, tests\immutable\) are frozen.
- Diff budget is at most 5 files and 250 net lines per task; every public symbol in src\ must be wired to src\pipeline.py and fail a test when mutated to return None.

# 3. ARTIFACT_PAYLOAD
- `src\pipeline.py`: Batched Visual critic (`build_visual_critic_montage`, `build_visual_critic_prompt`, `parse_visual_critic_response`, `record_visual_critic_review`, `evaluate_visual_critic_promotion`, `check_visual_critic_eligibility`) and low-quota mode (`should_activate_low_quota_mode`, `build_low_quota_scene_author_prompt`, `parse_low_quota_scene_author_response`, `evaluate_low_quota_golden_set`), all wired into `run_pipeline`
- `tests\regression\test_f018_visual_critic_low_quota.py`: Regression tests covering 2x2 montage with 6x6 grid overlay, fail-open shadow critic reports, database review records without blocking scenes, promotion criteria, headroom/eligibility checks, 2-scene batching prompts and parsing, and golden set entity coverage evaluations
- `PHASE_LOG.md`: Phase P11 (F-018) verification output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-018
result: passed=94 failed=0   report_sha256: abb37d5b419ef96b93adcccca0e0dfaecc8e58facadf7890b6a0a8fe49007701   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-019 (Phase P12): Packaging and 6-hour soak (SPEC Sections 16, 17).





