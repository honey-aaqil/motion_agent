HARD SESSION CONSTRAINTS (MAX 5. DO NOT SUMMARIZE OR COMPACT THESE)
1. ONE FEATURE, FRESH SESSION. Work on exactly one feature ID from
   feature_list.json. Stop and write HANDOFF_PACKET.md at 25 agent turns
   or 25,000 context tokens.
2. FROZEN FILES. Never edit, delete, skip or mock anything in SPEC.md,
   CONSTRAINTS.md, scripts\verify_done.py or tests\immutable\. In
   feature_list.json you may not change a status.
3. CHANGE BUDGET. Touch at most 5 files and 250 net lines per task. If the
   fix needs more files, a new dependency or a SQLite schema change, write
   STOP_AND_ASK.md and halt.
4. NO DEAD CODE. Every function you add under src\ must be imported and
   called by the real pipeline (src\pipeline.py or what it calls), never
   only by a test, a demo or a fixture.
5. VERIFIED DONE ONLY. Never write "tests pass" or "done" in prose. Run
   python scripts\verify_done.py --feature <ID> and attach the SHA-256 of
   reports\ctrf_latest.json from its output.
