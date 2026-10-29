# 1. PACKET_HEADER
task_id: F-014            stage: REVIEW
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
- `src\pipeline.py`: StoryBible default creator (`create_default_story_bible`), StoryBible prompt builder (`build_story_bible_prompt`), Scene Author prompt builder (`build_scene_author_prompt`), 1-hop previous scene exit state extractor bounded <=80 tokens (`extract_scene_exit_state`), targeted repair / fresh restart prompt builder (`build_repair_or_restart_prompt`), content-dropping repair rejection validator (`validate_repair_entity_retention`), adaptive thinking step-down evaluator (`evaluate_thinking_step_down`), and SQLite scene attempt telemetry recorder (`record_scene_attempt`), all wired into `run_pipeline`
- `tests\regression\test_f014_story_bible_author.py`: Regression tests for StoryBible default generation, exit state extraction, scene author prompting, local repair vs global restart prompt construction, entity drop rejection rules, thinking level step-down logic, attempt recording in SQLite, and pipeline authoring execution
- `PHASE_LOG.md`: Phase P7 (F-014) terminal verification output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-014
result: passed=72 failed=0   report_sha256: 61dc2e085152433f84fec469d0ab6d70f3358c12fa2bb3620e00e50e8269306d   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-015 (Phase P8): Evaluation harness and gates (SPEC Section 13).



