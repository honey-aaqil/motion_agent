from __future__ import annotations

import os
import shutil
import subprocess
import time
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright
from pydantic import BaseModel

from src.engine.gate import RATIO_DIMENSIONS, SAFE_MARGINS
from src.engine.parametric_schema import (
    ParametricShot,
    ParametricVideoProject,
    safe_resolve_path,
)

PARAMETRIC_HOST_HTML = Path(__file__).resolve().parent / "parametric_host.html"


class ParametricRenderStats(BaseModel):
    out_path: str
    ratio: str
    frames: int
    seconds: float
    unique_colors_mid: int
    pixel_delta_ratio: float


class ParametricQualityError(RuntimeError):
    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("Parametric shot failed quality check: " + "; ".join(issues))


def _unique_colors(img: Image.Image) -> int:
    w, h = img.size
    thumb_h = max(1, int(round(h * (120.0 / w))))
    thumb = img.convert("RGB").resize((120, thumb_h), Image.Resampling.BILINEAR)
    colors = thumb.getcolors(maxcolors=120 * thumb_h)
    return len(colors or [])


def _delta_ratio(a: Image.Image, b: Image.Image) -> float:
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    hist = diff.histogram()
    changed = sum(hist[11:])  # px > 10
    return changed / max(1, diff.width * diff.height)


def audit_parametric_shot(
    shot: ParametricShot,
    ratio: Literal["9:16", "16:9"],
    host_html: Path = PARAMETRIC_HOST_HTML,
) -> tuple[list[str], list[bytes]]:
    vw, vh = RATIO_DIMENSIONS[ratio]
    lm, tm, rm, bm = SAFE_MARGINS[ratio]
    sl, st, sr, sb = vw * lm, vh * tm, vw * (1.0 - rm), vh * (1.0 - bm)

    issues: list[str] = []
    pngs: list[bytes] = []
    imgs: list[Image.Image] = []
    shot_dict = shot.model_dump()
    props = shot.resolved_props()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(viewport={"width": vw, "height": vh})
            page = ctx.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            page.goto(host_html.resolve().as_uri(), wait_until="load")
            page.evaluate("([s, p]) => window.mountParametricShot(s, p)", [shot_dict, props])
            page.wait_for_function("window.ready === true", timeout=10_000)

            for frac in (0.10, 0.50, 0.90):
                ts = round(shot.duration * frac, 4)
                page.evaluate("([t, dur]) => window.seek(t, dur)", [ts, shot.duration])
                info = page.evaluate("() => window.inspectScene()")

                if info.get("lastRuntimeError"):
                    issues.append(str(info["lastRuntimeError"]))
                if info.get("childElementCount", 0) < 1:
                    issues.append("Scene mounted zero visual elements.")

                for el in info.get("textElements", []):
                    if el["left"] < 0 or el["right"] > vw:
                        issues.append(f"[{ratio} @ {ts}s] Text '{el['text']}' overflows frame.")
                    elif (
                        el["left"] < sl - 10
                        or el["top"] < st - 10
                        or el["right"] > sr + 10
                        or el["bottom"] > sb + 10
                    ):
                        issues.append(f"[{ratio} @ {ts}s] Text '{el['text']}' outside safe margin.")

                frame_bytes = page.screenshot(type="png")
                pngs.append(frame_bytes)
                imgs.append(Image.open(BytesIO(frame_bytes)).convert("RGB"))

            if page_errors:
                issues.append(f"JS runtime error: {page_errors[0]}")
            ctx.close()
        finally:
            browser.close()

    if len(imgs) == 3:
        colors = _unique_colors(imgs[1])
        if colors < 15:
            issues.append(f"[{ratio}] Rendered frame is blank/flat ({colors} unique colors).")
        delta = _delta_ratio(imgs[0], imgs[2])
        if delta < 0.015:
            issues.append(f"[{ratio}] Scene has no visible motion ({delta:.2%} pixel change).")

    return issues, pngs


