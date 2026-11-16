from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from src.engine.generative_render import render_storyboard_master
from src.engine.generative_schema import GenerativeStoryboard, safe_resolve_path
from src.planner.generative_coder import UniversalVideoCoderAgent

ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT_DIR / "reports" / "generated_videos"

app = FastAPI(title="Motion Studio v2 — Universal AI Code-to-Video Director")


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=3000)
    style_brief: str = Field(default="Apple Keynote 3D glassmorphic motion graphics", max_length=500)
    ratio: Literal["9:16", "16:9"] = "16:9"
    shot_count: int = Field(default=3, ge=1, le=8)
    enable_visual_critic: bool = True


class RenderRequest(BaseModel):
    storyboard: dict
    ratio: Literal["9:16", "16:9"] = "16:9"
    fps: int = Field(default=30, ge=15, le=60)


_STUDIO_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Motion Studio v2 — Universal Generative Video Director</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #070a12; color: #f1f5f9; font-family: "Segoe UI", system-ui, sans-serif;
      display: grid; grid-template-columns: 420px 1fr; height: 100vh;
    }
    aside {
      background: #0d1322; border-right: 1px solid #1e293b; padding: 22px;
      display: flex; flex-direction: column; gap: 14px; overflow-y: auto;
    }
    h1 { font-size: 18px; font-weight: 800; letter-spacing: 0.02em; color: #38bdf8; }
    label { font-size: 12px; font-weight: 600; color: #94a3b8; text-transform: uppercase; }
    textarea, select, input {
      width: 100%; background: #131c31; border: 1px solid #26344d; color: #f8fafc;
      border-radius: 8px; padding: 10px; font-size: 13px; margin-top: 4px;
    }
    textarea { min-height: 96px; resize: vertical; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    button {
      background: linear-gradient(135deg, #0284c7, #4f46e5); color: #fff; border: none;
      border-radius: 8px; padding: 12px; font-weight: 700; cursor: pointer; font-size: 13px;
    }
    button.secondary { background: #1e293b; border: 1px solid #334155; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    main { padding: 24px; display: flex; flex-direction: column; gap: 16px; overflow-y: auto; }
    .card { background: #0d1322; border: 1px solid #1e293b; border-radius: 12px; padding: 16px; }
    pre {
      background: #050811; padding: 12px; border-radius: 8px; font-size: 12px;
      overflow-x: auto; color: #7dd3fc; max-height: 280px;
    }
    video { width: 100%; max-height: 520px; border-radius: 10px; background: #000; }
    .status { font-size: 13px; color: #34d399; }
  </style>
</head>
<body>
  <aside>
    <h1>MOTION STUDIO v2</h1>
    <p style="font-size:12px;color:#94a3b8;">Universal AI Code-to-Video Engine (Gemini 3.8 Flash + Chromium + FFmpeg)</p>
    <div>
      <label>Visual Style (Any Style)</label>
      <textarea id="style" placeholder="e.g. Cyberpunk HUD telemetry with glowing cyan radar rings, or Swiss kinetic typography..."></textarea>
    </div>
    <div>
      <label>Script / Video Concept</label>
      <textarea id="prompt" placeholder="Describe your scenes, metrics, story beats, or product pitch..."></textarea>
    </div>
    <div class="row">
      <div>
        <label>Aspect Ratio</label>
        <select id="ratio">
          <option value="16:9">16:9 Landscape</option>
          <option value="9:16">9:16 Reels / Shorts</option>
        </select>
      </div>
      <div>
        <label>Shots</label>
        <input id="shots" type="number" min="1" max="8" value="3" />
      </div>
    </div>
    <button id="btn-plan" onclick="generateCode()">1. AI Write Custom Scene Code</button>
    <button id="btn-render" class="secondary" onclick="renderVideo()" disabled>2. Render Real H.264 Video</button>
    <div id="status" class="status">Ready.</div>
  </aside>
  <main>
    <div class="card">
      <h3 style="margin-bottom:10px;">Rendered Master Video</h3>
      <video id="player" controls></video>
    </div>
    <div class="card">
      <h3 style="margin-bottom:10px;">AI-Authored Scene Code (HTML / CSS / SVG / Canvas2D)</h3>
      <pre id="code-view">// Generated shot code will appear here...</pre>
    </div>
  </main>
  <script>
    let CURRENT_BOARD = null;
    async function generateCode() {
      const btn = document.getElementById("btn-plan");
      const status = document.getElementById("status");
      btn.disabled = true;
      status.textContent = "AI Director writing custom HTML/CSS/SVG/Canvas code & running Vision Critic...";
      try {
        const res = await fetch("/api/v2/generate_code", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            style_brief: document.getElementById("style").value || "Cyberpunk HUD data visualization",
            prompt: document.getElementById("prompt").value || "3-shot AI engine launch teaser",
            ratio: document.getElementById("ratio").value,
            shot_count: Number(document.getElementById("shots").value || 3)
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Generation failed");
        CURRENT_BOARD = data.storyboard;
        document.getElementById("code-view").textContent = JSON.stringify(CURRENT_BOARD, null, 2);
        document.getElementById("btn-render").disabled = false;
        status.textContent = `Verified ${CURRENT_BOARD.shots.length} custom-coded shots (repairs used: ${data.repairs_used}).`;
      } catch (e) {
        status.textContent = "Error: " + e.message;
      } finally {
        btn.disabled = false;
      }
    }
    async function renderVideo() {
      if (!CURRENT_BOARD) return;
      const btn = document.getElementById("btn-render");
      const status = document.getElementById("status");
      btn.disabled = true;
      status.textContent = "Rendering frames in Chromium & encoding H.264 MP4 via FFmpeg...";
      try {
        const ratio = document.getElementById("ratio").value;
        const res = await fetch("/api/v2/render_master", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ storyboard: CURRENT_BOARD, ratio, fps: 30 })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Render failed");
        const player = document.getElementById("player");
        player.src = data.video_url + "?t=" + Date.now();
        player.load();
        status.textContent = "Render complete: " + data.video_url;
      } catch (e) {
        status.textContent = "Render error: " + e.message;
      } finally {
        btn.disabled = false;
      }
    }
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def studio_index() -> str:
    return _STUDIO_HTML


@app.post("/api/v2/generate_code")
def api_generate_code(req: GenerateRequest) -> dict:
    try:
        agent = UniversalVideoCoderAgent()
        board, repairs = agent.create_coded_video_plan(
            prompt=req.prompt,
            style_brief=req.style_brief,
            ratios=[req.ratio],
            shot_count=req.shot_count,
            enable_visual_critic=req.enable_visual_critic,
        )
        return {"storyboard": board.model_dump(), "repairs_used": repairs}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v2/render_master")
def api_render_master(req: RenderRequest) -> dict:
    try:
        board = GenerativeStoryboard.model_validate(req.storyboard)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        master_path = render_storyboard_master(
            storyboard=board,
            ratio=req.ratio,
            out_dir=OUTPUT_DIR,
            fps=req.fps,
            base_dir=ROOT_DIR,
        )
        return {"video_url": f"/videos/{master_path.name}"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/videos/{filename}")
def serve_video(filename: str) -> FileResponse:
    target = safe_resolve_path(OUTPUT_DIR, filename)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(path=target, media_type="video/mp4")
