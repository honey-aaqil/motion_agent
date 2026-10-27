# 1. PACKET_HEADER
task_id: F-005            stage: REVIEW
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
- `src\pipeline.py`: SQLite initialization with WAL mode & pragmas, table schemas (`projects`, `scenes`, `scene_attempts`, `api_rate_ledger`, `editor_events`), state transition machine with `MAX_LLM_CALLS_PER_SCENE = 2`, heartbeat leases with 90s expiry & reclaim, and error routing classifier (`LOCAL_REPAIR` vs `GLOBAL_RESTART` vs `NEEDS_HUMAN_EDIT`), all wired to `run_pipeline`
- `tests\regression\test_f005_state_machine.py`: Regression tests covering database schema & WAL pragmas, state transition validation & illegal rejection, lease acquisition/renewal/reclaim, and error routing classification
- `PHASE_LOG.md`: Phase P1 (F-005) terminal output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-005
result: passed=29 failed=0   report_sha256: 307c645d2dad2a8e3802abc4cb13259e039a93535f1f076a7a9fe954df6bda6d   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-006 (Phase P1): Rate governor and gateway (SPEC Section 6).

