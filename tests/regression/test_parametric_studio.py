from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.engine.parametric_render import render_parametric_shot
from src.engine.parametric_schema import ParametricShot, validate_parametric_project


def test_blocks_unwired_controls_and_non_deterministic_code() -> None:
    _, issues = validate_parametric_project(
        {
            "version": 3,
            "project_title": "Audit Test",
            "style_prompt": "Neon HUD",
            "ratios": ["16:9"],
            "shots": [
                {
                    "id": "SH01",
                    "title": "HUD",
                    "duration": 2.0,
                    "visual_direction": "HUD ring",
                    "controls": [
                        {
                            "id": "ring_color",
                            "node_id": "ring",
                            "group": "Ring",
                            "label": "Color",
                            "kind": "color",
                            "default_value": "#38bdf8",
                        },
                        {
                            "id": "unused_slider",
                            "node_id": "ring",
                            "group": "Ring",
                            "label": "Unused",
                            "kind": "number",
                            "default_value": 10,
                        },
                    ],
                    "html_markup": "<canvas id='c' width='640' height='360'></canvas>",
                    "css_styles": "#c { width:100vw; height:100vh; }",
                    "seek_js_body": "const x = props.ring_color;",
                }
            ],
        }
    )
    assert issues
    assert "unused_slider" in issues[0]["message"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required")
def test_renders_parametric_canvas_shot_with_user_graphic_overrides(tmp_path: Path) -> None:
    shot = ParametricShot(
        id="SH_PARAM",
        title="Parametric Neon Orb",
        duration=1.0,
        visual_direction="Glowing vector orb with editable color, radius, title, and XY drag offset",
        controls=[
            {
                "id": "headline_text",
                "node_id": "hero_title",
                "group": "Headline",
                "label": "Title Text",
                "kind": "text",
                "default_value": "AI DIRECTOR",
            },
            {
                "id": "orb_color",
                "node_id": "energy_orb",
                "group": "Energy Orb",
                "label": "Orb Color",
                "kind": "color",
                "default_value": "#38bdf8",
            },
            {
                "id": "orb_radius",
                "node_id": "energy_orb",
                "group": "Energy Orb",
                "label": "Base Radius",
                "kind": "number",
                "default_value": 55,
                "min_val": 20,
                "max_val": 140,
                "step": 1,
            },
            {
                "id": "orb_offset",
                "node_id": "energy_orb",
                "group": "Energy Orb",
                "label": "Position Offset",
                "kind": "xy",
                "default_value": {"x": 0.0, "y": 0.0},
            },
        ],
        user_overrides={
            "headline_text": "VISUAL EDITS",
            "orb_color": "#f43f5e",
            "orb_offset": {"x": 5.0, "y": -3.0},
        },
        html_markup=(
            "<canvas id='c' width='960' height='540'></canvas>"
            "<div id='title' data-node='hero_title'></div>"
        ),
        css_styles=(
            "#c { position:absolute; inset:0; width:100vw; height:100vh; }"
            "#title { position:absolute; left:10vw; bottom:18vh; font-size:42px; font-weight:900; color:#f8fafc; }"
        ),
        seek_js_body="""
          const c = document.getElementById('c');
          const ctx = c.getContext('2d');
          ctx.fillStyle = '#050811';
          ctx.fillRect(0, 0, c.width, c.height);

          const cx = c.width * (0.5 + props.orb_offset.x / 100);
          const cy = c.height * (0.45 + props.orb_offset.y / 100);
          const r = props.orb_radius + progress * 65;

          ctx.fillStyle = props.orb_color;
          ctx.beginPath();
          ctx.arc(cx, cy, r, 0, Math.PI * 2);
          ctx.fill();

          registerHitbox('energy_orb', (cx - r) * (window.innerWidth / c.width), (cy - r) * (window.innerHeight / c.height), (r * 2) * (window.innerWidth / c.width), (r * 2) * (window.innerHeight / c.height));

          const title = document.getElementById('title');
          title.textContent = props.headline_text;
          title.style.opacity = String(0.3 + 0.7 * progress);
        """,
    )

    out_mp4 = tmp_path / "parametric_edited.mp4"
    stats = render_parametric_shot(shot, ratio="16:9", out_path=out_mp4, fps=15, base_dir=tmp_path)
    assert out_mp4.exists()
    assert stats.pixel_delta_ratio > 0.03

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
            str(out_mp4),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    assert probe.stdout.strip() == "h264"
