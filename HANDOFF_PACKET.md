# 1. PACKET_HEADER
task_id: F-010            stage: REVIEW
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
- `src\pipeline.py`: Templates catalog (14 hand-crafted templates supporting 9:16 portrait and 16:9 landscape layouts), layout configs (`get_layout_config`), zero-call canonicalizer with JSON bracket repair, story token replacement and overhang clamping (`canonicalize_scene_spec`), schema/timing/relative-anchor/word-count validator (`validate_scene_spec`), DOM geometry, caption-safe zone, overlap, trap and contrast gate (`audit_dom_layout`), and startup sabotage preflight runner (`run_dom_sabotage_preflight`), wired directly into `run_pipeline`
- `tests\regression\test_f010_templates_and_gates.py`: Regression tests for parameter validation, explicit errors on invalid inputs, template catalog completeness, canonicalizer repair & clamping, validator constraints, DOM layout violations, sabotage preflight, and pipeline wiring
- `PHASE_LOG.md`: Phase P3 (F-010) terminal output recorded

# 4. DETERMINISTIC_TEST_LOG
command: python scripts\verify_done.py --feature F-010
result: passed=51 failed=0   report_sha256: 0aa73d384f0b59f93c9414db78df51abe45188df7cfcdd4407a2fadd3cdb460f   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS

# 5. REVIEWER_INSTRUCTIONS
Inspect ARTIFACT_PAYLOAD against INVARIANTS_CONTRACT. List only concrete
defects (location, mechanism, severity Critical/Major/Minor) and give minimal
unified diffs. Do not rewrite working functions. Do not praise. Say
"no defects found" only if you checked every invariant.

# 6. DELTA_STATE_FOR_NEXT_BUILDER
open_defects: []
locked_files: ["SPEC.md", "CONSTRAINTS.md", "scripts/verify_done.py", "tests/immutable/test_immutable_sample.py"]
next_atomic_action:
  Start Feature F-011 (Phase P4): Parser, VO round trip, Audio Pack (SPEC Sections 9, 16).
