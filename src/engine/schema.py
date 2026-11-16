from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

ALLOWED_RATIOS = ("9:16", "16:9")

ALLOWED_GENRES = (
    "explainer",
    "product_demo",
    "news",
    "kinetic",
    "minimal",
    "hype",
)

ALLOWED_LOOKS = (
    "title_slam",
    "kinetic_type",
    "parallax_cards",
    "device_mockup",
    "chart_reveal",
    "list_reveal",
    "split_compare",
    "quote",
    "stat_counter",
    "logo_outro",
    "photo_cutout",
    "map_route",
)

ALLOWED_MOVES = (
    "dolly_in",
    "dolly_out",
    "truck_left",
    "truck_right",
    "pan_left",
    "pan_right",
    "tilt_up",
    "tilt_down",
    "orbit",
    "crane_up",
    "crane_down",
    "push_through",
    "whip_pan",
    "handheld_drift",
)

ALLOWED_SPEED_RAMPS = (
    "ease_in_out",
    "linear",
    "slow_then_fast",
    "fast_then_slow",
    "hold_end",
)

ALLOWED_TRANSITIONS = (
    "cut",
    "match_cut",
    "whip_pan",
    "push_through",
)

ALLOWED_EMOTIONS = (
    "neutral",
    "confident",
    "curious",
    "urgent",
    "celebratory",
)

SLOT_MAX_WORDS: dict[str, int] = {
    "headline": 8,
    "sub": 18,
    "kicker": 5,
    "stat_value": 4,
    "stat_label": 8,
    "quote_body": 28,
    "quote_author": 6,
    "cta": 5,
}

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_SAFE_ASSET_RE = re.compile(r"^assets/[A-Za-z0-9_./-]+\.(svg|png|webp|jpg|jpeg)$")


def normalize_text(value: str) -> str:
    cleaned = unicodedata.normalize("NFC", value).strip()
    return re.sub(r"\s+", " ", cleaned)


def safe_resolve_path(base_dir: Path, relative_or_child: str | Path) -> Path:
    """Prevent CWE-22 path traversal outside base_dir."""
    root = base_dir.resolve()
    candidate = (root / relative_or_child).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Path traversal blocked: {relative_or_child!r} escapes {root}")
    return candidate


class CameraRig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    move: Literal[
        "dolly_in",
        "dolly_out",
        "truck_left",
        "truck_right",
        "pan_left",
        "pan_right",
        "tilt_up",
        "tilt_down",
        "orbit",
        "crane_up",
        "crane_down",
        "push_through",
        "whip_pan",
        "handheld_drift",
    ] = "dolly_in"
    lens_mm: float = Field(default=35.0, ge=14.0, le=135.0)
    aperture: float = Field(default=2.8, ge=1.2, le=16.0)
    focus: Literal["bg", "mid", "fg"] = "fg"
    speed: Literal[
        "ease_in_out",
        "linear",
        "slow_then_fast",
        "fast_then_slow",
        "hold_end",
    ] = "ease_in_out"


class CastMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    asset: str
    role: Literal["host", "expert", "mascot"] = "host"

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        v = normalize_text(v)
        if not _SAFE_ID_RE.match(v):
            raise ValueError(f"Invalid cast id: {v!r}")
        return v

    @field_validator("asset")
    @classmethod
    def _validate_asset(cls, v: str) -> str:
        v = normalize_text(v)
        if not _SAFE_ASSET_RE.match(v) or ".." in v:
            raise ValueError(f"Asset must be a safe relative path under assets/: {v!r}")
        return v


class ShotSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    scene: str
    duration: float = Field(default=3.0, ge=0.5, le=15.0)
    look: Literal[
        "title_slam",
        "kinetic_type",
        "parallax_cards",
        "device_mockup",
        "chart_reveal",
        "list_reveal",
        "split_compare",
        "quote",
        "stat_counter",
        "logo_outro",
        "photo_cutout",
        "map_route",
    ] = "parallax_cards"
    camera: CameraRig = Field(default_factory=CameraRig)
    slots: dict[str, str] = Field(default_factory=dict)
    cast: list[str] = Field(default_factory=list, max_length=3)
    emotion: Literal["neutral", "confident", "curious", "urgent", "celebratory"] = "confident"
    transition_out: Literal["cut", "match_cut", "whip_pan", "push_through"] = "cut"
    anchors: dict[str, str] = Field(default_factory=dict)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)

    @field_validator("id", "scene")
    @classmethod
    def _validate_identifiers(cls, v: str) -> str:
        v = normalize_text(v)
        if not _SAFE_ID_RE.match(v):
            raise ValueError(f"Invalid identifier: {v!r}")
        return v

    @field_validator("slots")
    @classmethod
    def _validate_slots(cls, slots: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, raw_val in slots.items():
            clean_key = normalize_text(key)
            if not _SAFE_ID_RE.match(clean_key):
                raise ValueError(f"Invalid slot name: {clean_key!r}")
            clean_val = normalize_text(raw_val)
            word_limit = SLOT_MAX_WORDS.get(clean_key, 20)
            words = [w for w in clean_val.split(" ") if w]
            if len(words) > word_limit:
                raise ValueError(
                    f"Slot '{clean_key}' has {len(words)} words (max {word_limit}): {clean_val!r}"
                )
            normalized[clean_key] = clean_val
        if not normalized.get("headline"):
            raise ValueError("Every shot must define a non-empty 'headline' slot.")
        return normalized


class ShotPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=120)
    ratios: list[Literal["9:16", "16:9"]] = Field(default_factory=lambda: ["9:16", "16:9"])
    genre: Literal[
        "explainer",
        "product_demo",
        "news",
        "kinetic",
        "minimal",
        "hype",
    ] = "explainer"
    cast: list[CastMember] = Field(default_factory=list, max_length=3)
    shots: list[ShotSpec] = Field(min_length=1, max_length=24)

    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        return normalize_text(v)

    @field_validator("ratios")
    @classmethod
    def _dedupe_ratios(cls, v: list[Literal["9:16", "16:9"]]) -> list[Literal["9:16", "16:9"]]:
        if not v:
            raise ValueError("At least one target aspect ratio is required.")
        seen: list[Literal["9:16", "16:9"]] = []
        for item in v:
            if item not in seen:
                seen.append(item)
        return seen


class ValidationFinding(BaseModel):
    path: str
    message: str


def validate_shot_plan(payload: dict) -> tuple[ShotPlan | None, list[ValidationFinding]]:
    """Validate and canonicalize a raw Shot Plan dictionary, returning structured findings."""
    try:
        plan = ShotPlan.model_validate(payload)
    except ValidationError as exc:
        findings = [
            ValidationFinding(
                path=".".join(str(part) for part in err["loc"]),
                message=err["msg"],
            )
            for err in exc.errors()
        ]
        return None, findings

    cast_ids = {c.id for c in plan.cast}
    cross_findings: list[ValidationFinding] = []
    for idx, shot in enumerate(plan.shots):
        for cid in shot.cast:
            if cid not in cast_ids:
                cross_findings.append(
                    ValidationFinding(
                        path=f"shots.{idx}.cast",
                        message=f"Unknown cast id '{cid}' not declared in top-level cast list.",
                    )
                )
    if cross_findings:
        return None, cross_findings
    return plan, []
