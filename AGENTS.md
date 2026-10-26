BUILDER PROTOCOL (Antigravity + Gemini 3.8 Flash)

1. Start (turns 1-3)
   - Run: python scripts\verify_done.py --baseline  BEFORE editing anything.
     If any test in tests\regression or tests\immutable fails, your only task
     this session is to fix that regression or git reset --hard to the last
     green commit.
   - Read CONSTRAINTS.md, the DELTA section of HANDOFF_PACKET.md, the one
     feature_list.json entry marked FAIL with the highest priority, and ONLY
     the SPEC.md sections that entry lists. Do not load the whole spec.
2. Test first (turns 4-15)
   - tests\immutable\ is read-only. It holds human-written cross-feature and
     bad-input tests. Never touch it.
   - Write tests\regression\test_<feature_id>.py BEFORE editing src\.
     Include at least one test where invalid input must raise an explicit
     error (no silent acceptance).
3. Implement (turns 16-22)
   - Edit src\ so your tests and all existing tests pass.
   - Limits: at most 5 files, 250 net lines, 3 simultaneous structural changes.
   - STOP AND ASK (write STOP_AND_ASK.md) if: a locked test contradicts SPEC.md
     (never hardcode answers for test inputs); you need more than 5 files, a new
     dependency, or a schema change; the same test still fails after 3
     edit-test cycles.
4. Finish (turns 23-25)
   - Run python scripts\verify_done.py --feature <ID>.
   - Update HANDOFF_PACKET.md (delta section only). Commit. End the session.
Rules about honesty: never mark anything done yourself; report failures as
failures; never weaken, skip or delete a test to make it pass.
