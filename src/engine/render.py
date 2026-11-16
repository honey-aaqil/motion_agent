from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Literal

import psutil
from playwright.sync_api import sync_playwright
from pydantic import BaseModel

from src.engine.gate import RATIO_DIMENSIONS, evaluate_dom_gate
from src.engine.schema import safe_resolve_path

DEFAULT_SHOT_HTML = Path(__file__).resolve().parent / "shot.html"


class RenderMetrics(BaseModel):
    out_path: str
    ratio: str
    frames: int
    total_seconds: float
    seconds_per_frame: float
    peak_rss_mb: float


class DomGateRejectedError(RuntimeError):
    def __init__(self, findings: list[dict]) -> None:
        self.findings = findings
        super().__init__(f"DOM layout gate rejected shot with {len(findings)} finding(s).")


def _tree_rss_mb(pid: int) -> float:
    try:
        proc = psutil.Process(pid)
        rss = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                rss += child.memory_info().rss
            except psutil.Error:
                continue
        return round(rss / (1024 * 1024), 2)
    except psutil.Error:
        return 0.0


def render_hero_frame(
    plan_shot: dict,
    ratio: Literal["9:16", "16:9"],
    out_path: Path,
    base_dir: Path | None = None,
    html_path: Path = DEFAULT_SHOT_HTML,
    hero_fraction: float = 0.5,
) -> Path:
    """Render a real PNG Hero Frame at the shot's peak visual moment."""
    root = (base_dir or Path.cwd()).resolve()
    target = safe_resolve_path(root, out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_png = target.with_suffix(".tmp.png")

    vw, vh = RATIO_DIMENSIONS[ratio]
    duration = float(plan_shot.get("duration", 2.0))
    t_hero = round(duration * max(0.0, min(1.0, hero_fraction)), 4)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": vw, "height": vh})
            page = context.new_page()
            page.goto(html_path.resolve().as_uri(), wait_until="load")
            page.evaluate("(s) => window.loadShot(s)", plan_shot)
            page.wait_for_function("window.ready === true", timeout=10_000)
            page.evaluate("([ts, dur]) => window.seek(ts, dur)", [t_hero, duration])
            page.screenshot(path=str(tmp_png), type="png")
            context.close()
        finally:
            browser.close()

    os.replace(tmp_png, target)
    return target


def render_shot(
    plan_shot: dict,
    ratio: Literal["9:16", "16:9"],
    out_path: Path,
    fps: int = 30,
    base_dir: Path | None = None,
    html_path: Path = DEFAULT_SHOT_HTML,
    enforce_gate: bool = True,
) -> RenderMetrics:
    """Deterministically render a Shot Plan item into an H.264 MP4 via Playwright + FFmpeg."""
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg executable not found on PATH.")
    if fps < 1 or fps > 120:
        raise ValueError(f"Invalid fps: {fps}")

    root = (base_dir or Path.cwd()).resolve()
    target = safe_resolve_path(root, out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = target.with_suffix(".tmp.mp4")

    if enforce_gate:
        findings = evaluate_dom_gate(plan_shot, [ratio], html_path=html_path)
        if findings:
            raise DomGateRejectedError([f.model_dump() for f in findings])

    vw, vh = RATIO_DIMENSIONS[ratio]
    duration = float(plan_shot.get("duration", 2.0))
    total_frames = max(2, int(round(duration * fps)))
    scene_uri = html_path.resolve().as_uri()

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
    peak_rss = _tree_rss_mb(os.getpid())
    ffmpeg_proc: subprocess.Popen[bytes] | None = None

    try:
        ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        assert ffmpeg_proc.stdin is not None

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={"width": vw, "height": vh})
                page = context.new_page()
                page.goto(scene_uri, wait_until="load")
                page.evaluate("(s) => window.loadShot(s)", plan_shot)
                page.wait_for_function("window.ready === true", timeout=10_000)

                for frame_idx in range(total_frames):
                    ts = frame_idx / fps
                    page.evaluate("([t, dur]) => window.seek(t, dur)", [ts, duration])
                    png_bytes = page.screenshot(type="png")
                    ffmpeg_proc.stdin.write(png_bytes)

                    if frame_idx % 15 == 0:
                        peak_rss = max(peak_rss, _tree_rss_mb(os.getpid()))

                context.close()
            finally:
                browser.close()

        ffmpeg_proc.stdin.close()
        stderr_bytes = ffmpeg_proc.stderr.read() if ffmpeg_proc.stderr else b""
        ret = ffmpeg_proc.wait(timeout=30)
        if ret != 0:
            raise RuntimeError(f"ffmpeg failed (exit {ret}): {stderr_bytes.decode('utf-8', 'replace')}")

        os.replace(tmp_mp4, target)
    except Exception:
        if ffmpeg_proc is not None and ffmpeg_proc.poll() is None:
            ffmpeg_proc.kill()
            ffmpeg_proc.wait(timeout=5)
        if tmp_mp4.exists():
            tmp_mp4.unlink()
        raise

    elapsed = max(0.001, time.perf_counter() - t0)
    return RenderMetrics(
        out_path=str(target),
        ratio=ratio,
        frames=total_frames,
        total_seconds=round(elapsed, 3),
        seconds_per_frame=round(elapsed / total_frames, 4),
        peak_rss_mb=peak_rss,
    )
