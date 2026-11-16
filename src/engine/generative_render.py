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
from src.engine.generative_schema import GenerativeShotCode, GenerativeStoryboard, safe_resolve_path

GENERATIVE_HOST_HTML = Path(__file__).resolve().parent / "generative_host.html"


class GenerativeRenderResult(BaseModel):
    out_path: str
    ratio: str
    frames: int
    total_seconds: float
    seconds_per_frame: float
    unique_colors_mid: int
    motion_delta_ratio: float


class SceneQualityError(RuntimeError):
    def __init__(self, findings: list[str]) -> None:
        self.findings = findings
        super().__init__("Generative scene failed visual/DOM verification: " + "; ".join(findings))


def _unique_colors_thumb(img: Image.Image) -> int:
    w, h = img.size
    thumb_h = max(1, int(round(h * (120.0 / w))))
    thumb = img.convert("RGB").resize((120, thumb_h), Image.Resampling.BILINEAR)
    colors = thumb.getcolors(maxcolors=120 * thumb_h)
    return len(colors or [])


def _pixel_delta_ratio(img_a: Image.Image, img_b: Image.Image) -> float:
    diff = ImageChops.difference(img_a.convert("RGB"), img_b.convert("RGB")).convert("L")
    hist = diff.histogram()
    changed = sum(hist[11:])  # px > 10
    return changed / max(1, diff.width * diff.height)


def audit_and_capture_keyframes(
    shot: GenerativeShotCode,
    ratio: Literal["9:16", "16:9"],
    host_html: Path = GENERATIVE_HOST_HTML,
) -> tuple[list[str], list[bytes]]:
    """
    Launch Chromium, mount AI-generated code, verify DOM geometry & pixel motion across
    [10%, 50%, 90%] keyframes, and return (findings, keyframe_png_bytes).
    """
    vw, vh = RATIO_DIMENSIONS[ratio]
    left_m, top_m, right_m, bottom_m = SAFE_MARGINS[ratio]
    safe_l, safe_t = vw * left_m, vh * top_m
    safe_r, safe_b = vw * (1.0 - right_m), vh * (1.0 - bottom_m)

    findings: list[str] = []
    keyframe_pngs: list[bytes] = []
    captured_imgs: list[Image.Image] = []
    shot_dict = shot.model_dump()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": vw, "height": vh})
            page = context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            page.goto(host_html.resolve().as_uri(), wait_until="load")
            page.evaluate("(s) => window.mountGenerativeShot(s)", shot_dict)
            page.wait_for_function("window.ready === true", timeout=10_000)

            for frac in (0.10, 0.50, 0.90):
                ts = round(shot.duration * frac, 4)
                page.evaluate("([t, dur]) => window.seek(t, dur)", [ts, shot.duration])
                info = page.evaluate("() => window.inspectScene()")

                if info.get("lastRuntimeError"):
                    findings.append(str(info["lastRuntimeError"]))
                if info.get("childElementCount", 0) < 1:
                    findings.append("Scene rendered zero DOM/SVG/Canvas elements inside #scene-canvas.")

                for el in info.get("textElements", []):
                    if el["left"] < 0 or el["right"] > vw:
                        findings.append(
                            f"[{ratio} @ {ts}s] Text '{el['text']}' overflows viewport ({el['left']:.0f}..{el['right']:.0f}px vs {vw}px)."
                        )
                    elif (
                        el["left"] < safe_l - 8
                        or el["top"] < safe_t - 8
                        or el["right"] > safe_r + 8
                        or el["bottom"] > safe_b + 8
                    ):
                        findings.append(
                            f"[{ratio} @ {ts}s] Text '{el['text']}' drifts outside safe area."
                        )

                png_bytes = page.screenshot(type="png")
                keyframe_pngs.append(png_bytes)
                captured_imgs.append(Image.open(BytesIO(png_bytes)).convert("RGB"))

            if page_errors:
                findings.append(f"Uncaught browser JS error: {page_errors[0]}")
            context.close()
        finally:
            browser.close()

    if len(captured_imgs) == 3:
        mid_colors = _unique_colors_thumb(captured_imgs[1])
        if mid_colors < 15:
            findings.append(
                f"[{ratio}] Rendered scene is nearly blank/monochrome ({mid_colors} unique colors at 50%)."
            )
        delta_10_90 = _pixel_delta_ratio(captured_imgs[0], captured_imgs[2])
        if delta_10_90 < 0.015:
            findings.append(
                f"[{ratio}] Animation appears frozen ({delta_10_90:.2%} pixel change between 10% and 90%)."
            )

    return findings, keyframe_pngs


