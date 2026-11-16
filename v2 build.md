# Motion Studio v2: a Higgsfield-style director workflow, rendered by code

For Antigravity (Gemini 3.8 Flash, high). Repo: https://github.com/honey-aaqil/motion_agent (public, one commit `0d71ad2`).

---

## 0. What I found in the repo (I ran it)

I cloned the repo, started the dashboard, posted a script, clicked render, and opened the video with ffprobe.

| Claim in PHASE_LOG | What the code does | Evidence |
|---|---|---|
| Dashboard works | **Real.** `python run_gui.py` serves HTTP 200, accepts a script, stores scenes in SQLite. | I ran it. |
| "Deterministic renderer" (F-008) | **Fake.** `render_scene_chunk(..., mock_frames=True)` writes 64 zero bytes. | `src/pipeline.py:612` |
| "Render" button | **Fake.** `/api/render_video` runs ffmpeg `lavfi color=0x0b0f19` plus `anullsrc`: a solid dark-blue video with silent audio, regardless of your script. | `pipeline.py:2109`; ffprobe gives h264 1920x1080, and the extracted frame has **1 unique colour**. |
| "Preview stills" (F-010) | **Fake.** Every still is the same 1-pixel PNG. | `pipeline.py:1239` |
| Gemini gateway | Only talks to the repo's own mock server; it never reads `GEMINI_API_KEY` for a call. | `pipeline.py:479` |
| Playwright / Chromium | **Never imported.** It is only a name in an environment check. | grep over `src/` |
| Soak, 503 load, canaries | Pure functions over hand-made input lists. | `pipeline.py:179, 1002, 2524` |
| Architecture | One 2,619-line `src/pipeline.py` (138 functions) and one 862-line HTML file. | `wc -l` |

So the shell (dashboard, parser, state machine, license ledger, governance) exists, but **the engine that makes video does not**. All 108 tests pass because they test the fake. This is why it "doesn't work as planned". Rewriting the whole thing is not needed. The engine has to be built, and the rule that let fakes pass has to be closed.

## 1. What "like Higgsfield, but with code" means

