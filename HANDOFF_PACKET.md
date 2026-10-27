# 1. PACKET_HEADER
task_id: F-004            stage: REVIEW
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
- `src\pipeline.py`: Gemini diagnostics, configuration validation, backoff with full jitter calculation, status classification, and 503 load simulation helpers wired to `run_pipeline`
- `tests\regression\test_f004_gemini.py`: Regression tests verifying bad config rejections, jitter backoff bounds, status code classification (200, 503, 500, 429, 400, 404), fallback switching, queue pause, 30-request 503 load simulation, and pipeline wiring
- `SPIKES.md`: SP-06 empirical spike verified
- `PHASE_LOG.md`: Phase P0 (F-004) terminal output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-004
result: passed=24 failed=0   report_sha256: c176bdc97f8cf52a022cdc5dfcacc2605536e59c683b9d9489e011223cf1f655   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-005 (Phase P1): SQLite schema, state machine, leases (SPEC Section 5 and 12).
