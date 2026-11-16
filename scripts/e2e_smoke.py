from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageChops

from src.engine.render import render_hero_frame, render_shot
from src.engine.schema import ShotPlan, ShotSpec
from src.planner.agent import MotionDirectorAgent

REPORTS_DIR = ROOT / "reports"
ARTIFACTS_DIR = REPORTS_DIR / "smoke_artifacts"


def _git_head() -> str:
    res = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        shell=False,
    )
    return res.stdout.strip() if res.returncode == 0 else "unknown"


def _unique_colors_downscaled(img: Image.Image) -> int:
    w, h = img.size
    new_h = max(1, int(round(h * (108.0 / w))))
    thumb = img.convert("RGB").resize((108, new_h), Image.Resampling.BILINEAR)
    colors = thumb.getcolors(maxcolors=108 * new_h)
    return len(colors or [])


def _ffprobe_video(mp4_path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,r_frame_rate,nb_frames",
        "-of",
        "json",
        str(mp4_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True, shell=False)
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream found in {mp4_path}")
    return streams[0]


def _extract_frame(mp4_path: Path, timestamp_s: float, out_png: Path) -> Image.Image:
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-ss",
        f"{timestamp_s:.3f}",
        "-i",
        str(mp4_path),
        "-frames:v",
        "1",
        str(out_png),
    ]
    subprocess.run(cmd, check=True, shell=False)
    with Image.open(out_png) as im:
        return im.convert("RGB")


def run_e2e_a() -> dict:
    """E2E-A: Hero Frame PNG in both ratios with >100 unique colors."""
    shot = ShotSpec(
        id="SH01",
        scene="S01",
        duration=2.0,
        look="parallax_cards",
        slots={"kicker": "V2 ENGINE", "headline": "Ship faster", "sub": "Real Chromium frames"},
    ).model_dump()

    outputs = {}
    for ratio in ("9:16", "16:9"):
        tag = ratio.replace(":", "x")
        png_path = render_hero_frame(
            shot,
            ratio=ratio,
            out_path=ARTIFACTS_DIR / f"hero_{tag}.png",
            base_dir=ROOT,
        )
        with Image.open(png_path) as im:
            colors = _unique_colors_downscaled(im)
        if colors <= 100:
            raise AssertionError(f"E2E-A failed for {ratio}: only {colors} unique colors")
        outputs[ratio] = {"path": str(png_path.relative_to(ROOT)), "unique_colors": colors}
    return {"status": "PASS", "outputs": outputs}


def run_e2e_b() -> dict:
    """E2E-B: Motion MP4 in both ratios verified by ffprobe + Pillow frame delta."""
    shot = ShotSpec(
        id="SH01",
        scene="S01",
        duration=2.0,
        look="parallax_cards",
        slots={"kicker": "CAMERA RIG", "headline": "35mm Dolly In", "sub": "25% vs 75% delta"},
    ).model_dump()

    outputs = {}
    for ratio in ("9:16", "16:9"):
        tag = ratio.replace(":", "x")
        mp4_path = ARTIFACTS_DIR / f"motion_{tag}.mp4"
        metrics = render_shot(shot, ratio=ratio, out_path=mp4_path, fps=30, base_dir=ROOT)
        stream = _ffprobe_video(mp4_path)
        if stream.get("codec_name") != "h264":
            raise AssertionError(f"Expected h264, got {stream}")

        f25 = _extract_frame(mp4_path, 0.5, ARTIFACTS_DIR / f"f25_{tag}.png")
        f75 = _extract_frame(mp4_path, 1.5, ARTIFACTS_DIR / f"f75_{tag}.png")
        diff = ImageChops.difference(f25, f75).convert("L")
        hist = diff.histogram()
        changed = sum(hist[7:])  # px > 6 (filters H.264 macroblock compression noise)
        total = diff.width * diff.height
        changed_ratio = changed / max(1, total)
        if changed_ratio < 0.05:
            raise AssertionError(f"Static video detected ({changed_ratio:.2%} changed pixels)")

        outputs[ratio] = {
            "metrics": metrics.model_dump(),
            "ffprobe": stream,
            "changed_pixel_ratio": round(changed_ratio, 4),
        }
    return {"status": "PASS", "outputs": outputs}


def run_e2e_d() -> dict:
    """E2E-D: Real Gemini prompt -> ShotPlan -> rendered clip."""
    agent = MotionDirectorAgent()
    plan, repairs = agent.plan_from_brief(
        "Create a 3-shot launch teaser for an AI video director studio.",
        ratios=["16:9"],
        genre="product_demo",
        run_dom_gate=True,
    )
    first_shot = plan.shots[0].model_dump()
    mp4_path = ARTIFACTS_DIR / "e2e_d_shot1.mp4"
    metrics = render_shot(first_shot, ratio="16:9", out_path=mp4_path, fps=30, base_dir=ROOT)
    return {
        "status": "PASS",
        "repairs_used": repairs,
        "shot_count": len(plan.shots),
        "metrics": metrics.model_dump(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Motion Studio v2 real-engine smoke runner")
    parser.add_argument("--scenario", choices=["E2E-A", "E2E-B", "E2E-D"], default=None)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    runners = {"E2E-A": run_e2e_a, "E2E-B": run_e2e_b}
    if args.scenario == "E2E-D":
        runners = {"E2E-D": run_e2e_d}
    elif args.scenario:
        runners = {args.scenario: runners[args.scenario]}

    t0 = time.perf_counter()
    results: dict[str, dict] = {}
    failed = 0

    for name, fn in runners.items():
        try:
            results[name] = fn()
        except Exception as exc:
            failed += 1
            results[name] = {"status": "FAIL", "error": str(exc)}

    report = {
        "git_head": _git_head(),
        "seconds": round(time.perf_counter() - t0, 3),
        "passed": len(results) - failed,
        "failed": failed,
        "scenarios": results,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "e2e_latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
