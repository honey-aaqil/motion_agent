# 1. PACKET_HEADER
task_id: F-002            stage: REVIEW
date: 2026-10-26          tool: Antigravity

# 2. INVARIANTS_CONTRACT
- Max 2 LLM calls per scene; 503/429 never consume a call.
- Windows 11, 8 GB RAM; one heavy process at a time.
- SQLite WAL, single writer per column; no raw stderr or HTML in prompts.
- A gate that errors or sees zero boxes is FAIL, never PASS.
- Narration text is immutable; no LLM may change it.
- Protected files (SPEC.md, CONSTRAINTS.md, scripts\verify_done.py, tests\immutable\) are frozen.
- Diff budget is at most 5 files and 250 net lines per task; every public symbol in src\ must be wired to src\pipeline.py and fail a test when mutated to return None.

# 3. ARTIFACT_PAYLOAD
- `scripts\check_env.ps1`: environment check script covering Node, git, ffmpeg/ffprobe, Python via py, Playwright chromium-headless-shell, whisper-cli + model, SQLite >= 3.51.3, RAM/disk, power plan, page file, Defender exclusion
- `src\pipeline.py`: `validate_environment()` checking required keys and SQLite >= 3.51.3, wired to `run_pipeline()`
- `tests\regression\test_f002_env.py`: 7 regression tests verifying type checks, missing keys, SQLite version rejection, valid report structured output, wiring into `run_pipeline()`, and `check_env.ps1` execution in `-JsonOut` and human modes

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-002
result: passed=16 failed=0   report_sha256: c1446444ea8a87e45ee09fc6bb5708e19f7ca3eb3849b909344692e0e6a45950   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Phase P0 (F-003): Spikes: render memory in openfilm, whisper latency on EN/HI/TA,
  rembg on 10 images, DOM gate defect injection, Gemini diagnostics/quota/load test,
  and UTF-8 round trip through SQLite/HTTP/PowerShell.
