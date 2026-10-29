# 1. PACKET_HEADER
task_id: F-015            stage: REVIEW
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
- `src\pipeline.py`: Dataset loader (`load_eval_dataset`), SQLite scene trials recorder (`record_scene_trial`), exact mid-p McNemar calculator (`mcnemar_exact_mid_p`), paired bootstrap CI calculator (`paired_bootstrap_ci`), Stage 1 abort gate (`evaluate_stage1_gate`), Ship/Block decision gate (`evaluate_ship_block_gate`), WCAG contrast evaluator (`compute_wcag_contrast`), local visual metrics calculator (`compute_local_visual_metrics`), Goodhart guards checker (`check_goodhart_guards`), vision-judge calibration evaluator (`compute_judge_calibration`), human contact sheet generator (`generate_human_contact_sheet`), and contact sheet gate evaluator (`evaluate_contact_sheet_gate`), plus `scene_trials` SQLite table, all wired into `run_pipeline`
- `tests\regression\test_f015_eval_harness.py`: Regression tests for dataset parsing, trials persistence, McNemar, bootstrap CI, Stage 1 abort, Ship/Block gate, WCAG contrast and bounding-box edge overlap/clutter, Goodhart guards, judge calibration metrics, contact sheet generation and gating, and pipeline integration
- `PHASE_LOG.md`: Phase P8 (F-015) terminal verification output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-015
result: passed=78 failed=0   report_sha256: 81a9cd2c13b16296809ca989868025e093afb694472aa4ff10d2a2015fa60edd   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-016 (Phase P9): Dashboard, watchdog, auto-start (SPEC Sections 11, 12).




