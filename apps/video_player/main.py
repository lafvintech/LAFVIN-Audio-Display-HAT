from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import time
from collections.abc import Iterator
from pathlib import Path

from PIL import Image, ImageDraw

from lafvin_hat.sdk import DeviceApp, RawFrameSession
from lafvin_hat.ui.fonts import load_ui_font


WIDTH = 240
HEIGHT = 280
TARGET_FPS = 30
ASSETS_VIDEO_RELATIVE_PATH = Path("assets") / "videos"
VIDEO_FILENAME = "test.mp4"


def resolve_video_file(*, project_root: Path | None = None) -> Path:
    return resolve_video_directory(project_root=project_root) / VIDEO_FILENAME


def resolve_video_directory(*, project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_root / ASSETS_VIDEO_RELATIVE_PATH
    for candidate_root in _candidate_project_roots():
        candidate = candidate_root / ASSETS_VIDEO_RELATIVE_PATH
        if candidate.is_dir():
            return candidate
    return _source_project_root() / ASSETS_VIDEO_RELATIVE_PATH


def build_ffmpeg_cmd(
    video_path: Path,
    *,
    width: int = WIDTH,
    height: int = HEIGHT,
    fps: int = TARGET_FPS,
    model: str | None = None,
) -> list[str]:
    model_text = (model if model is not None else _read_pi_model()).lower()
    input_args: list[str] = []
    scale_flags = "bilinear"

    if "zero 2" in model_text or "raspberry pi 3" in model_text:
        input_args = ["-threads", "4"]
        scale_flags = "fast_bilinear"
    elif "zero" in model_text:
        input_args = ["-vcodec", "h264_v4l2m2m"]
        scale_flags = "fast_bilinear"
    elif "raspberry pi 4" in model_text or "raspberry pi 5" in model_text:
        input_args = ["-threads", "4"]

    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-analyzeduration",
        "0",
        "-probesize",
        "32768",
        *input_args,
        "-i",
        str(video_path),
        "-an",
        "-vf",
        f"scale={width}:{height}:flags={scale_flags},fps={fps}",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb565be",
        "-f",
        "rawvideo",
        "-",
    ]


