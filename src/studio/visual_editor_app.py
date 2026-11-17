from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from src.engine.parametric_render import PARAMETRIC_HOST_HTML, render_parametric_project
from src.engine.parametric_schema import (
    ParametricShot,
    ParametricVideoProject,
    safe_resolve_path,
)
from src.planner.parametric_coder import ParametricDirectorAgent

ROOT_DIR = Path(__file__).resolve().parents[2]
ENGINE_DIR = ROOT_DIR / "src" / "engine"
OUTPUT_DIR = ROOT_DIR / "reports" / "visual_studio_renders"

app = FastAPI(title="Motion Studio v2 — Visual AI Video Platform")


class CreateProjectRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=3000)
    style_prompt: str = Field(default="Cyberpunk neon HUD telemetry with glowing vector rings", max_length=600)
    ratio: Literal["9:16", "16:9"] = "16:9"
    shot_count: int = Field(default=3, ge=1, le=8)
    enable_vision_critic: bool = True


class RefineShotRequest(BaseModel):
    shot: dict
    edit_instruction: str = Field(min_length=3, max_length=500)
    ratio: Literal["9:16", "16:9"] = "16:9"


class ExportProjectRequest(BaseModel):
    project: dict
    ratio: Literal["9:16", "16:9"] = "16:9"
    fps: int = Field(default=30, ge=15, le=60)