def render_generative_shot(
    shot: GenerativeShotCode,
    ratio: Literal["9:16", "16:9"],
    out_path: Path,
    fps: int = 30,
    base_dir: Path | None = None,
    host_html: Path = GENERATIVE_HOST_HTML,
    run_preflight: bool = True,
) -> GenerativeRenderResult:
    """Render an AI-coded shot to H.264 MP4 after verifying geometry and motion."""
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg executable not found on PATH.")

    root = (base_dir or Path.cwd()).resolve()
    target = safe_resolve_path(root, out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = target.with_suffix(".tmp.mp4")

    if run_preflight:
        findings, _ = audit_and_capture_keyframes(shot, ratio=ratio, host_html=host_html)
        if findings:
            raise SceneQualityError(findings)

    vw, vh = RATIO_DIMENSIONS[ratio]
    total_frames = max(2, int(round(shot.duration * fps)))
    shot_dict = shot.model_dump()

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
    mid_img: Image.Image | None = None
    first_img: Image.Image | None = None
    last_img: Image.Image | None = None
    proc: subprocess.Popen[bytes] | None = None

    try:
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        assert proc.stdin is not None

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={"width": vw, "height": vh})
                page = context.new_page()
                page.goto(host_html.resolve().as_uri(), wait_until="load")
                page.evaluate("(s) => window.mountGenerativeShot(s)", shot_dict)
                page.wait_for_function("window.ready === true", timeout=10_000)

                for idx in range(total_frames):
                    ts = idx / fps
                    page.evaluate("([t, dur]) => window.seek(t, dur)", [ts, shot.duration])
                    png_bytes = page.screenshot(type="png")
                    proc.stdin.write(png_bytes)

                    if idx == 0:
                        first_img = Image.open(BytesIO(png_bytes)).convert("RGB")
                    elif idx == total_frames // 2:
                        mid_img = Image.open(BytesIO(png_bytes)).convert("RGB")
                    elif idx == total_frames - 1:
                        last_img = Image.open(BytesIO(png_bytes)).convert("RGB")

                context.close()
            finally:
                browser.close()

        proc.stdin.close()
        stderr = proc.stderr.read() if proc.stderr else b""
        if proc.wait(timeout=45) != 0:
            raise RuntimeError(f"ffmpeg encode failed: {stderr.decode('utf-8', 'replace')}")
        os.replace(tmp_mp4, target)
    except Exception:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if tmp_mp4.exists():
            tmp_mp4.unlink()
        raise

    elapsed = max(0.001, time.perf_counter() - t0)
    unique_mid = _unique_colors_thumb(mid_img) if mid_img else 0
    delta = _pixel_delta_ratio(first_img, last_img) if (first_img and last_img) else 0.0

    return GenerativeRenderResult(
        out_path=str(target),
        ratio=ratio,
        frames=total_frames,
        total_seconds=round(elapsed, 3),
        seconds_per_frame=round(elapsed / total_frames, 4),
        unique_colors_mid=unique_mid,
        motion_delta_ratio=round(delta, 4),
    )


def render_storyboard_master(
    storyboard: GenerativeStoryboard,
    ratio: Literal["9:16", "16:9"],
    out_dir: Path,
    fps: int = 30,
    base_dir: Path | None = None,
) -> Path:
    """Render every AI-coded shot and concatenate into master_<ratio>.mp4."""
    root = (base_dir or Path.cwd()).resolve()
    work_dir = safe_resolve_path(root, out_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    tag = ratio.replace(":", "x")

    clip_paths: list[Path] = []
    for idx, shot in enumerate(storyboard.shots):
        clip_path = work_dir / f"shot_{idx:02d}_{shot.id}_{tag}.mp4"
        render_generative_shot(shot, ratio=ratio, out_path=clip_path, fps=fps, base_dir=root)
        clip_paths.append(clip_path)

    master_path = work_dir / f"master_{tag}.mp4"
    if len(clip_paths) == 1:
        shutil.copyfile(clip_paths[0], master_path)
        return master_path

    concat_list = work_dir / f"concat_{tag}.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in clip_paths),
        encoding="utf-8",
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        str(master_path),
    ]
    subprocess.run(cmd, stdin=subprocess.DEVNULL, check=True, shell=False)
    return master_path
