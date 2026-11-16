from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.engine.gate import compute_wcag_contrast, evaluate_dom_gate
from src.engine.render import DomGateRejectedError, render_shot
from src.engine.schema import safe_resolve_path, validate_shot_plan
from src.planner.agent import MotionDirectorAgent, PlannerSettings, ShotPlanRepairExhaustedError


class _FakeModels:
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)
        self.calls: list[str] = []

    def generate_content(self, *, model: str, contents: str, config: object) -> SimpleNamespace:
        self.calls.append(contents)
        idx = min(len(self.calls) - 1, len(self._payloads) - 1)
        return SimpleNamespace(text=json.dumps(self._payloads[idx]))


class _FakeGenAIClient:
    def __init__(self, payloads: list[dict]) -> None:
        self.models = _FakeModels(payloads)


def test_planner_repairs_invalid_move_and_overlong_headline() -> None:
    bad_plan = {
        "version": 1,
        "title": "Launch Video",
        "ratios": ["9:16", "16:9"],
        "genre": "explainer",
        "cast": [],
        "shots": [
            {
                "id": "SH01",
                "scene": "S01",
                "duration": 2.5,
                "look": "parallax_cards",
                "camera": {"move": "not_a_real_move", "lens_mm": 35, "aperture": 2.8},
                "slots": {"headline": "One two three four five six seven eight nine ten"},
            }
        ],
    }
    fixed_plan = {
        "version": 1,
        "title": "Launch Video",
        "ratios": ["9:16", "16:9"],
        "genre": "explainer",
        "cast": [],
        "shots": [
            {
                "id": "SH01",
                "scene": "S01",
                "duration": 2.5,
                "look": "parallax_cards",
                "camera": {"move": "dolly_in", "lens_mm": 35, "aperture": 2.8},
                "slots": {"headline": "Ship faster with code"},
            }
        ],
    }

    fake_client = _FakeGenAIClient([bad_plan, fixed_plan])
    agent = MotionDirectorAgent(
        settings=PlannerSettings(GEMINI_API_KEY="test-key", max_repair_attempts=2),
        client=fake_client,
    )

    plan, repairs_used = agent.plan_from_brief("Build a launch teaser")
    assert repairs_used == 1
    assert len(fake_client.models.calls) == 2
    assert plan.shots[0].camera.move == "dolly_in"
    assert plan.shots[0].slots["headline"] == "Ship faster with code"


def test_planner_raises_after_exhausting_repair_budget() -> None:
    always_invalid = {"version": 1, "title": "Broken", "shots": []}
    fake_client = _FakeGenAIClient([always_invalid])
    agent = MotionDirectorAgent(
        settings=PlannerSettings(GEMINI_API_KEY="test-key", max_repair_attempts=2),
        client=fake_client,
    )

    with pytest.raises(ShotPlanRepairExhaustedError):
        agent.plan_from_brief("Broken brief")
    assert len(fake_client.models.calls) == 3  # 1 initial + 2 repair attempts


def test_path_traversal_is_blocked(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Path traversal blocked"):
        safe_resolve_path(tmp_path, "../outside.mp4")


def test_wcag_contrast_catches_white_on_white() -> None:
    assert compute_wcag_contrast("rgb(255, 255, 255)", "rgb(255, 255, 255)") == pytest.approx(1.0)
    assert compute_wcag_contrast("rgb(248, 250, 252)", "rgb(15, 23, 42)") > 14.0


def test_dom_gate_rejects_overflow_and_render_fails_closed(tmp_path: Path) -> None:
    shot, findings = validate_shot_plan(
        {
            "version": 1,
            "title": "Gate Test",
            "ratios": ["9:16"],
            "shots": [
                {
                    "id": "SH01",
                    "scene": "S01",
                    "duration": 1.0,
                    "look": "title_slam",
                    "slots": {"headline": "SUPERCALIFRAGILISTICEXPIALIDOCIOUS_OVERFLOW_WORD"},
                }
            ],
        }
    )
    assert shot is not None and not findings

    gate_issues = evaluate_dom_gate(
        shot.shots[0].model_dump(),
        ["9:16"],
        html_path=Path("src/engine/shot.html"),
    )
    if gate_issues:
        with pytest.raises(DomGateRejectedError):
            render_shot(
                shot.shots[0].model_dump(),
                ratio="9:16",
                out_path=tmp_path / "blocked.mp4",
                base_dir=tmp_path,
            )
