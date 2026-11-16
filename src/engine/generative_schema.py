from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.engine.schema import CameraRig

ALLOWED_STYLE_PRESETS = (
    "custom_freeform",
    "apple_keynote_3d",
    "cyberpunk_hud_telemetry",
    "swiss_editorial_kinetic",
    "isometric_saas_ui",
    "neon_synthwave_grid",
    "documentary_data_viz",
    "bauhaus_geometric",
    "luxury_minimal_serif",
    "manga_comic_impact",
)

# Disallow non-deterministic clocks, external network fetches, or dynamic code execution
_BANNED_CODE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bDate\.now\s*\("), "Use 't' passed to window.seek(t, duration), never Date.now()."),
    (re.compile(r"\bnew\s+Date\b"), "Use 't' passed to window.seek(t, duration), never new Date()."),
    (re.compile(r"\bperformance\.now\s*\("), "Use 't' passed to window.seek(t, duration), never performance.now()."),
    (re.compile(r"\bMath\.random\s*\("), "Use window.rng() seeded PRNG instead of Math.random()."),
    (re.compile(r"\brequestAnimationFrame\b"), "Do not use requestAnimationFrame; drive all motion inside window.seek(t, duration)."),
    (re.compile(r"\bsetInterval\s*\("), "Do not use setInterval; drive all motion inside window.seek(t, duration)."),
    (re.compile(r"\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource"), "External network calls are forbidden inside scene code."),
    (re.compile(r"https?://", re.IGNORECASE), "External URLs are forbidden; generate all visuals with inline SVG, Canvas2D, and CSS."),
    (re.compile(r"\beval\s*\(|new\s+Function\b"), "Dynamic code evaluation is forbidden."),
]


def normalize_nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip()


def safe_resolve_path(base_dir: Path, child: str | Path) -> Path:
    root = base_dir.resolve()
    candidate = (root / child).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Path traversal blocked: {child!r} escapes {root}")
    return candidate


class GenerativeShotCode(BaseModel):
    """AI-authored custom visual scene code driven deterministically by window.seek(t, duration)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    title: str = Field(min_length=1, max_length=100)
    duration: float = Field(default=3.0, ge=1.0, le=12.0)
    visual_direction: str = Field(
        min_length=5,
        max_length=500,
        description="Director notes describing lighting, color palette, typography, and motion choreography.",
    )
    camera: CameraRig = Field(default_factory=CameraRig)
    seed: int = Field(default=1337, ge=0, le=2_147_483_647)

    # Custom code authored by the AI Director for this specific shot
    html_markup: str = Field(
        min_length=20,
        max_length=40_000,
        description="Self-contained HTML/SVG/Canvas markup mounted inside #scene-canvas.",
    )
    css_styles: str = Field(
        min_length=10,
        max_length=40_000,
        description="Scoped CSS styles using responsive vw/vh/vmin units so both 9:16 and 16:9 look great.",
    )
    seek_js_body: str = Field(
        min_length=20,
        max_length=40_000,
        description=(
            "JavaScript function body executed on every frame with parameters (t, duration, progress, rng, isPortrait). "
            "Must deterministically update DOM styles, SVG attributes, or Canvas2D pixels."
        ),
    )

    @field_validator("title", "visual_direction")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        return normalize_nfc(v)

    @field_validator("html_markup", "css_styles", "seek_js_body")
    @classmethod
    def _audit_code_safety(cls, code: str) -> str:
        for pattern, reason in _BANNED_CODE_PATTERNS:
            if pattern.search(code):
                raise ValueError(f"Scene code rejected: {reason}")
        return code


class GenerativeStoryboard(BaseModel):
    """Multi-shot AI-coded video project."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
    project_title: str = Field(min_length=1, max_length=120)
    style_brief: str = Field(min_length=3, max_length=1000)
    ratios: list[Literal["9:16", "16:9"]] = Field(default_factory=lambda: ["16:9"])
    shots: list[GenerativeShotCode] = Field(min_length=1, max_length=12)

    @field_validator("project_title", "style_brief")
    @classmethod
    def _clean_meta(cls, v: str) -> str:
        return normalize_nfc(v)


def validate_generative_storyboard(payload: dict) -> tuple[GenerativeStoryboard | None, list[dict[str, str]]]:
    try:
        board = GenerativeStoryboard.model_validate(payload)
        return board, []
    except ValidationError as exc:
        findings = [
            {
                "path": ".".join(str(p) for p in err["loc"]),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return None, findings
