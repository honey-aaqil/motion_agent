# 1. PACKET_HEADER
task_id: F-012            stage: REVIEW
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
- `src\pipeline.py`: License filter accepting CC0, PD, CC-BY (with attribution), Pexels, Pixabay, Unsplash, Mixkit, Coverr, OFL, MIT, ISC, Apache-2.0 and silently rejecting NC, ND, ShareAlike, editorial-only, watermarked, and unknown licenses (`filter_asset_license`); Action-needed detector for risky user uploads, endorsement risks, and slots with no safe alternatives (`detect_action_needed`); AssetLedger manager for asset CRUD and atomic JSON export (`AssetLedger`); Ready-to-paste markdown attribution generator (`generate_credits_markdown`); SHA-256 hash-cached background removal with rembg fallback (`remove_background_cached`), wired directly into `run_pipeline`
- `tests\regression\test_f012_assets_and_ledger.py`: Regression tests for license filtering contracts and acceptance/silent rejections, action-needed warnings, asset ledger CRUD and atomic export, credits markdown generation, background removal caching by sha256 hash, and full pipeline wiring
- `PHASE_LOG.md`: Phase P5 (F-012) terminal output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-012
result: passed=63 failed=0   report_sha256: e497511d04e1a02507e142ec383634fb58fded6160b916dfbf842e8d3423ddac   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-013 (Phase P6): Timing and sentence anchors (SPEC Section 3).

