# 1. PACKET_HEADER
task_id: F-001            stage: REVIEW
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
- `CONSTRAINTS.md`, `AGENTS.md`, `feature_list.json`, `.gitattributes`, `.env.example`
- `DECISIONS.md`, `SPIKES.md`, `PHASE_LOG.md`, `TOOLS_LICENSES.md`
- `src\pipeline.py`: `durable_replace()` (MoveFileExW atomic write-through) and `run_pipeline()`
- `scripts\verify_done.py`: 6-step verifier (`--baseline`, `--pre-commit`, `--feature`, `--audit-week`) with built-in CTRF JSON generator, protected-file diff check, 5-file/250-line budget check, AST reachability check, and return-None mutation check
- `.git\hooks\pre-commit`: invokes `python scripts/verify_done.py --pre-commit`
- `tests\immutable\test_immutable_sample.py`: held-out governance and bad-input check
- `tests\regression\test_f001_governance.py`: 5 sabotage checks (failing earlier test, edited protected file, 6-file diff, uncalled function in `src\`, read-only lock write rejection)

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-001
result: PENDING_HOST_EXECUTION   report_sha256: PENDING_HOST_EXECUTION   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PENDING_HOST_EXECUTION

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Phase P0a (F-002): implement `scripts\check_env.ps1` to verify Node, git,
  ffmpeg/ffprobe, Python via `py`, Playwright `chromium-headless-shell`,
  `whisper-cli.exe`, SQLite >= 3.51.3, free RAM/disk, power plan, page file,
  and Defender exclusion for `C:\motion-agent`.
