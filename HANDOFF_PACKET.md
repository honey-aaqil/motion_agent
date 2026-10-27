# 1. PACKET_HEADER
task_id: F-006            stage: REVIEW
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
- `src\pipeline.py`: SQLite initialization with `llm_queue` and `llm_log` tables, rate governor with monotonic interval enforcement (15.5s) & daily quota checks against `api_rate_ledger`, persistent queue with priority dispatching (editor outranks batch) & SHA-256 prompt hash idempotency caching, model version assertion (catching silent auto-routing), call attempt logging, and dashboard formatting display, wired to `run_pipeline`
- `tests\regression\test_f006_rate_governor.py`: Regression tests covering rate governor interval and daily quota cap rejections, queue priority ordering and idempotency, model version mismatch detection, call logging, and pipeline wiring
- `PHASE_LOG.md`: Phase P1 (F-006) terminal output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-006
result: passed=33 failed=0   report_sha256: 1699fc31ed2497703412fd9369207a566463dd30d264bbf5cb7b34e6ce0b6cd0   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-007 (Phase P1): Mock Gemini chaos server (SPEC Section 6, 17).
