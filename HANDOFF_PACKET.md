# 1. PACKET_HEADER
task_id: F-019            stage: REVIEW
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
- `src\pipeline.py`: Deliverables packaging (`build_cue_sheet`, `generate_thumbnail_options`, `bundle_editable_project`, `assemble_final_package`) and chaos soak simulation (`simulate_chaos_soak_test`), all wired into `run_pipeline`
- `tests\regression\test_f019_package_and_soak.py`: Regression tests for packaging deliverables (out/ hierarchy, 6 video outputs, cue sheets in CSV/MD, 3 thumbnail options per ratio, editable_project.zip under 260 char paths) and 6-hour chaos soak (120 scenes, fault injection catch, WAL zero-loss recovery, RAM budget)
- `PHASE_LOG.md`: Phase P12 (F-019) verification output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-019
result: passed=101 failed=0   report_sha256: b1ccc97b0e2cacfc1b5b5094f487afe97b0ca62f267fa12ffa93304478e434ab   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-020 (Phase P13): Improvement program (rules, exemplar bank) (SPEC Section 14).






