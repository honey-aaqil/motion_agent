from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from src.engine.schema import CameraRig

_BANNED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bDate\.now\s*\("), "Use 't' or 'progress' in seek(), never Date.now()."),
    (re.compile(r"\bnew\s+Date\b"), "Use 't' or 'progress' in seek(), never new Date()."),
    (re.compile(r"\bperformance\.now\s*\("), "Use 't' or 'progress' in seek(), never performance.now()."),
    (re.compile(r"\bMath\.random\s*\("), "Use seeded 'rng()' instead of Math.random()."),
    (re.compile(r"\brequestAnimationFrame\b"), "Never call requestAnimationFrame; seek() drives every frame."),
    (re.compile(r"\bsetInterval\s*\("), "Never call setInterval; seek() drives every frame."),
    (re.compile(r"\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource"), "Network calls are forbidden in scene code."),
    (re.compile(r"https?://", re.IGNORECASE), "External URLs are forbidden; draw all graphics with SVG/Canvas/CSS."),
    (re.compile(r"\beval\s*\(|new\s+Function\b"), "Dynamic eval/Function is forbidden."),
]


def normalize_nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def safe_resolve_path(base_dir: Path, child: str | Path) -> Path:
    root = base_dir.resolve()
    candidate = (root / child).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Path traversal blocked: {child!r} escapes {root}")
    return candidate


class GraphicControl(BaseModel):
    """A single visual property exposed to the user in the no-code Graphic Inspector."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-zA-Z0-9_]{1,40}$")
    node_id: str = Field(
        pattern=r"^[a-zA-Z0-9_-]{1,40}$",
        description="Matches data-node='...' on HTML/SVG elements or registerHitbox('...', ...) in Canvas2D.",
    )
    group: str = Field(default="Layer", min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=48)
    kind: Literal["text", "color", "number", "xy", "select", "toggle"]
    default_value: Any
    min_val: float | None = None
    max_val: float | None = None
    step: float | None = None
    options: list[str] = Field(default_factory=list)

    @field_validator("group", "label")
    @classmethod
    def _clean_labels(cls, v: str) -> str:
        return normalize_nfc(v)

    @model_validator(mode="after")
    def _validate_kind_value(self) -> GraphicControl:
        val = self.default_value
        if self.kind == "text" and not isinstance(val, str):
            raise ValueError(f"Control '{self.id}' (text) requires a string default_value.")
        if self.kind == "color":
            if not isinstance(val, str) or not re.match(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$", val):
                raise ValueError(f"Control '{self.id}' (color) requires hex '#RRGGBB', got {val!r}.")
        if self.kind == "number":
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ValueError(f"Control '{self.id}' (number) requires numeric default_value.")
            if self.min_val is None:
                self.min_val = min(0.0, float(val) * 0.5)
            if self.max_val is None:
                self.max_val = max(100.0, float(val) * 2.0)
            if self.step is None:
                self.step = 0.05 if (self.max_val - self.min_val) <= 5.0 else 1.0
        if self.kind == "xy":
            if (
                not isinstance(val, dict)
                or not isinstance(val.get("x"), (int, float))
                or not isinstance(val.get("y"), (int, float))
            ):
                raise ValueError(f"Control '{self.id}' (xy) requires {{'x': float, 'y': float}}.")
        if self.kind == "toggle" and not isinstance(val, bool):
            raise ValueError(f"Control '{self.id}' (toggle) requires boolean default_value.")
        if self.kind == "select":
            if not self.options or val not in self.options:
                raise ValueError(f"Control '{self.id}' (select) default_value must be in options.")
        return self


class ParametricShot(BaseModel):
    """AI-authored custom visual scene code coupled with no-code visual inspector controls."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    title: str = Field(min_length=1, max_length=100)
    duration: float = Field(default=3.0, ge=1.0, le=12.0)
    visual_direction: str = Field(min_length=5, max_length=600)
    camera: CameraRig = Field(default_factory=CameraRig)
    seed: int = Field(default=2026, ge=0, le=2_147_483_647)

    controls: list[GraphicControl] = Field(min_length=2, max_length=32)
    user_overrides: dict[str, Any] = Field(default_factory=dict)

    html_markup: str = Field(min_length=15, max_length=45_000)
    css_styles: str = Field(min_length=10, max_length=45_000)
    seek_js_body: str = Field(
        min_length=20,
        max_length=45_000,
        description=(
            "JS body executed per frame with args: "
            "(t, duration, progress, props, rng, isPortrait, registerHitbox)."
        ),
    )

    @field_validator("title", "visual_direction")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        return normalize_nfc(v)

    @field_validator("html_markup", "css_styles", "seek_js_body")
    @classmethod
    def _audit_security_and_determinism(cls, code: str) -> str:
        for pattern, msg in _BANNED_PATTERNS:
            if pattern.search(code):
                raise ValueError(f"Code audit failed: {msg}")
        return code

    @model_validator(mode="after")
    def _ensure_controls_used_in_code(self) -> ParametricShot:
        seen_ids: set[str] = set()
        for ctrl in self.controls:
            if ctrl.id in seen_ids:
                raise ValueError(f"Duplicate control id: '{ctrl.id}'")
            seen_ids.add(ctrl.id)
            if ctrl.id not in self.seek_js_body:
                raise ValueError(
                    f"Control '{ctrl.id}' is declared in controls[] but never read via props.{ctrl.id} in seek_js_body."
                )
        return self

    def resolved_props(self) -> dict[str, Any]:
        merged = {ctrl.id: ctrl.default_value for ctrl in self.controls}
        for key, val in self.user_overrides.items():
            if key in merged:
                merged[key] = val
        return merged


class ParametricVideoProject(BaseModel):
    """Complete multi-shot AI-coded video project with visual graphic controls."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[3] = 3
    project_title: str = Field(min_length=1, max_length=120)
    style_prompt: str = Field(min_length=3, max_length=1000)
    ratios: list[Literal["9:16", "16:9"]] = Field(default_factory=lambda: ["16:9"])
    shots: list[ParametricShot] = Field(min_length=1, max_length=12)

    @field_validator("project_title", "style_prompt")
    @classmethod
    def _clean_meta(cls, v: str) -> str:
        return normalize_nfc(v)


def validate_parametric_project(
    payload: dict[str, Any],
) -> tuple[ParametricVideoProject | None, list[dict[str, str]]]:
    try:
        proj = ParametricVideoProject.model_validate(payload)
        return proj, []
    except ValidationError as exc:
        findings = [
            {
                "path": ".".join(str(p) for p in err["loc"]),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return None, findings
