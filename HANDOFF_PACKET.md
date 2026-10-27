# 1. PACKET_HEADER
task_id: F-007            stage: REVIEW
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
- `src\pipeline.py`: Mock Gemini chaos server (`start_gemini_chaos_server`, `stop_gemini_chaos_server`, `_GeminiChaosHandler`) supporting 503 storm, 429 minute & day, truncated JSON, empty 200, slow response, and wrong model version; `compute_llm_backoff` with exponential backoff & full jitter; `call_gemini_gateway` with chaos mode headers, HTTP error handling, timeout / network error handling, `api_rate_ledger` tracking (503 does not increment call count), and pipeline wiring via `run_pipeline`
- `tests\regression\test_f007_chaos_server.py`: Regression tests covering backoff math and jitter bounds, chaos server bad inputs, all chaos modes, ledger non-increment on 503, clock-mocked full-state-machine replay (200, 503, 503, 429, midnight reset, crash, lease expiry, 200), and pipeline wiring
- `PHASE_LOG.md`: Phase P1 (F-007) terminal output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-007
result: passed=37 failed=0   report_sha256: 58ad5115ca0296742db832440e3081590f6ff93705889928ff88226bdcc6a8cf   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-008 (Phase P2): Deterministic renderer and chunking (SPEC Section 12).
