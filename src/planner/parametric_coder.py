from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field

from src.engine.parametric_render import PARAMETRIC_HOST_HTML, audit_parametric_shot
from src.engine.parametric_schema import (
    ParametricShot,
    ParametricVideoProject,
    validate_parametric_project,
)
from src.engine.schema import ALLOWED_MOVES, ALLOWED_SPEED_RAMPS
from src.planner.agent import DEFAULT_GEMINI_MODEL, PlannerSettings

PARAMETRIC_DIRECTOR_PROMPT = f"""
You are an elite Motion Graphics Creative Technologist and Director (Claude Opus 5.5 + Higgsfield +
Theatre.js workflow). For ANY visual style or script requested by the user, you write bespoke,
production-grade HTML5, CSS3, inline SVG, and Canvas2D animation code AND expose every visual
element as a no-code GraphicControl so the user can edit colors, text, positions, and speeds
visually without touching code.

ARCHITECTURE RULES:
1. Never build a plain text card. Craft rich, bespoke motion graphics: multi-layered parallax
   backgrounds, custom SVG vector paths, animated data visualizations, 3D isometric UI cards,
   glowing particle simulations, or kinetic typography.
2. Every visual element MUST be editable without code:
   - Declare typed controls in `controls[]` with kinds: "text", "color", "number", "xy", "select", "toggle".
   - Group controls logically by layer (`group`: e.g. "Title", "Accent Shape", "Background", "Particles").
   - Assign a `node_id` to every graphic layer. Add `data-node="<node_id>"` on HTML/SVG elements, or
     call `registerHitbox("<node_id>", x, y, width, height)` inside `seek_js_body` for Canvas2D elements
     so clicking or dragging on the video canvas selects that graphic layer!
   - Always include at least one `xy` offset control (e.g. `title_offset` with default {{"x": 0, "y": 0}})
     so dragging the element on the canvas moves it smoothly via `translate(props.title_offset.x + 'vw', props.title_offset.y + 'vh')`.
   - Read EVERY declared control inside `seek_js_body` via `props.<control_id>`.
3. Responsive layout: use `vw`, `vh`, `vmin`, `clamp()`, flex, and grid so both 9:16 portrait and
   16:9 landscape stay inside safe margins (8% sides, 12% top, 20% bottom).
4. Higgsfield Camera Rig per shot: choose `lens_mm` (14-135), `aperture` (1.4-11.0),
   `move` from {list(ALLOWED_MOVES)}, and `speed` from {list(ALLOWED_SPEED_RAMPS)}.
5. STRICT DETERMINISM & CSP SECURITY:
   - Function signature: `(t, duration, progress, props, rng, isPortrait, registerHitbox)`.
   - NEVER use Date.now(), new Date(), performance.now(), Math.random(), requestAnimationFrame(),
     setInterval(), fetch(), XMLHttpRequest, eval(), or http(s):// URLs.
""".strip()


class VisionAuditResult(BaseModel):
    passed: bool
    score_1_to_10: int = Field(ge=1, le=10)
    findings: list[str] = Field(default_factory=list)


