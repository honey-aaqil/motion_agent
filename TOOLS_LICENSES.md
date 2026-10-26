# Tools & Code Reuse License Ledger

Policy: Private project. Record every external tool and reference repository here. Never copy code from AGPL or non-commercial repositories (`GTKottman/mortiflix-oss`, `feitangyuan/onetake`, Meta MMS non-commercial weights).

| Tool / Repository | Purpose | License | Usage Mode | Verification Status |
|---|---|---|---|---|
| Python 3.11+ (`sqlite3`, `pytest`, `psutil`) | Core orchestrator, state machine, test runner | PSF / MIT / BSD | Direct dependency | Standard |
| `openfilm/openfilm` | HTML frame renderer, Studio editor base | MIT | Subprocess / local server | Verify Windows build in P0 |
| `COPPSARY/Motify` | Presets and editor patterns | Apache-2.0 | Pattern reference | Verify repo name & license in P0 |
| `heygen-com/hyperframes` | Motion block library, lint rules | Verify in P0 | Registry/lint reference only | Do not use CLI as renderer |
| `nexu-io/motion-anything` | Motion tokens and recipes | Verify in P0 | Reference | Pending P0 check |
| `emilkowalski/skills`, `LottieFiles/motion-design-skill` | Animation rules for prompts | Verify in P0 | Reference | Pending P0 check |
| `Leonxlnx/cinetic` | Technique picker, lints | Verify in P0 | Reference | Pending P0 check |
| `howseen-ai/claude-motion-design` | Seek-and-capture reference, asset fetch | Verify in P0 | Reference | Pending P0 check |
| `alchaincyf/huashu-art-motion`, `gojiplus/layoutlens`, `nolangz/pixel2motion` | Layout audit concepts | Verify in P0 | Reference | Custom code on `getBoundingClientRect()` |
| `nateherkai/herk-edit-kit` | Slot contract, editing timing | Verify in P0 | Reference | Pending P0 check |
| `alexgreensh/anidoodle` | Frame capture determinism contract | Verify in P0 | Reference | Pending P0 check |
| Playwright (`chromium-headless-shell`) | Deterministic headless frame capture & DOM gate | Apache-2.0 | Direct tool | Verify in P0a |
| `ffmpeg` / `ffprobe` | Audio duration, encode, canary gates INV-1..4 | LGPL / GPL | External binary | Verify in P0a |
| `whisper.cpp` (`whisper-cli.exe`) | Sentence timestamp alignment (EN, HI, TA) | MIT | External binary | Verify in P0a |
| `rembg` (`u2netp` via `onnxruntime`) | CPU background removal | MIT | Python library | Verify Windows Python support in P0 |
| `GTKottman/mortiflix-oss` | N/A | Restricted / AGPL / NC | **BANNED (ideas only)** | Enforced |
| `feitangyuan/onetake` | N/A | Restricted / NC | **BANNED (ideas only)** | Enforced |
| Meta MMS Aligner | N/A | Non-Commercial | **BANNED** | Enforced |
