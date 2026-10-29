# 1. PACKET_HEADER
task_id: F-013            stage: REVIEW
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
- `src\pipeline.py`: Scene timing calculator (`compute_scene_timing`), uploaded audio file validator checking missing and extra files (`validate_uploaded_audio_files`), sentence anchor extraction & alignment with whisper and silence fallback and confidence tracking (`align_sentence_anchors`), cue anchor timing resolver prohibiting absolute timestamps (`resolve_cue_timing`), whisper CLI command generator (`build_whisper_alignment_cmd`), and ffprobe duration measurement (`measure_audio_duration_ffprobe`), wired directly into `run_pipeline`
- `tests\regression\test_f013_timing_and_anchors.py`: Regression tests for audio duration measurement, file upload validation, single and multi-sentence alignment, silence fallback, confidence mapping, multilingual anchors (hi, ta), cue resolution with offset/clamping and syntax validation, whisper command builder, and full pipeline wiring
- `PHASE_LOG.md`: Phase P6 (F-013) terminal output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-013
result: passed=67 failed=0   report_sha256: 45d4db5e216af8b184171bf46d0c7bbd87f34d146f675720ae8df14062e88aad   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-014 (Phase P7): StoryBible, Scene Author, repair/restart routing (SPEC Section 4).


