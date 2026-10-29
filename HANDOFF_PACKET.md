# 1. PACKET_HEADER
task_id: F-017            stage: REVIEW
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
- `src\pipeline.py`: Slot overrides (`apply_slot_overrides`), asset replacement/upload security (`replace_scene_asset`), browser engine check (`check_editor_browser_support`), timeline operations (`edit_scene_timeline`), regeneration payload builder (`prepare_scene_regeneration`), re-render cache key hashing (`compute_rerender_cache_key`), editor gate warnings/auto-fix (`evaluate_editor_gates`), and editor events logging (`record_editor_event`), all wired into `run_pipeline`
- `tests\regression\test_f017_editor_overrides.py`: Regression tests covering slot overrides, safe asset uploads, Chromium warning, timeline edits, regeneration payload preparation, rerender cache key hashing, editor gates, and editor events table logging
- `PHASE_LOG.md`: Phase P10 (F-017) verification output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-017
result: passed=88 failed=0   report_sha256: e6e3cfcdf1791e5b19a44a6cfed6b7a3a94acc581ac57af918b2bd81724e6515   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-018 (Phase P11): Visual critic (shadow) and low-quota mode (SPEC Section 12).





