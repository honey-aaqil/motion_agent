# 1. PACKET_HEADER
task_id: F-011            stage: REVIEW
date: 2026-10-28          tool: Antigravity

# 2. INVARIANTS_CONTRACT
- Max 2 LLM calls per scene; 503/429 never consume a call.
- Windows 11, 8 GB RAM; one heavy process at a time.
- SQLite WAL, single writer per column; no raw stderr or HTML in prompts.
- A gate that errors or sees zero boxes is FAIL, never PASS.
- Narration text is immutable; no LLM may change it.
- Protected files (SPEC.md, CONSTRAINTS.md, scripts\verify_done.py, tests\immutable\) are frozen.
- Diff budget is at most 5 files and 250 net lines per task; every public symbol in src\ must be wired to src\pipeline.py and fail a test when mutated to return None.

# 3. ARTIFACT_PAYLOAD
- `src\pipeline.py`: Sacred VO normalization preserving NFC/ZWJ/ZWNJ and converting CRLF (`normalize_sacred_vo`), deterministic two-column AV script parser extracting scenes/timecodes/directions/onscreen-text/VO/music/SFX/style and detecting uncertain lines (`parse_av_script`), VO round-trip reconstructor (`rebuild_vo_text`), Audio Pack generator with TTS directions, durations, music prompts (no vocals, loopable, margin) and SFX list (`generate_audio_pack`), and atomic filesystem exporter (`export_audio_pack`), wired directly into `run_pipeline`
- `tests\regression\test_f011_parser_audio_pack.py`: Regression tests for parameter validation, explicit errors on invalid inputs, NFC/ZWJ/ZWNJ preservation, byte-exact VO round trip, Appendix A fixture parsing, uncertain line flagging, and Audio Pack export
- `PHASE_LOG.md`: Phase P4 (F-011) terminal output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-011
result: passed=57 failed=0   report_sha256: a7d444edda2e89c6447b90ecd9bad6adc3a70bdd3c2b5d3eee14d58e00ca08e9   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-012 (Phase P5): Assets, ledger, license filter (SPEC Section 10).
