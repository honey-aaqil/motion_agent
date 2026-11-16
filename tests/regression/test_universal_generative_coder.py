from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.engine.generative_render import audit_and_capture_keyframes, render_generative_shot
from src.engine.generative_schema import GenerativeShotCode, validate_generative_storyboard
from src.planner.agent import PlannerSettings
from src.planner.generative_coder import UniversalVideoCoderAgent


class _SequencedModels:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def generate_content(self, *, model: str, contents: object, config: object) -> SimpleNamespace:
        idx = min(self.call_count, len(self._responses) - 1)
        self.call_count += 1
        return SimpleNamespace(text=json.dumps(self._responses[idx]))


class _FakeClient:
    def __init__(self, responses: list[dict]) -> None:
        self.models = _SequencedModels(responses)


def test_rejects_non_deterministic_or_network_scene_code() -> None:
    _, findings = validate_generative_storyboard(
        {
            "version": 2,
            "project_title": "Unsafe Scene",
            "style_brief": "HUD",
            "ratios": ["16:9"],
            "shots": [
                {
                    "id": "SH01",
                    "title": "Bad Clock",
                    "duration": 2.0,
                    "visual_direction": "HUD ring",
                    "html_markup": "<div id='box'>HUD</div>",
                    "css_styles": "#box { color: cyan; }",
                    "seek_js_body": "document.getElementById('box').style.opacity = Date.now() % 2;",
                }
            ],
        }
    )
    assert findings
    assert "Date.now()" in findings[0]["message"]


def test_ai_coder_repairs_frozen_scene_and_passes_vision_critic() -> None:
    frozen_shot = {
        "version": 2,
        "project_title": "Cyberpunk Telemetry",
        "style_brief": "Glowing cyan SVG radar & kinetic metrics",
        "ratios": ["16:9"],
        "shots": [
            {
                "id": "SH01",
                "title": "Radar Boot",
                "duration": 1.5,
                "visual_direction": "Glowing cyan circular HUD radar expanding on dark grid",
                "camera": {"move": "dolly_in", "lens_mm": 35, "aperture": 2.8, "focus": "fg", "speed": "ease_in_out"},
                "html_markup": "<svg viewBox='0 0 400 400' width='360' height='360'><circle cx='200' cy='200' r='120' stroke='#38bdf8' stroke-width='8' fill='none'/></svg>",
                "css_styles": "#scene-canvas { display:grid; place-items:center; background:#050811; }",
                "seek_js_body": "/* bug: forgot to animate anything */",
            }
        ],
    }

    animated_shot = {
        "version": 2,
        "project_title": "Cyberpunk Telemetry",
        "style_brief": "Glowing cyan SVG radar & kinetic metrics",
        "ratios": ["16:9"],
        "shots": [
            {
                "id": "SH01",
                "title": "Radar Boot",
                "duration": 1.5,
                "visual_direction": "Glowing cyan circular HUD radar expanding on dark grid",
                "camera": {"move": "dolly_in", "lens_mm": 35, "aperture": 2.8, "focus": "fg", "speed": "ease_in_out"},
                "html_markup": (
                    "<div class='hud'>"
                    "<svg viewBox='0 0 400 400' width='380' height='380'>"
                    "<circle id='ring' cx='200' cy='200' r='30' stroke='#38bdf8' stroke-width='10' fill='rgba(56,189,248,0.18)'/>"
                    "<rect id='bar' x='40' y='320' width='40' height='24' fill='#f43f5e'/>"
                    "</svg>"
                    "<div id='lbl'>SYSTEM ONLINE</div>"
                    "</div>"
                ),
                "css_styles": (
                    "#scene-canvas { display:grid; place-items:center; background:radial-gradient(circle,#0f172a,#020617); }"
                    ".hud { display:flex; flex-direction:column; align-items:center; gap:16px; }"
                    "#lbl { font-size:36px; font-weight:800; color:#f8fafc; letter-spacing:0.12em; }"
                ),
                "seek_js_body": (
                    "const ring = document.getElementById('ring');"
                    "const bar = document.getElementById('bar');"
                    "ring.setAttribute('r', String(30 + progress * 140));"
                    "bar.setAttribute('width', String(40 + progress * 280));"
                ),
            }
        ],
    }

    vision_pass = {"passed": True, "score_1_to_10": 9, "critique_findings": []}
    fake_client = _FakeClient([frozen_shot, animated_shot, vision_pass])

    agent = UniversalVideoCoderAgent(
        settings=PlannerSettings(GEMINI_API_KEY="test-key", max_repair_attempts=2),
        client=fake_client,
    )
    board, repairs = agent.create_coded_video_plan(
        prompt="Create a cyberpunk telemetry intro",
        style_brief="Glowing cyan SVG radar",
        ratios=["16:9"],
        shot_count=1,
        enable_visual_critic=True,
    )
    assert repairs == 1
    assert "ring.setAttribute" in board.shots[0].seek_js_body


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required for full MP4 test")
def test_renders_custom_canvas_simulation_to_real_mp4(tmp_path: Path) -> None:
    shot = GenerativeShotCode(
        id="SH_CANVAS",
        title="Orbital Particle Wave",
        duration=1.0,
        visual_direction="Custom HTML5 Canvas2D wave simulation with glowing nodes",
        html_markup="<canvas id='c' width='960' height='540'></canvas>",
        css_styles="#c { width:100vw; height:100vh; display:block; }",
        seek_js_body="""
          const c = document.getElementById('c');
          const ctx = c.getContext('2d');
          ctx.fillStyle = '#060913';
          ctx.fillRect(0, 0, c.width, c.height);
          for (let i = 0; i < 36; i++) {
            const x = 60 + i * 24;
            const y = 270 + Math.sin(i * 0.35 + progress * Math.PI * 2) * 140;
            ctx.fillStyle = i % 2 === 0 ? '#38bdf8' : '#a855f7';
            ctx.beginPath();
            ctx.arc(x, y, 10 + progress * 6, 0, Math.PI * 2);
            ctx.fill();
          }
        """,
    )
    out_mp4 = tmp_path / "canvas_sim.mp4"
    res = render_generative_shot(shot, ratio="16:9", out_path=out_mp4, fps=15, base_dir=tmp_path)
    assert out_mp4.exists()
    assert res.unique_colors_mid >= 15
    assert res.motion_delta_ratio > 0.05

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(out_mp4)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    assert probe.stdout.strip() == "h264"
