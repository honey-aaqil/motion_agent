from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from playwright.sync_api import sync_playwright
from pydantic import BaseModel

RATIO_DIMENSIONS: dict[Literal["9:16", "16:9"], tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

SAFE_MARGINS: dict[Literal["9:16", "16:9"], tuple[float, float, float, float]] = {
    # (left_pct, top_pct, right_pct, bottom_pct)
    "9:16": (0.08, 0.12, 0.08, 0.20),
    "16:9": (0.06, 0.08, 0.06, 0.10),
}

_RGB_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")


class GateFinding(BaseModel):
    slot: str
    ratio: str
    time_s: float
    code: str
    detail: str
    box: dict[str, float]


def _parse_rgb(css_color: str) -> tuple[int, int, int]:
    match = _RGB_RE.search(css_color or "")
    if not match:
        return (15, 23, 42)
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for c in rgb:
        s = c / 255.0
        channels.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def compute_wcag_contrast(fg_css: str, bg_css: str) -> float:
    l1 = _relative_luminance(_parse_rgb(fg_css))
    l2 = _relative_luminance(_parse_rgb(bg_css))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _boxes_overlap(a: dict[str, float], b: dict[str, float]) -> bool:
    return not (
        a["right"] <= b["left"] + 1.0
        or b["right"] <= a["left"] + 1.0
        or a["bottom"] <= b["top"] + 1.0
        or b["bottom"] <= a["top"] + 1.0
    )


def evaluate_dom_gate(
    shot: dict,
    ratios: list[Literal["9:16", "16:9"]],
    html_path: Path,
    min_contrast: float = 4.5,
) -> list[GateFinding]:
    """Run real-browser DOM safe-area, overflow, overlap, and contrast checks."""
    findings: list[GateFinding] = []
    duration = float(shot.get("duration", 2.0))
    sample_fracs = (0.0, 0.25, 0.5, 0.75, 1.0)
    scene_uri = html_path.resolve().as_uri()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for ratio in ratios:
                vw, vh = RATIO_DIMENSIONS[ratio]
                left_m, top_m, right_m, bottom_m = SAFE_MARGINS[ratio]
                safe_left = vw * left_m
                safe_top = vh * top_m
                safe_right = vw * (1.0 - right_m)
                safe_bottom = vh * (1.0 - bottom_m)

                context = browser.new_context(viewport={"width": vw, "height": vh})
                page = context.new_page()
                page.goto(scene_uri, wait_until="load")
                page.evaluate("(s) => window.loadShot(s)", shot)
                page.wait_for_function("window.ready === true", timeout=10_000)

                for frac in sample_fracs:
                    t = round(duration * frac, 4)
                    page.evaluate("([ts, dur]) => window.seek(ts, dur)", [t, duration])
                    measured = page.evaluate("() => window.measure()")
                    items = measured.get("items", [])

                    for item in items:
                        box = {
                            "left": float(item["left"]),
                            "top": float(item["top"]),
                            "right": float(item["right"]),
                            "bottom": float(item["bottom"]),
                            "width": float(item["width"]),
                            "height": float(item["height"]),
                        }
                        slot_name = str(item["slot"])

                        if box["left"] < 0 or box["right"] > vw or box["width"] > vw:
                            findings.append(
                                GateFinding(
                                    slot=slot_name,
                                    ratio=ratio,
                                    time_s=t,
                                    code="FRAME_OVERFLOW",
                                    detail=f"Slot '{slot_name}' exceeds viewport width {vw}px.",
                                    box=box,
                                )
                            )

                        if (
                            box["left"] < safe_left
                            or box["top"] < safe_top
                            or box["right"] > safe_right
                            or box["bottom"] > safe_bottom
                        ):
                            findings.append(
                                GateFinding(
                                    slot=slot_name,
                                    ratio=ratio,
                                    time_s=t,
                                    code="SAFE_AREA_VIOLATION",
                                    detail=(
                                        f"Slot '{slot_name}' outside safe area "
                                        f"[{safe_left:.0f}, {safe_top:.0f}, {safe_right:.0f}, {safe_bottom:.0f}]."
                                    ),
                                    box=box,
                                )
                            )

                        contrast = compute_wcag_contrast(
                            str(item.get("color", "")),
                            str(item.get("backgroundColor", "")),
                        )
                        if contrast < min_contrast:
                            findings.append(
                                GateFinding(
                                    slot=slot_name,
                                    ratio=ratio,
                                    time_s=t,
                                    code="LOW_CONTRAST",
                                    detail=f"WCAG contrast {contrast:.2f} < {min_contrast:.2f}.",
                                    box=box,
                                )
                            )

                    for i in range(len(items)):
                        for j in range(i + 1, len(items)):
                            if _boxes_overlap(items[i], items[j]):
                                findings.append(
                                    GateFinding(
                                        slot=f"{items[i]['slot']}+{items[j]['slot']}",
                                        ratio=ratio,
                                        time_s=t,
                                        code="SLOT_OVERLAP",
                                        detail="Rendered text slots overlap in screen space.",
                                        box={
                                            "left": float(items[i]["left"]),
                                            "top": float(items[i]["top"]),
                                            "right": float(items[i]["right"]),
                                            "bottom": float(items[i]["bottom"]),
                                        },
                                    )
                                )
                context.close()
        finally:
            browser.close()

    return findings
