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

from src.engine.generative_render import GENERATIVE_HOST_HTML, audit_and_capture_keyframes
from src.engine.generative_schema import (
    GenerativeShotCode,
    GenerativeStoryboard,
    validate_generative_storyboard,
)
from src.engine.schema import ALLOWED_MOVES, ALLOWED_SPEED_RAMPS
from src.planner.agent import DEFAULT_GEMINI_MODEL, PlannerSettings

CREATIVE_TECHNOLOGIST_PROMPT = f"""
You are an elite Motion Graphics Creative Technologist and Film Director (like Claude Opus 5.5 +
Higgsfield Cinema Studio). Given ANY user prompt, script, or style reference, you design a
multi-shot video and WRITE THE ACTUAL HTML5, CSS3, INLINE SVG, AND CANVAS 2D ANIMATION CODE
to render every frame deterministically.

NEVER rely on plain text boxes on a solid background. Craft rich, bespoke visual worlds:
- Multi-layered parallax backgrounds, custom SVG illustrations, glowing vector paths, animated data
  charts, isometric UI mockups, kinetic typography reveals, particle fields, or editorial split-screens.
- Responsive layout: use vw, vh, vmin, clamp(), flexbox, and CSS grid so the scene looks balanced in
  both 9:16 portrait (1080x1920) and 16:9 landscape (1920x1080). Keep key text inside the central
  safe zone (8% side margins, 12% top, 20% bottom).
- Choose Higgsfield camera rig settings per shot:
  * lens_mm (14 to 135; 24mm wide dynamic, 50mm-85mm cinematic tight)
  * aperture (1.4 shallow depth-of-field blur to 11.0 crisp)
  * move from {list(ALLOWED_MOVES)}
  * speed from {list(ALLOWED_SPEED_RAMPS)}

STRICT DETERMINISM & SECURITY RULES FOR CODE:
1. All visual state MUST be computed purely from (t, duration, progress, rng, isPortrait) inside
   `seek_js_body`.
2. NEVER use Date.now(), new Date(), performance.now(), Math.random(), requestAnimationFrame(),
   setInterval(), fetch(), XMLHttpRequest, eval(), or external http(s) URLs.
3. For procedural particles or starfields, initialize arrays deterministically or sample `rng()`.
4. Ensure high contrast, crisp typography, and continuous visual motion across progress 0.0 -> 1.0.
""".strip()


class VisionCritiqueVerdict(BaseModel):
    passed: bool
    score_1_to_10: int = Field(ge=1, le=10)
    critique_findings: list[str] = Field(default_factory=list)


class UniversalVideoCoderAgent:
    """AI Agent that writes custom HTML/CSS/SVG/Canvas code for any visual style and self-heals."""

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

    def _generate_json(
        self,
        contents: Any,
        schema: type[BaseModel],
        system_instruction: str,
        use_high_thinking: bool = True,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                cfg_kwargs: dict[str, Any] = {
                    "system_instruction": system_instruction,
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                    "temperature": 0.35,
                }
                if use_high_thinking:
                    cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="HIGH")

                resp = self.client.models.generate_content(
                    model=self.settings.gemini_model or DEFAULT_GEMINI_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(**cfg_kwargs),
                )
                if self.rate_acquire is not None:
                    self.rate_acquire()

                raw = (resp.text or "").strip()
                if not raw:
                    raise ValueError("Model returned an empty response.")
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

    def critique_keyframes_with_vision(
        self,
        shot: GenerativeShotCode,
        ratio: str,
        keyframe_pngs: list[bytes],
    ) -> VisionCritiqueVerdict:
        """Send actual rendered PNG frames [10%, 50%, 90%] to Gemini Vision to audit aesthetics."""
        prompt = (
            f"Inspect these 3 rendered frames (10%, 50%, 90% timestamps) for shot '{shot.title}' "
            f"({ratio}). Style goal: '{shot.visual_direction}'.\n"
            "Check for: (1) text clipping or overlap, (2) unreadable low contrast, "
            "(3) broken/empty canvas or missing graphics, (4) visible animation progression across "
            "the 3 frames. Set passed=true only if it looks like broadcast-grade motion graphics."
        )
        parts: list[Any] = [prompt]
        for png in keyframe_pngs:
            parts.append(types.Part.from_bytes(data=png, mime_type="image/png"))

        raw = self._generate_json(
            contents=parts,
            schema=VisionCritiqueVerdict,
            system_instruction="You are a strict Hollywood & Motion-Design Visual Quality Critic.",
            use_high_thinking=False,
        )
        return VisionCritiqueVerdict.model_validate(raw)

    def create_coded_video_plan(
        self,
        prompt: str,
        style_brief: str = "Cinematic bespoke motion graphics",
        ratios: list[Literal["9:16", "16:9"]] | None = None,
        shot_count: int = 3,
        enable_visual_critic: bool = True,
        host_html: Path = GENERATIVE_HOST_HTML,
    ) -> tuple[GenerativeStoryboard, int]:
        """
        Generate a complete multi-shot GenerativeStoryboard where every shot has custom AI-authored
        HTML/CSS/SVG/Canvas code, verified in headless Chromium before returning.
        """
        target_ratios: list[Literal["9:16", "16:9"]] = ratios or ["16:9"]
        user_prompt = (
            f"Create a {shot_count}-shot video project.\n"
            f"Target ratios: {json.dumps(target_ratios)}\n"
            f"Visual style direction: {style_brief}\n"
            f"Script / Concept:\n{prompt.strip()}"
        )

        candidate_raw = self._generate_json(
            contents=user_prompt,
            schema=GenerativeStoryboard,
            system_instruction=CREATIVE_TECHNOLOGIST_PROMPT,
            use_high_thinking=True,
        )

        repairs_used = 0
        while True:
            board, schema_findings = validate_generative_storyboard(candidate_raw)
            all_findings: list[dict[str, str]] = list(schema_findings)

            if board is not None:
                for s_idx, shot in enumerate(board.shots):
                    for ratio in board.ratios:
                        dom_findings, png_frames = audit_and_capture_keyframes(
                            shot, ratio=ratio, host_html=host_html
                        )
                        for df in dom_findings:
                            all_findings.append(
                                {"path": f"shots.{s_idx}.{ratio}", "message": df}
                            )

                        if not dom_findings and enable_visual_critic and png_frames:
                            verdict = self.critique_keyframes_with_vision(shot, ratio, png_frames)
                            if not verdict.passed:
                                for cf in verdict.critique_findings:
                                    all_findings.append(
                                        {
                                            "path": f"shots.{s_idx}.{ratio}.vision",
                                            "message": f"VisualCritic ({verdict.score_1_to_10}/10): {cf}",
                                        }
                                    )

            if board is not None and not all_findings:
                return board, repairs_used

            if repairs_used >= self.settings.max_repair_attempts:
                raise RuntimeError(
                    f"Generative storyboard failed quality verification after {repairs_used} repairs: {all_findings}"
                )

            repairs_used += 1
            repair_prompt = (
                "Your generated scene code had the following layout, runtime, or visual quality issues. "
                "Rewrite the offending HTML/CSS/JS code so every frame renders cleanly with zero clipping "
                "and strong visual motion.\n\n"
                f"ISSUES:\n{json.dumps(all_findings, indent=2)}\n\n"
                f"CURRENT_STORYBOARD_JSON:\n{json.dumps(candidate_raw, indent=2)}"
            )
            candidate_raw = self._generate_json(
                contents=repair_prompt,
                schema=GenerativeStoryboard,
                system_instruction=CREATIVE_TECHNOLOGIST_PROMPT,
                use_high_thinking=True,
            )