_STUDIO_WORKSTATION_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Motion Studio v2 — Visual AI Video Platform</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #060911; color: #f1f5f9; font-family: "Segoe UI", system-ui, sans-serif;
      display: grid; grid-template-columns: 330px 1fr 340px; height: 100vh; overflow: hidden;
    }
    .panel {
      background: #0c1220; border-right: 1px solid #1e293b; padding: 16px;
      display: flex; flex-direction: column; gap: 12px; overflow-y: auto;
    }
    .panel.right { border-right: none; border-left: 1px solid #1e293b; }
    h1 { font-size: 15px; font-weight: 800; color: #38bdf8; letter-spacing: 0.05em; }
    h2 { font-size: 12px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; }
    label { display: block; font-size: 11px; font-weight: 600; color: #94a3b8; margin-bottom: 4px; }
    textarea, input[type="text"], input[type="number"], select {
      width: 100%; background: #131c31; border: 1px solid #27354f; color: #f8fafc;
      border-radius: 7px; padding: 8px 10px; font-size: 12px;
    }
    textarea { min-height: 74px; resize: vertical; }
    button {
      background: linear-gradient(135deg, #0284c7, #4f46e5); color: #fff; border: none;
      border-radius: 7px; padding: 10px 12px; font-weight: 700; font-size: 12px; cursor: pointer;
    }
    button.secondary { background: #1e293b; border: 1px solid #334155; }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .shot-pill {
      padding: 9px 10px; border-radius: 7px; background: #131c31; border: 1px solid #1e293b;
      cursor: pointer; font-size: 12px; display: flex; justify-content: space-between; align-items: center;
    }
    .shot-pill.active { border-color: #38bdf8; background: #16243d; }
    .stage-wrap {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      padding: 16px; gap: 12px; background: #04060c; position: relative;
    }
    .viewport-frame {
      position: relative; background: #000; border: 1px solid #1e293b; border-radius: 10px;
      overflow: hidden; box-shadow: 0 24px 60px rgba(0, 0, 0, 0.75);
      width: min(100%, 860px); aspect-ratio: 16 / 9;
    }
    .viewport-frame.portrait {
      width: auto; height: min(72vh, 720px); aspect-ratio: 9 / 16;
    }
    iframe#stage-frame { width: 100%; height: 100%; border: none; display: block; }
    .transport {
      width: min(100%, 860px); background: #0c1220; border: 1px solid #1e293b;
      border-radius: 9px; padding: 10px 14px; display: flex; align-items: center; gap: 12px;
    }
    .transport input[type="range"] { flex: 1; accent-color: #38bdf8; }
    .group-card {
      background: #11192c; border: 1px solid #1e293b; border-radius: 8px; padding: 10px;
      display: flex; flex-direction: column; gap: 9px;
    }
    .group-card.selected { border-color: #38bdf8; box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.35); }
    .ctrl-row { display: flex; flex-direction: column; gap: 3px; }
    .ctrl-inline { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    input[type="color"] { width: 42px; height: 28px; border: none; background: transparent; cursor: pointer; }
    .hint { font-size: 11px; color: #64748b; }
    .status-bar { font-size: 11px; color: #34d399; min-height: 16px; }
  </style>
</head>
<body>
  <!-- LEFT: AI Director & Shot Timeline -->
  <div class="panel">
    <h1>MOTION STUDIO v2</h1>
    <p class="hint">AI writes custom graphics code; you edit every visual layer directly without touching code.</p>
    <div>
      <label>Visual Style (Any Aesthetic)</label>
      <textarea id="style-input" placeholder="e.g. Apple 3D glassmorphic product showcase, or Cyberpunk neon HUD radar..."></textarea>
    </div>
    <div>
      <label>Script / Story Concept</label>
      <textarea id="prompt-input" placeholder="Describe your video scenes, stats, and story beats..."></textarea>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
      <div>
        <label>Format</label>
        <select id="ratio-select" onchange="updateViewportAspect()">
          <option value="16:9">16:9 Widescreen</option>
          <option value="9:16">9:16 Portrait</option>
        </select>
      </div>
      <div>
        <label>Shots</label>
        <input id="shot-count" type="number" min="1" max="8" value="3" />
      </div>
    </div>
    <button id="btn-generate" onclick="generateProject()">Generate Custom Video</button>
    <div id="status-bar" class="status-bar">Ready.</div>

    <hr style="border-color:#1e293b;" />
    <h2>Shots</h2>
    <div id="shot-list" style="display:flex;flex-direction:column;gap:6px;"></div>

    <hr style="border-color:#1e293b;" />
    <h2>AI Graphic Co-Pilot Tweak</h2>
    <input id="tweak-input" type="text" placeholder="e.g. Make the ring gold and spin faster..." />
    <button id="btn-tweak" class="secondary" onclick="refineActiveShot()" disabled>Apply AI Visual Tweak</button>
    <button id="btn-export" onclick="exportMasterVideo()" disabled>Render & Download MP4</button>
    <a id="download-link" style="display:none;color:#38bdf8;font-size:12px;font-weight:700;" target="_blank">Open Rendered MP4</a>
  </div>

  <!-- CENTER: Interactive Live Video Stage -->
  <div class="stage-wrap">
    <div id="viewport-frame" class="viewport-frame">
      <iframe id="stage-frame" src="/engine/parametric_host.html"></iframe>
    </div>
    <div class="transport">
      <button id="btn-play" class="secondary" style="padding:6px 12px;" onclick="togglePlay()">Play</button>
      <input id="scrubber" type="range" min="0" max="3" step="0.01" value="0" oninput="onScrub(this.value)" />
      <span id="time-readout" style="font-size:12px;font-variant-numeric:tabular-nums;">0.00s / 3.00s</span>
    </div>
    <p class="hint">Tip: Click any graphic element directly on the video canvas to select it and drag to reposition.</p>
  </div>

  <!-- RIGHT: No-Code Graphic & Camera Rig Inspector -->
  <div class="panel right">
    <h2>Graphic Element Inspector</h2>
    <div id="inspector-controls" style="display:flex;flex-direction:column;gap:10px;">
      <p class="hint">Generate a video to inspect and edit its graphic layers visually.</p>
    </div>

    <hr style="border-color:#1e293b;" />
    <h2>Higgsfield Camera Rig</h2>
    <div class="group-card">
      <div class="ctrl-row">
        <label>Camera Move</label>
        <select id="cam-move" onchange="onCameraChange()">
          <option value="dolly_in">Dolly In</option>
          <option value="dolly_out">Dolly Out</option>
          <option value="orbit">3D Orbit</option>
          <option value="pan_right">Pan Right</option>
          <option value="pan_left">Pan Left</option>
          <option value="tilt_up">Tilt Up</option>
          <option value="crane_up">Crane Up</option>
          <option value="push_through">Push Through</option>
          <option value="whip_pan">Whip Pan</option>
          <option value="handheld_drift">Handheld Drift</option>
        </select>
      </div>
      <div class="ctrl-row">
        <div class="ctrl-inline"><label>Focal Length (mm)</label><span id="lbl-lens" class="hint">35mm</span></div>
        <input id="cam-lens" type="range" min="14" max="135" step="1" value="35" oninput="onCameraChange()" />
      </div>
      <div class="ctrl-row">
        <div class="ctrl-inline"><label>Aperture Depth Blur (f/)</label><span id="lbl-aper" class="hint">f/2.8</span></div>
        <input id="cam-aper" type="range" min="1.4" max="11" step="0.2" value="2.8" oninput="onCameraChange()" />
      </div>
      <div class="ctrl-row">
        <label>Speed Ramp</label>
        <select id="cam-speed" onchange="onCameraChange()">
          <option value="ease_in_out">Ease In-Out</option>
          <option value="linear">Linear</option>
          <option value="slow_then_fast">Slow -> Fast Ramp</option>
          <option value="fast_then_slow">Fast -> Slow Ramp</option>
          <option value="hold_end">Hero Hold End</option>
        </select>
      </div>
    </div>
  </div>

  <script>
    let PROJECT = null;
    let ACTIVE_IDX = 0;
    let SELECTED_NODE = null;
    let PLAYING = false;
    let RAF_ID = null;
    let LAST_TICK = 0;

    function activeShot() {
      return PROJECT && PROJECT.shots ? PROJECT.shots[ACTIVE_IDX] : null;
    }

    function resolvedProps(shot) {
      const merged = {};
      for (const c of shot.controls || []) {
        merged[c.id] = typeof c.default_value === "object" && c.default_value !== null
          ? Object.assign({}, c.default_value)
          : c.default_value;
      }
      for (const [k, v] of Object.entries(shot.user_overrides || {})) {
        if (k in merged) merged[k] = v;
      }
      return merged;
    }

    function updateViewportAspect() {
      const ratio = document.getElementById("ratio-select").value;
      document.getElementById("viewport-frame").classList.toggle("portrait", ratio === "9:16");
      mountActiveShot();
    }

    async function mountActiveShot() {
      const shot = activeShot();
      if (!shot) return;
      const frame = document.getElementById("stage-frame");
      const win = frame.contentWindow;
      if (!win || typeof win.mountParametricShot !== "function") return;

      const props = resolvedProps(shot);
      await win.mountParametricShot(shot, props);
      win.setInteractiveMode(true);
      if (SELECTED_NODE) win.selectNode(SELECTED_NODE);

      const scrubber = document.getElementById("scrubber");
      scrubber.max = String(shot.duration);
      scrubber.value = "0";
      document.getElementById("time-readout").textContent = `0.00s / ${shot.duration.toFixed(2)}s`;

      // Sync camera controls
      document.getElementById("cam-move").value = shot.camera.move || "dolly_in";
      document.getElementById("cam-lens").value = String(shot.camera.lens_mm || 35);
      document.getElementById("lbl-lens").textContent = `${shot.camera.lens_mm || 35}mm`;
      document.getElementById("cam-aper").value = String(shot.camera.aperture || 2.8);
      document.getElementById("lbl-aper").textContent = `f/${shot.camera.aperture || 2.8}`;
      document.getElementById("cam-speed").value = shot.camera.speed || "ease_in_out";

      renderShotList();
      renderInspector();
    }

    function renderShotList() {
      const list = document.getElementById("shot-list");
      list.innerHTML = "";
      if (!PROJECT) return;
      PROJECT.shots.forEach((s, idx) => {
        const div = document.createElement("div");
        div.className = "shot-pill" + (idx === ACTIVE_IDX ? " active" : "");
        div.innerHTML = `<span><strong>${s.id}</strong> ${s.title}</span><span class="hint">${s.duration}s</span>`;
        div.onclick = () => { ACTIVE_IDX = idx; SELECTED_NODE = null; mountActiveShot(); };
        list.appendChild(div);
      });
    }

    function renderInspector() {
      const container = document.getElementById("inspector-controls");
      container.innerHTML = "";
      const shot = activeShot();
      if (!shot) return;

      const props = resolvedProps(shot);
      const groups = new Map();
      for (const ctrl of shot.controls || []) {
        const key = `${ctrl.group}::${ctrl.node_id}`;
        if (!groups.has(key)) groups.set(key, { group: ctrl.group, nodeId: ctrl.node_id, items: [] });
        groups.get(key).items.push(ctrl);
      }

      for (const grp of groups.values()) {
        const card = document.createElement("div");
        card.className = "group-card" + (grp.nodeId === SELECTED_NODE ? " selected" : "");
        card.onclick = () => {
          SELECTED_NODE = grp.nodeId;
          const win = document.getElementById("stage-frame").contentWindow;
          if (win && win.selectNode) win.selectNode(SELECTED_NODE);
          renderInspector();
        };

        const header = document.createElement("div");
        header.className = "ctrl-inline";
        header.innerHTML = `<strong style="font-size:12px;color:#e2e8f0;">${grp.group}</strong><span class="hint">#${grp.nodeId}</span>`;
        card.appendChild(header);

        for (const c of grp.items) {
          const row = document.createElement("div");
          row.className = "ctrl-row";
          const curVal = props[c.id];

          if (c.kind === "text") {
            row.innerHTML = `<label>${c.label}</label>`;
            const inp = document.createElement("input");
            inp.type = "text";
            inp.value = String(curVal ?? "");
            inp.oninput = () => applyControlEdit(c.id, inp.value);
            row.appendChild(inp);
          } else if (c.kind === "color") {
            const inline = document.createElement("div");
            inline.className = "ctrl-inline";
            inline.innerHTML = `<label style="margin:0;">${c.label}</label>`;
            const inp = document.createElement("input");
            inp.type = "color";
            inp.value = String(curVal || "#38bdf8");
            inp.oninput = () => applyControlEdit(c.id, inp.value);
            inline.appendChild(inp);
            row.appendChild(inline);
          } else if (c.kind === "number") {
            const valLabel = document.createElement("span");
            valLabel.className = "hint";
            valLabel.textContent = String(curVal);
            const top = document.createElement("div");
            top.className = "ctrl-inline";
            top.innerHTML = `<label style="margin:0;">${c.label}</label>`;
            top.appendChild(valLabel);
            const slider = document.createElement("input");
            slider.type = "range";
            slider.min = String(c.min_val ?? 0);
            slider.max = String(c.max_val ?? 100);
            slider.step = String(c.step ?? 1);
            slider.value = String(curVal);
            slider.oninput = () => {
              const num = Number(slider.value);
              valLabel.textContent = String(num);
              applyControlEdit(c.id, num);
            };
            row.appendChild(top);
            row.appendChild(slider);
          } else if (c.kind === "xy") {
            row.innerHTML = `<label>${c.label} (X / Y Offset)</label>`;
            const pair = document.createElement("div");
            pair.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:6px;";
            const ix = document.createElement("input");
            ix.type = "number";
            ix.step = "0.5";
            ix.value = String(curVal.x ?? 0);
            const iy = document.createElement("input");
            iy.type = "number";
            iy.step = "0.5";
            iy.value = String(curVal.y ?? 0);
            ix.oninput = () => applyControlEdit(c.id, { x: Number(ix.value), y: Number(iy.value) });
            iy.oninput = () => applyControlEdit(c.id, { x: Number(ix.value), y: Number(iy.value) });
            pair.appendChild(ix);
            pair.appendChild(iy);
            row.appendChild(pair);
          } else if (c.kind === "select") {
            row.innerHTML = `<label>${c.label}</label>`;
            const sel = document.createElement("select");
            for (const opt of c.options || []) {
              const o = document.createElement("option");
              o.value = opt;
              o.textContent = opt;
              if (opt === curVal) o.selected = true;
              sel.appendChild(o);
            }
            sel.onchange = () => applyControlEdit(c.id, sel.value);
            row.appendChild(sel);
          } else if (c.kind === "toggle") {
            const inline = document.createElement("div");
            inline.className = "ctrl-inline";
            inline.innerHTML = `<label style="margin:0;">${c.label}</label>`;
            const chk = document.createElement("input");
            chk.type = "checkbox";
            chk.checked = Boolean(curVal);
            chk.onchange = () => applyControlEdit(c.id, chk.checked);
            inline.appendChild(chk);
            row.appendChild(inline);
          }
          card.appendChild(row);
        }
        container.appendChild(card);
      }
    }

    function applyControlEdit(controlId, value) {
      const shot = activeShot();
      if (!shot) return;
      shot.user_overrides = shot.user_overrides || {};
      shot.user_overrides[controlId] = value;
      const win = document.getElementById("stage-frame").contentWindow;
      if (win && win.updateProps) win.updateProps({ [controlId]: value });
    }

    function onCameraChange() {
      const shot = activeShot();
      if (!shot) return;
      const lens = Number(document.getElementById("cam-lens").value);
      const aper = Number(document.getElementById("cam-aper").value);
      document.getElementById("lbl-lens").textContent = `${lens}mm`;
      document.getElementById("lbl-aper").textContent = `f/${aper}`;
      shot.camera = {
        move: document.getElementById("cam-move").value,
        lens_mm: lens,
        aperture: aper,
        focus: shot.camera.focus || "fg",
        speed: document.getElementById("cam-speed").value,
      };
      const win = document.getElementById("stage-frame").contentWindow;
      if (win && win.updateCamera) win.updateCamera(shot.camera);
    }

    function onScrub(val) {
      const shot = activeShot();
      if (!shot) return;
      const t = Number(val);
      document.getElementById("time-readout").textContent = `${t.toFixed(2)}s / ${shot.duration.toFixed(2)}s`;
      const win = document.getElementById("stage-frame").contentWindow;
      if (win && win.seek) win.seek(t, shot.duration);
    }

    function togglePlay() {
      PLAYING = !PLAYING;
      document.getElementById("btn-play").textContent = PLAYING ? "Pause" : "Play";
      if (PLAYING) {
        LAST_TICK = performance.now();
        const step = (now) => {
          if (!PLAYING) return;
          const shot = activeShot();
          if (shot) {
            const dt = (now - LAST_TICK) / 1000;
            LAST_TICK = now;
            const scrubber = document.getElementById("scrubber");
            let next = Number(scrubber.value) + dt;
            if (next > shot.duration) next = 0;
            scrubber.value = String(next);
            onScrub(next);
          }
          RAF_ID = requestAnimationFrame(step);
        };
        RAF_ID = requestAnimationFrame(step);
      } else if (RAF_ID) {
        cancelAnimationFrame(RAF_ID);
      }
    }

    // Listen to click-and-drag events from inside the video stage iframe
    window.addEventListener("message", (ev) => {
      const msg = ev.data || {};
      if (msg.type === "NODE_SELECTED") {
        SELECTED_NODE = msg.nodeId || null;
        renderInspector();
      } else if (msg.type === "NODE_DRAGGED" && msg.nodeId) {
        const shot = activeShot();
        if (!shot) return;
        const xyCtrl = (shot.controls || []).find(
          (c) => c.node_id === msg.nodeId && c.kind === "xy"
        );
        if (xyCtrl) {
          const props = resolvedProps(shot);
          const cur = props[xyCtrl.id] || { x: 0, y: 0 };
          const updated = {
            x: Number((cur.x + msg.dxPct).toFixed(2)),
            y: Number((cur.y + msg.dyPct).toFixed(2)),
          };
          applyControlEdit(xyCtrl.id, updated);
          renderInspector();
        }
      }
    });

    async function generateProject() {
      const btn = document.getElementById("btn-generate");
      const status = document.getElementById("status-bar");
      btn.disabled = true;
      status.textContent = "AI Director writing custom animation code & running Vision Critic...";
      try {
        const res = await fetch("/api/v3/create_project", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            style_prompt: document.getElementById("style-input").value || "Cyberpunk neon HUD telemetry",
            prompt: document.getElementById("prompt-input").value || "3-shot AI product launch",
            ratio: document.getElementById("ratio-select").value,
            shot_count: Number(document.getElementById("shot-count").value || 3),
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to generate project");
        PROJECT = data.project;
        ACTIVE_IDX = 0;
        SELECTED_NODE = null;
        document.getElementById("btn-tweak").disabled = false;
        document.getElementById("btn-export").disabled = false;
        status.textContent = `Ready: ${PROJECT.shots.length} custom-coded shots generated.`;
        await mountActiveShot();
      } catch (err) {
        status.textContent = "Error: " + err.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function refineActiveShot() {
      const shot = activeShot();
      const instruction = document.getElementById("tweak-input").value.trim();
      if (!shot || !instruction) return;
      const btn = document.getElementById("btn-tweak");
      const status = document.getElementById("status-bar");
      btn.disabled = true;
      status.textContent = "AI Co-Pilot refining shot graphics...";
      try {
        const res = await fetch("/api/v3/refine_shot", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            shot,
            edit_instruction: instruction,
            ratio: document.getElementById("ratio-select").value,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Refinement failed");
        PROJECT.shots[ACTIVE_IDX] = data.shot;
        document.getElementById("tweak-input").value = "";
        status.textContent = "Shot graphics updated.";
        await mountActiveShot();
      } catch (err) {
        status.textContent = "Error: " + err.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function exportMasterVideo() {
      if (!PROJECT) return;
      const btn = document.getElementById("btn-export");
      const status = document.getElementById("status-bar");
      btn.disabled = true;
      status.textContent = "Encoding H.264 master MP4 with your visual edits...";
      try {
        const res = await fetch("/api/v3/export_mp4", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project: PROJECT,
            ratio: document.getElementById("ratio-select").value,
            fps: 30,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Export failed");
        const link = document.getElementById("download-link");
        link.href = data.video_url;
        link.style.display = "inline-block";
        status.textContent = "MP4 ready!";
      } catch (err) {
        status.textContent = "Export error: " + err.message;
      } finally {
        btn.disabled = false;
      }
    }
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _STUDIO_WORKSTATION_HTML


@app.get("/engine/{asset_name}")
def serve_engine_asset(asset_name: str) -> FileResponse:
    target = safe_resolve_path(ENGINE_DIR, asset_name)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Engine asset not found")
    return FileResponse(path=target)


@app.post("/api/v3/create_project")
def create_project(req: CreateProjectRequest) -> dict:
    try:
        agent = ParametricDirectorAgent()
        project, repairs = agent.build_project(
            prompt=req.prompt,
            style_prompt=req.style_prompt,
            ratios=[req.ratio],
            shot_count=req.shot_count,
            enable_vision_critic=req.enable_vision_critic,
            host_html=PARAMETRIC_HOST_HTML,
        )
        return {"project": project.model_dump(), "repairs_used": repairs}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v3/refine_shot")
def refine_shot(req: RefineShotRequest) -> dict:
    try:
        shot = ParametricShot.model_validate(req.shot)
        agent = ParametricDirectorAgent()
        updated = agent.refine_shot_from_instruction(
            shot=shot,
            edit_instruction=req.edit_instruction,
            ratio=req.ratio,
            host_html=PARAMETRIC_HOST_HTML,
        )
        return {"shot": updated.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v3/export_mp4")
def export_mp4(req: ExportProjectRequest) -> dict:
    try:
        project = ParametricVideoProject.model_validate(req.project)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        master = render_parametric_project(
            project=project,
            ratio=req.ratio,
            out_dir=OUTPUT_DIR,
            fps=req.fps,
            base_dir=ROOT_DIR,
        )
        return {"video_url": f"/videos/{master.name}"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/videos/{filename}")
def serve_video(filename: str) -> FileResponse:
    target = safe_resolve_path(OUTPUT_DIR, filename)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(path=target, media_type="video/mp4")
