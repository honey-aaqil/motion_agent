# 1. PACKET_HEADER
task_id: F-003            stage: REVIEW
date: 2026-10-27          tool: Antigravity

# 2. INVARIANTS_CONTRACT
- Max 2 LLM calls per scene; 503/429 never consume a call.
- Windows 11, 8 GB RAM; one heavy process at a time.
- SQLite WAL, single writer per column; no raw stderr or HTML in prompts.
- A gate that errors or sees zero boxes is FAIL, never PASS.
- Narration text is immutable; no LLM may change it.
- Protected files (SPEC.md, CONSTRAINTS.md, scripts\verify_done.py, tests\immutable\) are frozen.
- Diff budget is at most 5 files and 250 net lines per task; every public symbol in src\ must be wired to src\pipeline.py and fail a test when mutated to return None.

# 3. ARTIFACT_PAYLOAD
- `src\pipeline.py`: P0 spike helpers (`validate_audio_filename`, `normalize_vo_text`, `split_sentences`, `compute_scene_duration`, `verify_utf8_roundtrip`, `check_process_memory_budget`) wired to `run_pipeline`
- `tests\regression\test_f003_spikes.py`: 4 regression tests verifying invalid input rejections, case-insensitive audio matching, VO normalization & danda split, duration calculation, SQLite WAL UTF-8 byte-exact round trip, and process memory budget
- `SPIKES.md`: Updated empirical measurements and fallbacks for SP-01, SP-02, SP-03, SP-04, SP-07

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-003
result: passed=20 failed=0   report_sha256: 189c02d5597e8e60b05008fe99deb4fa3fe336e8aeed8df4b7a34377a07d903c   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-004 (Phase P0): Gemini diagnostics, quota, 503 load test (SPEC Section 6).
