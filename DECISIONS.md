# Architectural Decisions Log

| ID | Date | Decision | Rationale |
|---|---|---|---|
| D-001 | 2026-10-26 | Orchestrator language: Python 3.11+ (`sqlite3`, `pytest`, `psutil`, Playwright for Python); Node used only as subprocess for `openfilm`. | Single language for state machine, gates, tests, and builder tooling. |
| D-002 | 2026-10-26 | Native Windows 11 at `C:\motion-agent` (not WSL2, not under OneDrive). | Avoids WSL2 memory reservation on an 8 GB RAM host and keeps paths short. |
| D-003 | 2026-10-26 | Plain Python state machine over SQLite WAL; no orchestration framework (no LangGraph or ADK). | Low memory footprint, debuggable by two people, no framework lock-in. |
| D-004 | 2026-10-26 | Plain Python and SQLite scripts for evaluation; no evaluation platform. | Zero extra daemon overhead; deterministic local replay. |
| D-005 | 2026-10-26 | Single API key per project; never rotate keys across projects. | Keys in one project share quota; rotation risks project suspension. |
| D-006 | 2026-10-26 | Explicit UTF-8 without BOM for all file I/O and LF line endings via `.gitattributes`. | Prevents Windows console code-page corruption of Hindi and Tamil scripts. |