def render_message_frame(
    title: str,
    lines: list[str],
    *,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> bytes:
    image = Image.new("RGB", (width, height), (10, 12, 18))
    draw = ImageDraw.Draw(image)
    title_font = load_ui_font(24, bold=True)
    body_font = load_ui_font(16)
    muted = (170, 177, 190)
    draw.text((16, 18), title, fill=(255, 255, 255), font=title_font)
    draw.line((16, 52, width - 16, 52), fill=(70, 76, 92), width=1)
    y = 72
    for line in lines:
        for wrapped in _wrap(line, 24):
            draw.text((16, y), wrapped, fill=muted, font=body_font)
            y += 21
    return _image_to_rgb565_be(image)


async def main() -> None:
    app = await DeviceApp.connect_from_environment()
    await app.acquire_foreground()
    frame = await app.frames.acquire()
    stop_event = asyncio.Event()
    events = app.subscribe(events=["app.exit_requested"])
    event_task = asyncio.create_task(_watch_exit(events, stop_event))

    try:
        video_path = resolve_video_file()
        if not video_path.is_file():
            await _show_message(
                frame,
                "Video Missing",
                [
                    "Expected file:",
                    str(video_path),
                    "Edit VIDEO_FILENAME in",
                    "apps/video_player/main.py",
                    "to use another file.",
                ],
            )
            await stop_event.wait()
            return
        if shutil.which("ffmpeg") is None:
            await _show_message(
                frame,
                "ffmpeg Missing",
                ["Install ffmpeg to play video.", str(video_path.name)],
            )
            await stop_event.wait()
            return

        print(f"[VideoPlayer] playing {video_path}", flush=True)
        await _play_loop(frame, video_path, stop_event)
    except Exception as exc:
        print(f"[VideoPlayer] error: {exc}", flush=True)
        with contextlib.suppress(Exception):
            await _show_message(frame, "Video Error", [str(exc)])
            await stop_event.wait()
    finally:
        stop_event.set()
        event_task.cancel()
        await asyncio.gather(event_task, return_exceptions=True)
        with contextlib.suppress(Exception):
            await events.aclose()
        await app.close()


async def _watch_exit(events: object, stop_event: asyncio.Event) -> None:
    async for event in events:  # type: ignore[attr-defined]
        if event["event"] == "app.exit_requested":
            stop_event.set()
            return


async def _show_message(
    frame: RawFrameSession,
    title: str,
    lines: list[str],
) -> None:
    frame.write(render_message_frame(title, lines))
    await frame.commit()


async def _play_loop(
    frame: RawFrameSession,
    video_path: Path,
    stop_event: asyncio.Event,
) -> None:
    frame_interval = 1 / max(1, int(os.getenv("LAFVIN_VIDEO_FPS", TARGET_FPS)))
    while not stop_event.is_set():
        cmd = build_ffmpeg_cmd(video_path, fps=int(round(1 / frame_interval)))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        audio_process: asyncio.subprocess.Process | None = None
        frame_count = 0
        next_frame_at = time.monotonic()
        try:
            assert process.stdout is not None
            while not stop_event.is_set():
                try:
                    data = await _read_frame_or_stop(
                        process.stdout,
                        frame.size,
                        stop_event,
                    )
                except asyncio.IncompleteReadError:
                    break
                if data is None:
                    break
                frame.write(data)
                await frame.commit()
                if frame_count == 0:
                    audio_process = await _start_audio(video_path)
                frame_count += 1
                next_frame_at += frame_interval
                delay = next_frame_at - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    next_frame_at = time.monotonic()
        finally:
            force = stop_event.is_set()
            await _stop_process(process, force=force)
            await _stop_process(audio_process, force=force)

        if stop_event.is_set():
            return
        if frame_count == 0:
            stderr = b""
            if process.stderr is not None:
                with contextlib.suppress(Exception):
                    stderr = await process.stderr.read()
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(message or "ffmpeg produced no frames")


async def _read_frame_or_stop(
    stream: asyncio.StreamReader,
    size: int,
    stop_event: asyncio.Event,
) -> bytes | None:
    read_task = asyncio.create_task(stream.readexactly(size))
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        {read_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    if stop_task in done:
        return None
    return read_task.result()


async def _start_audio(video_path: Path) -> asyncio.subprocess.Process | None:
    enabled = os.getenv("LAFVIN_VIDEO_AUDIO", "1").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    if not enabled or shutil.which("ffplay") is None:
        return None
    return await asyncio.create_subprocess_exec(
        "ffplay",
        "-nodisp",
        "-autoexit",
        "-loglevel",
        "error",
        str(video_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def _stop_process(
    process: asyncio.subprocess.Process | None,
    *,
    force: bool = False,
) -> None:
    if process is None or process.returncode is not None:
        return
    if force:
        process.kill()
    else:
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=0.25 if force else 1.0)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


def _read_pi_model() -> str:
    path = Path("/proc/device-tree/model")
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _candidate_project_roots() -> Iterator[Path]:
    seen: set[Path] = set()
    configured_root = os.getenv("LAFVIN_PROJECT_ROOT")
    starts = [_source_project_root(), Path.cwd().resolve()]
    if configured_root:
        starts.insert(0, Path(configured_root).expanduser().resolve())
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate not in seen:
                seen.add(candidate)
                yield candidate
    for candidate in (Path("/opt/lafvin-hat"), Path.home() / "LAFVIN-HAT", Path.home() / "LAFVIN-Audio-Display-HAT"):
        if candidate not in seen:
            seen.add(candidate)
            yield candidate


def _source_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def _image_to_rgb565_be(image: Image.Image) -> bytes:
    rgb = image.convert("RGB")
    output = bytearray()
    for red, green, blue in rgb.getdata():
        value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        output.extend((value >> 8, value & 0xFF))
    return bytes(output)


if __name__ == "__main__":
    asyncio.run(main())
