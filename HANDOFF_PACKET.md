# 1. PACKET_HEADER
task_id: F-016            stage: REVIEW
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
- `src\pipeline.py`: Machine health inspection (`get_machine_health`), HTML dashboard rendering (`render_dashboard_html`), watchdog conditions evaluator (`check_watchdog_conditions`), alert throttling logic (`evaluate_alert_throttling`), dead-man switch scheduler (`schedule_dead_man_switch`), Task Scheduler autostart generator (`generate_autostart_task_cmd`), and watchdog observer runner (`run_watchdog_observer`), all wired into `run_pipeline`
- `scripts\watchdog_observer.py`: Task Scheduler CLI entrypoint for periodic monitoring and atomic status.html updates
- `tests\regression\test_f016_dashboard_watchdog.py`: Regression tests for machine health, dashboard HTML, alert conditions, 4-hour throttling, dead-man switch, autostart commands, observer run, and pipeline integration
- `PHASE_LOG.md`: Phase P9 (F-016) verification output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-016
result: passed=83 failed=0   report_sha256: e0b1279273a1ade8d551ea14861f3dfff1f0a1cbda28311d71b6ce7aeecc1d36   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-017 (Phase P10): Editor, overrides, editor_events (SPEC Section 11).





