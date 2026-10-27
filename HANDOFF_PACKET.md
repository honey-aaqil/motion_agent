# 1. PACKET_HEADER
task_id: F-008            stage: REVIEW
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
- `src\pipeline.py`: Deterministic renderer and chunking helpers (`compute_render_chunks`, `get_chromium_render_flags`, `check_render_resource_watchdog`, `adjust_chunk_size_on_respawns`, `clean_stray_processes`, `build_ffmpeg_encode_cmd`, `build_ffmpeg_concat_cmd`, `build_ffmpeg_mix_cmd`, `render_scene_chunk`) enforcing <= 900 frame chunking, 10 GB disk floor, 2.8 GB process tree / 1.2 GB RAM watchdog, consecutive respawn fallback to 300 frames, ffmpeg encoding with libx264 yuv420p 30 fps CRF 18-20 +faststart and 2 threads, and pipeline wiring via `run_pipeline`
- `tests\regression\test_f008_renderer.py`: Regression tests covering chunk splitting and input rejection, Chromium flags, memory & disk watchdog thresholds, respawn adaptation, ffmpeg encode/concat/mix commands, process cleanup, chunk rendering, and pipeline wiring
- `PHASE_LOG.md`: Phase P2 (F-008) terminal output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-008
result: passed=41 failed=0   report_sha256: bd89f696dc53028d05b7d8d3eda42d4ba2279bde62ca89eb1e9304b5ff1a1efe   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-009 (Phase P2): Render canaries INV-1..6 with sabotage fixtures (SPEC Section 7).
