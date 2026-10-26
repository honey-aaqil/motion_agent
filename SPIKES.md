# Empirical Spikes & Verification Log (Phase P0)

All items marked `[verify]` in `SPEC.md` are recorded here once measured on the host machine. Empirical host measurements override directional research numbers.

| Spike ID | Target | Metric / Verification Question | Status | Measured Value / Fallback |
|---|---|---|---|---|
| SP-01 | Free RAM baseline | Available RAM on Windows 11 (8 GB total) before stack start | PENDING (P0) | TBD |
| SP-02 | `openfilm` 60 s render (1080x1920) | Peak process-tree working set, sec/frame, kill-and-resume, 1 vs 2 workers | PENDING (P0) | TBD |
| SP-03 | `whisper-cli.exe` | 60 s EN, HI, TA latency & timestamp accuracy (`base`, `small`, `medium`) | PENDING (P0) | TBD |
| SP-04 | `rembg` (`u2netp` CPU) | Memory & latency across 10 images; Python version compatibility on Windows | PENDING (P0) | TBD |
| SP-05 | DOM Geometry & Contrast Gate | Zero-LLM detection of 3 injected defects (overlap, low contrast, overflow) | PENDING (P0) | TBD |
| SP-06 | Gemini API diagnostics | Exact model ID, `model_version`, daily quota & reset time, JSON schema, vision, thinking tokens, 30-req 503 load test | PENDING (P0) | TBD |
| SP-07 | UTF-8 HI/TA round trip | Byte-exact round trip across file, SQLite, HTTP, and PowerShell pipe | PENDING (P0) | TBD |
| SP-08 | SQLite version | Confirm `sqlite3.sqlite_version >= 3.51.3` | PENDING (P0a) | TBD |
| SP-09 | Builder ACL lock | Confirm `icacls` read-only lock blocks file writes from the builder terminal | PENDING (P-1) | Verified by `test_sabotage_readonly_lock_blocks_edit` |