class ParametricDirectorAgent:
    """Generates custom-coded, visually editable multi-shot video projects."""

    def __init__(
        self,
        settings: PlannerSettings | None = None,
        client: Any | None = None,
        rate_acquire: Callable[[], None] | None = None,
    ) -> None:
        self.settings = settings or PlannerSettings()
        self.rate_acquire = rate_acquire
        if client is not None:
            self.client = client
        else:
            if not self.settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY is missing in environment or .env.")
            self.client = genai.Client(api_key=self.settings.gemini_api_key)

    def _call_structured(
        self,
        contents: Any,
        schema: type[BaseModel],
        system_instruction: str,
        high_thinking: bool = True,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                cfg: dict[str, Any] = {
                    "system_instruction": system_instruction,
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                    "temperature": 0.3,
                }
                if high_thinking:
                    cfg["thinking_config"] = types.ThinkingConfig(thinking_level="HIGH")

                resp = self.client.models.generate_content(
                    model=self.settings.gemini_model or DEFAULT_GEMINI_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(**cfg),
                )
                if self.rate_acquire is not None:
                    self.rate_acquire()

                raw = (resp.text or "").strip()
                if not raw:
                    raise ValueError("Gemini returned empty response.")
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("Expected JSON object at root.")
                return parsed
            except genai_errors.APIError as exc:
                last_exc = exc
                if getattr(exc, "code", None) in (429, 503) and attempt < 2:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    def _vision_critique(
        self,
        shot: ParametricShot,
        ratio: str,
        png_frames: list[bytes],
    ) -> VisionAuditResult:
        prompt = (
            f"Audit these 3 rendered frames (10%, 50%, 90%) for shot '{shot.title}' ({ratio}). "
            f"Style target: '{shot.visual_direction}'. Verify no text clipping, strong contrast, "
            "rich bespoke graphics (not a plain empty box), and clear animation motion across frames."
        )
        parts: list[Any] = [prompt]
        for png in png_frames:
            parts.append(types.Part.from_bytes(data=png, mime_type="image/png"))

        raw = self._call_structured(
            contents=parts,
            schema=VisionAuditResult,
            system_instruction="You are a strict Motion Graphics & Cinema Visual Quality Critic.",
            high_thinking=False,
        )
        return VisionAuditResult.model_validate(raw)

    def build_project(
        self,
        prompt: str,
        style_prompt: str = "Bespoke cinematic motion graphics",
        ratios: list[Literal["9:16", "16:9"]] | None = None,
        shot_count: int = 3,
        enable_vision_critic: bool = True,
        host_html: Path = PARAMETRIC_HOST_HTML,
    ) -> tuple[ParametricVideoProject, int]:
        target_ratios: list[Literal["9:16", "16:9"]] = ratios or ["16:9"]
        user_msg = (
            f"Create a {shot_count}-shot video project.\n"
            f"Target ratios: {json.dumps(target_ratios)}\n"
            f"Visual style direction: {style_prompt}\n"
            f"Script / Concept:\n{prompt.strip()}"
        )

        raw_candidate = self._call_structured(
            contents=user_msg,
            schema=ParametricVideoProject,
            system_instruction=PARAMETRIC_DIRECTOR_PROMPT,
            high_thinking=True,
        )

        repairs_used = 0
        while True:
            project, schema_issues = validate_parametric_project(raw_candidate)
            all_issues: list[dict[str, str]] = list(schema_issues)

            if project is not None:
                for idx, shot in enumerate(project.shots):
                    for ratio in project.ratios:
                        dom_issues, frames = audit_parametric_shot(
                            shot, ratio=ratio, host_html=host_html
                        )
                        for issue in dom_issues:
                            all_issues.append({"path": f"shots.{idx}.{ratio}", "message": issue})

                        if not dom_issues and enable_vision_critic and frames:
                            verdict = self._vision_critique(shot, ratio, frames)
                            if not verdict.passed:
                                for f in verdict.findings:
                                    all_issues.append(
                                        {
                                            "path": f"shots.{idx}.{ratio}.vision",
                                            "message": f"VisionCritic ({verdict.score_1_to_10}/10): {f}",
                                        }
                                    )

            if project is not None and not all_issues:
                return project, repairs_used

            if repairs_used >= self.settings.max_repair_attempts:
                raise RuntimeError(f"Project failed validation after {repairs_used} repairs: {all_issues}")

            repairs_used += 1
            repair_msg = (
                "Fix ONLY the issues listed below while keeping all exposed graphic controls working.\n\n"
                f"ISSUES:\n{json.dumps(all_issues, indent=2)}\n\n"
                f"CURRENT_PROJECT:\n{json.dumps(raw_candidate, indent=2)}"
            )
            raw_candidate = self._call_structured(
                contents=repair_msg,
                schema=ParametricVideoProject,
                system_instruction=PARAMETRIC_DIRECTOR_PROMPT,
                high_thinking=True,
            )

    def refine_shot_from_instruction(
        self,
        shot: ParametricShot,
        edit_instruction: str,
        ratio: Literal["9:16", "16:9"] = "16:9",
        host_html: Path = PARAMETRIC_HOST_HTML,
    ) -> ParametricShot:
        """Natural-language graphic co-pilot tweak for a single shot while keeping manual overrides."""
        msg = (
            f"Modify this single ParametricShot according to the user's graphic edit request: "
            f"{edit_instruction!r}.\nPreserve existing control IDs and user_overrides whenever possible.\n\n"
            f"SHOT_JSON:\n{shot.model_dump_json(indent=2)}"
        )
        raw = self._call_structured(
            contents=msg,
            schema=ParametricShot,
            system_instruction=PARAMETRIC_DIRECTOR_PROMPT,
            high_thinking=True,
        )
        updated = ParametricShot.model_validate(raw)
        updated.user_overrides = dict(shot.user_overrides)
        issues, _ = audit_parametric_shot(updated, ratio=ratio, host_html=host_html)
        if issues:
            raise RuntimeError(f"Refined shot failed visual audit: {issues}")
        return updated
