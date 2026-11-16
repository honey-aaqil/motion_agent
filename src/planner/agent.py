from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.engine.gate import evaluate_dom_gate
from src.engine.render import DEFAULT_SHOT_HTML
from src.engine.schema import (
    ALLOWED_EMOTIONS,
    ALLOWED_GENRES,
    ALLOWED_LOOKS,
    ALLOWED_MOVES,
    ALLOWED_SPEED_RAMPS,
    SLOT_MAX_WORDS,
    ShotPlan,
    ValidationFinding,
    validate_shot_plan,
)

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"

DIRECTOR_SYSTEM_PROMPT = f"""
You are the AI Director for Motion Studio v2. Convert the user's creative brief or AV script into a
valid JSON ShotPlan.

STRICT RULES:
1. Return ONLY valid JSON matching the ShotPlan schema. Never emit raw HTML or CSS.
2. Select 3 to 6 shots for standard briefs unless specified otherwise.
3. Allowed genres: {list(ALLOWED_GENRES)}.
4. Allowed looks: {list(ALLOWED_LOOKS)}.
5. Allowed camera moves: {list(ALLOWED_MOVES)}.
6. Allowed speed ramps: {list(ALLOWED_SPEED_RAMPS)}.
7. Allowed cast emotions: {list(ALLOWED_EMOTIONS)}.
8. Respect word limits per slot: {json.dumps(SLOT_MAX_WORDS)}.
9. Every shot must include a punchy, readable 'headline' slot. Keep text concise so it stays inside
   both 9:16 portrait and 16:9 landscape safe areas.
""".strip()


class PlannerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default=DEFAULT_GEMINI_MODEL, alias="GEMINI_MODEL")
    max_repair_attempts: int = Field(default=2, ge=0, le=2)


class ShotPlanRepairExhaustedError(RuntimeError):
    def __init__(self, findings: list[dict[str, Any]]) -> None:
        self.findings = findings
        super().__init__(f"ShotPlan failed validation after repair attempts: {findings}")


class MotionDirectorAgent:
    """AI Director Agent that plans, validates, repairs, and prepares ShotPlans."""

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

    def _call_gemini_structured(self, prompt: str) -> dict[str, Any]:
        max_transient_retries = 2
        last_exc: Exception | None = None

        for attempt in range(max_transient_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=DIRECTOR_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=ShotPlan,
                        temperature=0.2,
                    ),
                )
                if self.rate_acquire is not None:
                    self.rate_acquire()

                raw_text = (response.text or "").strip()
                if not raw_text:
                    raise ValueError("Gemini returned an empty response payload.")
                parsed = json.loads(raw_text)
                if not isinstance(parsed, dict):
                    raise ValueError("Gemini response JSON root must be an object.")
                return parsed
            except genai_errors.APIError as exc:
                last_exc = exc
                # Transient 429/503 errors never consume rate-governor quota
                if getattr(exc, "code", None) in (429, 503) and attempt < max_transient_retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise

        assert last_exc is not None
        raise last_exc

    def plan_from_brief(
        self,
        brief: str,
        ratios: list[str] | None = None,
        genre: str = "explainer",
        run_dom_gate: bool = False,
        html_path: Path = DEFAULT_SHOT_HTML,
    ) -> tuple[ShotPlan, int]:
        """Generate a validated ShotPlan from a brief, running up to 2 bounded repair calls."""
        target_ratios = ratios or ["9:16", "16:9"]
        user_prompt = (
            f"Target ratios: {json.dumps(target_ratios)}\n"
            f"Preferred genre: {genre}\n"
            f"Creative brief / AV script:\n{brief.strip()}"
        )

        candidate_raw = self._call_gemini_structured(user_prompt)
        repairs_used = 0

        while True:
            plan, schema_findings = validate_shot_plan(candidate_raw)
            all_findings: list[dict[str, Any]] = [f.model_dump() for f in schema_findings]

            if plan is not None and run_dom_gate:
                for idx, shot in enumerate(plan.shots):
                    dom_issues = evaluate_dom_gate(
                        shot.model_dump(),
                        plan.ratios,
                        html_path=html_path,
                    )
                    for issue in dom_issues:
                        all_findings.append(
                            ValidationFinding(
                                path=f"shots.{idx}.slots.{issue.slot}",
                                message=f"[{issue.ratio} @ {issue.time_s}s] {issue.code}: {issue.detail}",
                            ).model_dump()
                        )

            if plan is not None and not all_findings:
                return plan, repairs_used

            if repairs_used >= self.settings.max_repair_attempts:
                raise ShotPlanRepairExhaustedError(all_findings)

            repairs_used += 1
            repair_prompt = (
                "Fix ONLY the validation/layout findings below in the ShotPlan JSON while preserving "
                "all valid fields.\n\n"
                f"FINDINGS:\n{json.dumps(all_findings, indent=2)}\n\n"
                f"CURRENT_SHOT_PLAN:\n{json.dumps(candidate_raw, indent=2)}"
            )
            candidate_raw = self._call_gemini_structured(repair_prompt)