def render_parametric_shot(
    shot: ParametricShot,
    ratio: Literal["9:16", "16:9"],
    out_path: Path,
    fps: int = 30,
    base_dir: Path | None = None,
    host_html: Path = PARAMETRIC_HOST_HTML,
    preflight: bool = True,
) -> ParametricRenderStats:
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg executable not found on PATH.")

    root = (base_dir or Path.cwd()).resolve()
    target = safe_resolve_path(root, out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = target.with_suffix(".tmp.mp4")

    if preflight:
        issues, _ = audit_parametric_shot(shot, ratio=ratio, host_html=host_html)
        if issues:
            raise ParametricQualityError(issues)

    vw, vh = RATIO_DIMENSIONS[ratio]
    total_frames = max(2, int(round(shot.duration * fps)))
    shot_dict = shot.model_dump()
    props = shot.resolved_props()

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-r",
        str(fps),
        "-i",
        "-",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "18",
        "-movflags",
        "+faststart",
        str(tmp_mp4),
    ]

    t0 = time.perf_counter()
    first_im: Image.Image | None = None
    mid_im: Image.Image | None = None
    last_im: Image.Image | None = None
    proc: subprocess.Popen[bytes] | None = None

    try:
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        assert proc.stdin is not None

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(viewport={"width": vw, "height": vh})
                page = ctx.new_page()
                page.goto(host_html.resolve().as_uri(), wait_until="load")
                page.evaluate("([s, p]) => window.mountParametricShot(s, p)", [shot_dict, props])
                page.wait_for_function("window.ready === true", timeout=10_000)

                for i in range(total_frames):
                    ts = i / fps
                    page.evaluate("([t, dur]) => window.seek(t, dur)", [ts, shot.duration])
                    png_bytes = page.screenshot(type="png")
                    proc.stdin.write(png_bytes)

                    if i == 0:
                        first_im = Image.open(BytesIO(png_bytes)).convert("RGB")
                    elif i == total_frames // 2:
                        mid_im = Image.open(BytesIO(png_bytes)).convert("RGB")
                    elif i == total_frames - 1:
                        last_im = Image.open(BytesIO(png_bytes)).convert("RGB")

                ctx.close()
            finally:
                browser.close()

        proc.stdin.close()
        stderr = proc.stderr.read() if proc.stderr else b""
        if proc.wait(timeout=45) != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr.decode('utf-8', 'replace')}")
        os.replace(tmp_mp4, target)
    except Exception:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if tmp_mp4.exists():
            tmp_mp4.unlink()
        raise

    elapsed = max(0.001, time.perf_counter() - t0)
    return ParametricRenderStats(
        out_path=str(target),
        ratio=ratio,
        frames=total_frames,
        seconds=round(elapsed, 3),
        unique_colors_mid=_unique_colors(mid_im) if mid_im else 0,
        pixel_delta_ratio=round(_delta_ratio(first_im, last_im), 4) if (first_im and last_im) else 0.0,
    )


def render_parametric_project(
    project: ParametricVideoProject,
    ratio: Literal["9:16", "16:9"],
    out_dir: Path,
    fps: int = 30,
    base_dir: Path | None = None,
) -> Path:
    root = (base_dir or Path.cwd()).resolve()
    work_dir = safe_resolve_path(root, out_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    tag = ratio.replace(":", "x")

    clips: list[Path] = []
    for idx, shot in enumerate(project.shots):
        clip = work_dir / f"shot_{idx:02d}_{shot.id}_{tag}.mp4"
        render_parametric_shot(shot, ratio=ratio, out_path=clip, fps=fps, base_dir=root)
        clips.append(clip)

    master = work_dir / f"master_{tag}.mp4"
    if len(clips) == 1:
        shutil.copyfile(clips[0], master)
        return master

    concat_txt = work_dir / f"concat_{tag}.txt"
    concat_txt.write_text(
        "\n".join(f"file '{c.resolve().as_posix()}'" for c in clips),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-c",
            "copy",
            str(master),
        ],
        stdin=subprocess.DEVNULL,
        check=True,
        shell=False,
    )
    return master