[Higgsfield's Cinema Studio](https://higgsfield.ai/blog/cinema-studio-guide) is a director workflow: pick a camera rig (lens, focal length, aperture), make a **Hero Frame** still, approve it, then direct motion with named camera moves, speed ramps, a genre that sets pacing, up to 6 shots, up to 3 consistent characters, and grid storyboards (2x2 to 4x4). The pixels come from a video AI model.

Here the pixels come from **code**: an HTML/CSS scene with a virtual 3D camera, captured frame by frame by Chromium and encoded by ffmpeg. The workflow is the same; the output is motion graphics, not photoreal footage.

| Higgsfield control | Motion Studio equivalent (all real, all deterministic) |
|---|---|
| Prompt to clip | Prompt or AV script, then Gemini writes a **Shot Plan** (JSON, not HTML), then renderer |
| Camera rig: lens, aperture | `lens_mm` sets perspective (`perspective_px = viewport_width * lens_mm / 36`); `aperture` sets depth blur (`blur_px = k * abs(z - focus_z) / f_number`) |
| Named camera moves | 12 parametric moves: dolly in/out, truck L/R, pan, tilt, orbit, crane up/down, push-through, whip pan, handheld drift |
| Speed ramp | time remap curve per shot (slow, linear, speed up, hold) |
| Hero Frame | render one still of the shot at its best moment, approve it before any motion |
| Grid storyboard 2x2..4x4 | contact sheet of N variants (look, palette, camera) rendered as real stills in seconds |
| Genre | pacing preset: cut length, easing, camera energy, palette, type style |
| Up to 6 shots | unlimited shots; chunked rendering for long videos |
| 3 consistent characters | **Cast**: up to 3 reusable assets (SVG or background-removed cutouts) with emotion presets (pose, tilt, bounce), identical across shots |
| Start/end frame transitions | shot transitions: match cut, whip pan, push-through |
| 3D scene mode | live preview player in the browser using the same renderer; drag to orbit, which saves camera keyframes |
| Saved camera presets | saved user presets (menu) |

**Honest limits.** Code cannot make photoreal people, real footage or generated faces. "Characters" are vector or cut-out assets. The look will be strong motion graphics and 2.5D parallax, not film. If you want AI-generated footage later, it can be an optional asset source behind the same Shot Plan, but it is not in this plan.

## 2. Proof that the engine is feasible (spike, not production)

I wrote a 40-line scene (`scene.html`) with a virtual camera (dolly-in, orbit, parallax layers, rack-focus blur, animated headline) and a 30-line renderer (`render.py`: Playwright seeks `window.seek(t)`, takes a JPEG screenshot per frame, pipes to ffmpeg). Both are attached.

- **Result:** valid h264 mp4s in 1080x1920 and 1920x1080; frames differ over time (877, 1,326 and 1,538 unique colours at 0.1, 1.0 and 1.9 s, versus 1 for the repo's "render").
- **Speed:** 0.155 s/frame (9:16) and 0.123 s/frame (16:9) on my Linux sandbox. That is NOT your laptop: unmeasured, and complex scenes are slower. A 10-minute video is 18,000 frames, so 24 hours allows up to 4.8 s/frame. The headroom is large, but measure it on your 8 GB machine in F-101.
- **It also showed a real bug class:** in 9:16 the headline "Ship faster" at 120 px is clipped by the frame edge. That is exactly what the DOM layout gate (F-103) must catch, using real `getBoundingClientRect`, not hand-made boxes.

## 3. Part A: human steps (you)

1. `git tag v1-shell` on the current state.
2. **Close the loophole (frozen files, so you do it, not the builder).** Add `tests/immutable/test_no_fake_render.py` (Part E has the code). It fails the build if `src/` contains `anullsrc`, `color=c=` or `mock_frames=True` in a render path, or if the latest end-to-end report is missing or older than the last change to `src/`. Commit it, then re-run the lock commands you used before (`attrib`, `icacls`).
3. Add the F-100 to F-116 entries (Part C) to `feature_list.json`, status FAIL.
4. Put `GEMINI_API_KEY` in `.env` (planner sessions need it; everything else runs without a key).
5. Free disk (10 GB or more) and RAM (1.2 GB or more) as before. Chromium plus ffmpeg is the heavy part.
6. One fresh Antigravity session per feature, in the order in Part C. After each, run `python scripts\e2e_smoke.py --all` yourself and look at the video. **If you cannot see a changing picture, the session did not finish.**

## 4. Part B: architecture to build

```
src\
  pipeline.py            thin shim that re-exports (keeps the old wiring check satisfied)
  core\                  state machine, rate governor, ledger, parser (moved from pipeline.py, no behaviour change)
  engine\
    shot.html            the one scene page: loads a Shot Plan, exposes window.seek(t) and window.ready
    camera.js            virtual camera: moves, lens, aperture, speed ramp
    looks\               12 looks, each with portrait and landscape layout (HTML + CSS + data-slot)
    render.py            Playwright to ffmpeg pipe; chunking; respawn; resume
    stills.py            Hero Frame and storyboard grid (real PNGs)
    gate.py              real-DOM layout gate (overflow, safe area, contrast, overlap)
  planner\               Gemini client (real HTTP), prompts, repair loop, low-quota batch
  studio\                server + UI (wizard)
scripts\e2e_smoke.py     runs scenarios against the real engine, writes reports\e2e_latest.json
```

**Shot Plan schema (v1):**
```json
{"version":1,"title":"...","ratios":["9:16","16:9"],"genre":"explainer",
 "cast":[{"id":"C1","asset":"assets/c1.svg","role":"host"}],
 "shots":[{"id":"SH01","scene":"S01","duration":3.0,"look":"parallax_cards",
   "camera":{"move":"dolly_in","lens_mm":35,"aperture":2.8,"focus":"fg","speed":"ease_in_out"},
   "slots":{"headline":"Ship faster","sub":""},"cast":["C1"],"emotion":"confident",
   "transition_out":"whip_pan","anchors":{"headline":"@s1.start+0.2s"}}]}
```

**Rules that never change:** the LLM writes the Shot Plan (data), never raw HTML; every value is checked against the schema and a whitelist; looks are templates authored once by humans or by the builder under review; every frame is a pure function of `t` (no `Date.now`, no CSS transitions, no random without a seed), so any shot can be re-rendered identically.

**Product definition of "works" (end-to-end scenarios, all on the real engine):**

| ID | Scenario | PASS means |
|---|---|---|
| E2E-A | Prompt to Hero Frame | a real PNG with more than 100 unique colours exists in both ratios and its text is inside the safe area |
| E2E-B | Motion | ffprobe: h264, 30 fps, right size; frame at 25% differs from frame at 75% by more than a set pixel threshold; the camera move moves content in the expected direction |
| E2E-C | Storyboard grid | a 2x2 sheet of 4 different stills |
| E2E-D | Prompt to finished video | one prompt, real Gemini call (or the mock server only in CI), 3 to 6 shots, both ratios, audio present |
| E2E-E | Edit | change a headline in the studio; only that shot's clip is re-rendered |
| E2E-F | Resilience | kill the render process tree mid-run; restart resumes from the last finished chunk |
| E2E-G | Package | 6 videos (3 languages by audio only, both ratios), credits.md, editable bundle |

Completion is reported only as "N of 7 scenarios PASS".

## 5. Part C: feature list (JSON entries and order)

```json
[
 {"id":"F-100","phase":"V2","title":"Split pipeline.py into packages (no behaviour change)","spec":["B"],"status":"FAIL","evidence_path":null},
 {"id":"F-101","phase":"V2","title":"Real render core: one HTML shot to mp4","spec":["B","E2E-B"],"status":"FAIL","evidence_path":null},
 {"id":"F-102","phase":"V2","title":"Virtual camera: lens, aperture, 12 moves, speed ramp","spec":["B","E2E-B"],"status":"FAIL","evidence_path":null},
 {"id":"F-103","phase":"V2","title":"Real DOM layout gate, both ratios","spec":["B","E2E-A"],"status":"FAIL","evidence_path":null},
 {"id":"F-104","phase":"V2","title":"Shot Plan schema, validator, canonicalizer","spec":["B"],"status":"FAIL","evidence_path":null},
 {"id":"F-105","phase":"V2","title":"Looks kit: 12 looks, portrait and landscape","spec":["B","E2E-B"],"status":"FAIL","evidence_path":null},
 {"id":"F-106","phase":"V2","title":"Genre presets and saved user presets","spec":["B"],"status":"FAIL","evidence_path":null},
 {"id":"F-107","phase":"V2","title":"Hero Frame and storyboard grid (real stills)","spec":["B","E2E-A","E2E-C"],"status":"FAIL","evidence_path":null},
 {"id":"F-108","phase":"V2","title":"Planner: real Gemini client, prompt to Shot Plan, repair loop","spec":["B","E2E-D"],"status":"FAIL","evidence_path":null},
 {"id":"F-109","phase":"V2","title":"Audio sync: per-scene audio, whisper.cpp anchors, mix","spec":["B","E2E-D"],"status":"FAIL","evidence_path":null},
 {"id":"F-110","phase":"V2","title":"Cast and assets: cut-outs, 3 roles, emotion presets, ledger","spec":["B"],"status":"FAIL","evidence_path":null},
 {"id":"F-111","phase":"V2","title":"Chunked render, resume, memory watchdog (real kill test)","spec":["B","E2E-F"],"status":"FAIL","evidence_path":null},
 {"id":"F-112","phase":"V2","title":"Studio UI v2 wizard wired to the real engine","spec":["B","E2E-D"],"status":"FAIL","evidence_path":null},
 {"id":"F-113","phase":"V2","title":"Live preview player and 3D orbit camera","spec":["B"],"status":"FAIL","evidence_path":null},
 {"id":"F-114","phase":"V2","title":"Editor: per-shot edits, hash-cached re-render","spec":["B","E2E-E"],"status":"FAIL","evidence_path":null},
 {"id":"F-115","phase":"V2","title":"Package: languages, ratios, credits, editable bundle","spec":["B","E2E-G"],"status":"FAIL","evidence_path":null},
 {"id":"F-116","phase":"V2","title":"Full acceptance: all 7 scenarios, 10-minute unattended run","spec":["B"],"status":"FAIL","evidence_path":null}
]
```

**Milestones.** M1 (first real video you can watch) = F-100 to F-105, 6 sessions. M2 (prompt to finished video) = F-106 to F-109 and F-112, 5 more. M3 (the full studio) = the rest. Session count is an estimate (ASSUMED); each is capped at 5 files and 250 net lines, so a feature that does not fit gets split by the builder through `STOP_AND_ASK.md`.

## 6. Part D: session prompts

### Common header (paste at the top of every session)

```
You are the builder (Antigravity, Gemini 3.8 Flash). Fresh session. Do ONLY the feature below.
START: python scripts\verify_done.py --baseline. Read CONSTRAINTS.md, the DELTA section of
HANDOFF_PACKET.md, the feature entry, and only the Part B/E2E lines it names from
motion-studio-v2-build-pack.md. Read existing code before writing; reuse it.

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

V2 RULES (added)
6. NO STAND-INS IN THE PRODUCT PATH. No solid-colour video, no placeholder PNG, no zero-byte
   file, no mock_frames, no anullsrc/lavfi colour as output. Mock servers are allowed only in
   tests, never as the default path.
7. A FEATURE ENDS ONLY WHEN `python scripts\e2e_smoke.py --scenario <ID>` PASSES on this machine
   and its real output (command, exit code, seconds, ffprobe lines) is pasted into HANDOFF_PACKET.md.
8. Tests must assert on a produced artifact (a file read back by ffprobe/Pillow, an HTTP
   response, a SQLite row). A test that only calls a function and checks its return is not enough.
```

### F-100: Split pipeline.py (no behaviour change)

```
FEATURE: F-100. Goal: make the code editable inside the 5-file budget.
BUILD: move code out of src\pipeline.py into src\core\ (state.py, governor.py, ledger.py,
parser.py, gateway.py, dashboard.py). Do it in ONE module group this session (budget: 5 files):
move the state machine and rate governor only (functions between "init_database" and
"log_llm_call" in pipeline.py). Keep `from src.core.state import *` style re-exports in
pipeline.py so existing tests and the wiring check keep working. List the remaining groups in
HANDOFF_PACKET.md as follow-up rows (do not do them now).
TESTS: all 108 existing tests pass unchanged; add one test importing each moved function from both paths.
SPIKE (record in SPIKES.md, no code): on this machine run the spike in spike\render.py for 2 s
at 1080x1920 and 1920x1080 and record seconds/frame and peak RAM of the whole process tree.
```

### F-101: Real render core

```
FEATURE: F-101. SPEC: pack section 4 (E2E-B). Reuse spike\scene.html and spike\render.py as the
starting point; do not copy them blindly.
FILES (5): src\engine\render.py, src\engine\shot.html, src\engine\camera.js,
scripts\e2e_smoke.py, tests\regression\test_f101_render.py
BUILD:
1. shot.html exposes window.seek(t, duration) and window.ready (true after fonts and images load).
   Every frame is a pure function of t. No Date.now, no CSS transitions, no unseeded random.
2. render.py: render_shot(plan_shot, ratio, out_path, fps=30): launch chromium-headless-shell via
   Playwright, set viewport, load shot.html with the shot as JSON, wait for window.ready, then for
   each frame call seek(i/fps) and screenshot, pipe to ffmpeg (libx264, yuv420p, crf 18). Return the
   measured seconds/frame and peak process-tree RSS (psutil). Use PNG or JPEG quality 95; record
   which in DECISIONS.md with the reason.
3. scripts\e2e_smoke.py --scenario E2E-B: renders one built-in 2 s shot in both ratios, then checks
   with ffprobe (codec, size, fps, nb_frames within 1 of expected) and with Pillow (frame at 25% and
   75% differ in at least 5% of sampled pixels; each frame has more than 100 unique colours after
   downscaling to 108 px wide). Writes reports\e2e_latest.json (scenario, status, seconds, git HEAD).
4. Call render_shot from src\pipeline.py's render path (replace nothing else yet; the old fake
   /api/render_video is replaced in F-112, but add a TODO row to HANDOFF_PACKET.md).
TESTS: sabotage tests: (a) a shot.html that never changes -> the E2E check must FAIL;
(b) a render with ffmpeg missing -> raises, never writes a file; (c) kill chromium mid-render ->
returns an error, leaves no partial file named *.mp4.
```

### F-102: Virtual camera

```
FEATURE: F-102. FILES: src\engine\camera.js, src\engine\shot.html (small edits),
src\engine\render.py (accepts camera block), tests\regression\test_f102_camera.py,
scripts\e2e_smoke.py (add checks).
BUILD: camera.js implements camera({move, lens_mm, aperture, focus, speed}) -> transform per layer for
time p in [0,1]. perspective_px = viewport_width * lens_mm / 36. blur_px = K * abs(layer_z - focus_z) /
f_number (K recorded in DECISIONS.md). Moves: dolly_in, dolly_out, truck_left, truck_right, pan_left,
pan_right, tilt_up, tilt_down, orbit, crane_up, crane_down, push_through, whip_pan, handheld_drift
(seeded noise). Speed ramps: ease_in_out, linear, slow_then_fast, fast_then_slow, hold_end
(a monotonic time remap).
TESTS (pixel-based, not value-based): for each move, render 1 s at low resolution and measure
the direction of motion of a known bright marker (centroid shift): pan_right shifts content LEFT,
dolly_in grows the marker, tilt_up shifts content DOWN, and so on. A move whose centroid or size does
not change in the expected direction fails the test. Aperture test: a layer far from the focus plane is
blurrier (Laplacian variance lower) at f/1.8 than at f/11.
```

### F-103: Real DOM layout gate

```
FEATURE: F-103. FILES: src\engine\gate.py, src\engine\shot.html (expose window.measure()),
src\engine\render.py (call the gate before encoding), tests\regression\test_f103_gate.py,
scripts\e2e_smoke.py (E2E-A check).
BUILD: gate.py loads the shot in the real browser at each ratio, samples times (start, 25%, 50%,
75%, end), calls window.measure() which returns getBoundingClientRect for every element with
data-slot, and checks: inside the safe area (9:16: 8% side, 12% top, 20% bottom; 16:9: 6% sides,
8% top, 10% bottom), no text overlap between slots, text/background contrast at least 4.5 (WCAG
formula already in pipeline.py), and no text wider than the frame. Failure returns findings with the slot
name, ratio, time, and the measured box; render.py refuses to encode when the gate fails (fail closed).
Reuse audit_dom_layout and compute_wcag_contrast from pipeline.py instead of rewriting them.
TESTS: use spike\scene.html with its 120 px headline: the gate must FAIL it in 9:16 (the headline is
clipped by the frame edge; this is a known real case) and pass after the font size is reduced.
Sabotage: a slot positioned off-screen, and white text on a white background, must both fail.
```

### F-104 to F-116: use this template (fill in from Part C and section 1)

```
[COMMON HEADER]
FEATURE: F-1NN <title>. Read: pack section 1 (the row for this feature), section 4 (its E2E
scenario), and the real files this feature touches. Write a plan of at most 10 lines first.
BUILD: <the 3-6 concrete behaviours from the table below>
TESTS FIRST: assert on produced artifacts only. Add a sabotage test that makes the feature fail
the way a fake would pass (flat video, identical stills, mock server reply, empty asset).
FINISH: python scripts\e2e_smoke.py --scenario <ID>; python scripts\verify_done.py --feature F-1NN;
update the DELTA section of HANDOFF_PACKET.md only.
```

| Feature | Behaviours to build |
|---|---|
| F-104 | JSON Schema for the Shot Plan; whitelist of looks, moves, easings, fonts; per-slot `max_words`; canonicalizer (NFC, trims, defaults); validator returns findings with paths; round-trips the existing script parser output into shots. |
| F-105 | 12 looks (title slam, kinetic type, parallax cards, device mockup, chart reveal, list reveal, split compare, quote, stat counter, logo outro, photo cutout, map-style route), each with `data-slot`s and separate portrait and landscape layouts, each passing the F-103 gate in both ratios. |
| F-106 | Genre presets as data (explainer, product demo, news, kinetic, minimal, hype): cut length range, default easing, camera energy, palette, font pair; saving and loading user presets as JSON via a menu. |
| F-107 | `stills.py`: Hero Frame (a PNG at the shot's best moment, both ratios) and an N-variant contact sheet (2x2, 3x3, 4x4) varying look, palette, camera; stills shown in the approval-1 page. |
| F-108 | Real Gemini HTTP client (key from `.env`, existing rate governor, 503/429 never consume a call), prompt to Shot Plan, schema validation, repair loop with at most 2 calls per scene, low-quota batch mode. Keep the mock server as a test double only. |
| F-109 | Per-scene audio upload, duration via ffprobe, sentence anchors via whisper.cpp (real binary; fall back to even spacing with a visible warning), ducked mix, A/V length check within 0.1 s. |
| F-110 | Upload an image to remove its background (rembg, cached), a small vector library with a license ledger, up to 3 cast roles with emotion presets; the same cast asset renders identically across shots. |
| F-111 | Chunked render (default 900 frames), Chromium respawn per chunk, process-tree memory watchdog, resume from the last finished chunk; test by killing the process tree mid-render. |
| F-112 | Studio UI wizard: Prompt, Camera rig and genre menu, Hero Frame, Storyboard grid, Approve, Render, Edit, Download. Replaces `/api/render_video` and the fake stills with the real engine. Every control is a menu or button. |
| F-113 | In-browser preview using the same shot.html, scrub bar, drag to orbit that stores camera keyframes in the Shot Plan. |
| F-114 | Edit headline, swap asset, change camera preset or duration; cache key = hash(shot JSON, audio hash, engine version); only touched shots are re-rendered. |
| F-115 | Three languages by audio only (on-screen text stays English), both ratios, `credits.md` from the ledger, cue sheets, `editable_project.zip` that reopens in the studio. |
| F-116 | `e2e_smoke.py --all` passes 7 of 7; then one unattended 10-minute project; record seconds/frame and peak RAM; list the SPEC numbers that had to change. |

## 7. Part E: the immutable test you add by hand (Part A step 2)

`tests/immutable/test_no_fake_render.py`

```python
import json, re, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BANNED = [r"anullsrc", r"color=c=", r"mock_frames\s*=\s*True", r"\\x00\"\s*\*\s*64"]

def _src_text():
    return {p: p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "src").rglob("*.py")}

def test_no_stand_in_render_in_src():
    hits = [(str(p.relative_to(ROOT)), pat) for p, t in _src_text().items() for pat in BANNED if re.search(pat, t)]
    assert not hits, f"stand-in render code in product path: {hits}"

def test_e2e_report_is_fresh_and_green():
    rep = ROOT / "reports" / "e2e_latest.json"
    assert rep.exists(), "run python scripts\\e2e_smoke.py --all first"
    data = json.loads(rep.read_text(encoding="utf-8"))
    assert data.get("failed", 1) == 0, data
    newest_src = max(p.stat().st_mtime for p in (ROOT / "src").rglob("*") if p.is_file())
    assert rep.stat().st_mtime >= newest_src, "e2e report is older than the latest src change"
```

Start with only the first test active while F-100 to F-111 are in progress (the e2e report test would fail until the engine exists), and enable the second at F-112. You can enable it earlier if you prefer; the cost is that every session must re-run the smoke test, which takes minutes.

## 8. Known limits and open points

- Output is motion graphics and 2.5D parallax, not photoreal video (section 1).
- Render speed on your laptop is **unmeasured**. F-100 records it first; if it is above about 4 s/frame, chunk size and resolution defaults change before anything else is built.
- The Gemini model name, quota and daily limit are unverified; F-108 records what the real API returns.
- Fonts for Hindi and Tamil are not needed (on-screen text is English), but the looks must still be rendered with fonts that exist on Windows or are bundled; record the font licenses in the ledger.
- The Shot Plan, looks and camera formulas are my design. The constants (`K` for blur, the safe-area percentages, the 12 moves) are starting values to tune by looking at real frames.
- GSAP and Three.js are not required by this plan (the spike used neither). Adding either is a dependency and needs your decision and a license check.