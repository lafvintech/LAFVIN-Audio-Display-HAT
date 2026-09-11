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
SUPPORTED_VIDEO_SUFFIXES = frozenset(
    {".mp4", ".mov", ".mkv", ".webm", ".avi"}
)


def resolve_video_directory(*, project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_root / ASSETS_VIDEO_RELATIVE_PATH
    for candidate_root in _candidate_project_roots():
        candidate = candidate_root / ASSETS_VIDEO_RELATIVE_PATH
        if candidate.is_dir():
            return candidate
    return _source_project_root() / ASSETS_VIDEO_RELATIVE_PATH


def discover_video_files(*, project_root: Path | None = None) -> list[Path]:
    directory = resolve_video_directory(project_root=project_root)
    if not directory.is_dir():
        return []
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file()
            and not path.name.startswith(".")
            and path.suffix.lower() in SUPPORTED_VIDEO_SUFFIXES
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )


def next_selection(selected: int, item_count: int) -> int:
    if item_count <= 0:
        return 0
    return (selected + 1) % item_count


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


def render_selector_frame(
    videos: list[Path],
    selected: int,
    *,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> bytes:
    image = Image.new("RGB", (width, height), (10, 12, 18))
    draw = ImageDraw.Draw(image)
    title_font = load_ui_font(22, bold=True)
    item_font = load_ui_font(16)
    selected_font = load_ui_font(16, bold=True)
    hint_font = load_ui_font(13)

    draw.text((14, 14), "Video Player", fill=(255, 255, 255), font=title_font)
    counter = f"{selected + 1} / {len(videos)}" if videos else "0 / 0"
    counter_width = draw.textlength(counter, font=hint_font)
    draw.text(
        (width - 14 - counter_width, 21),
        counter,
        fill=(170, 177, 190),
        font=hint_font,
    )
    draw.line((14, 50, width - 14, 50), fill=(70, 76, 92), width=1)

    for row, index in enumerate(_visible_video_indices(len(videos), selected)):
        y = 64 + row * 45
        is_selected = index == selected
        if is_selected:
            draw.rounded_rectangle(
                (12, y, width - 12, y + 36),
                radius=8,
                fill=(104, 72, 214),
            )
            draw.polygon(
                ((24, y + 11), (24, y + 25), (35, y + 18)),
                fill=(255, 255, 255),
            )
        else:
            draw.rounded_rectangle(
                (12, y, width - 12, y + 36),
                radius=8,
                outline=(54, 60, 76),
                width=1,
            )
        name = _ellipsize(videos[index].name, 22)
        draw.text(
            (44, y + 8),
            name,
            fill=(255, 255, 255) if is_selected else (170, 177, 190),
            font=selected_font if is_selected else item_font,
        )

    draw.line((14, height - 68, width - 14, height - 68), fill=(70, 76, 92), width=1)
    hints = (
        ("Single click", "Next video"),
        ("Double click", "Play"),
        ("Triple click", "Home"),
    )
    for index, (gesture, action) in enumerate(hints):
        y = height - 61 + index * 18
        draw.text((16, y), gesture, fill=(142, 116, 238), font=hint_font)
        action_width = draw.textlength(action, font=hint_font)
        draw.text(
            (width - 16 - action_width, y),
            action,
            fill=(190, 196, 207),
            font=hint_font,
        )
    return _image_to_rgb565_be(image)


async def main() -> None:
    app = await DeviceApp.connect_from_environment()
    await app.acquire_foreground()
    frame = await app.frames.acquire()
    stop_event = asyncio.Event()
    playback_stop_event = asyncio.Event()
    command_queue: asyncio.Queue[str] = asyncio.Queue()
    selection_active = asyncio.Event()
    selection_active.set()
    events = app.subscribe(
        events=[
            "button.single_clicked",
            "button.double_clicked",
            "app.exit_requested",
        ]
    )
    event_task = asyncio.create_task(
        _watch_events(
            events,
            command_queue,
            stop_event,
            selection_active,
            playback_stop_event,
        ),
        name="video-player-events",
    )

    try:
        videos = discover_video_files()
        if not videos:
            selection_active.clear()
            await _show_message(
                frame,
                "No Videos",
                [
                    "Add a video file to:",
                    "assets/videos/",
                    "Supported:",
                    "MP4 MOV MKV WEBM AVI",
                    "Triple-click: Home",
                ],
            )
            await stop_event.wait()
            return
        if shutil.which("ffmpeg") is None:
            selection_active.clear()
            await _show_message(
                frame,
                "ffmpeg Missing",
                ["Install ffmpeg to play video.", "Triple-click: Home"],
            )
            await stop_event.wait()
            return

        selected = 0
        await _show_selector(frame, videos, selected)
        while not stop_event.is_set():
            command = await _next_command(command_queue, stop_event)
            if command is None:
                break
            if command == "button.single_clicked":
                selected = next_selection(selected, len(videos))
                await _show_selector(frame, videos, selected)
                continue
            if command != "button.double_clicked":
                continue

            video_path = videos[selected]
            playback_stop_event.clear()
            selection_active.clear()
            print(f"[VideoPlayer] playing {video_path}", flush=True)
            try:
                await _play_video(
                    frame,
                    video_path,
                    stop_event,
                    playback_stop_event,
                )
            except Exception as exc:
                print(f"[VideoPlayer] playback error: {exc}", flush=True)
                if not stop_event.is_set():
                    await _show_message(
                        frame,
                        "Playback Error",
                        [_ellipsize(video_path.name, 24), str(exc)],
                    )
                    await asyncio.sleep(1.5)
            finally:
                selection_active.set()
            if not stop_event.is_set():
                await _show_selector(frame, videos, selected)
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


async def _watch_events(
    events: object,
    command_queue: asyncio.Queue[str],
    stop_event: asyncio.Event,
    selection_active: asyncio.Event,
    playback_stop_event: asyncio.Event,
) -> None:
    async for event in events:  # type: ignore[attr-defined]
        name = event["event"]
        if name == "app.exit_requested":
            stop_event.set()
            playback_stop_event.set()
            return
        if selection_active.is_set():
            if name in {
                "button.single_clicked",
                "button.double_clicked",
            }:
                command_queue.put_nowait(name)
            continue
        if name == "button.single_clicked":
            playback_stop_event.set()


async def _show_message(
    frame: RawFrameSession,
    title: str,
    lines: list[str],
) -> None:
    frame.write(render_message_frame(title, lines))
    await frame.commit()


async def _show_selector(
    frame: RawFrameSession,
    videos: list[Path],
    selected: int,
) -> None:
    frame.write(render_selector_frame(videos, selected))
    await frame.commit()


async def _next_command(
    command_queue: asyncio.Queue[str],
    stop_event: asyncio.Event,
) -> str | None:
    command_task = asyncio.create_task(command_queue.get())
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        {command_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    if stop_task in done:
        return None
    return command_task.result()


async def _play_video(
    frame: RawFrameSession,
    video_path: Path,
    stop_event: asyncio.Event,
    playback_stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set() and not playback_stop_event.is_set():
        await _play_video_once(
            frame,
            video_path,
            stop_event,
            playback_stop_event,
        )


async def _play_video_once(
    frame: RawFrameSession,
    video_path: Path,
    stop_event: asyncio.Event,
    playback_stop_event: asyncio.Event,
) -> None:
    frame_interval = 1 / max(1, int(os.getenv("LAFVIN_VIDEO_FPS", TARGET_FPS)))
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
                    playback_stop_event,
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
        force = stop_event.is_set() or playback_stop_event.is_set()
        await _stop_process(process, force=force)
        await _stop_process(audio_process, force=force)

    if stop_event.is_set() or playback_stop_event.is_set():
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
    *stop_events: asyncio.Event,
) -> bytes | None:
    read_task = asyncio.create_task(stream.readexactly(size))
    stop_tasks = {
        asyncio.create_task(stop_event.wait())
        for stop_event in stop_events
    }
    done, pending = await asyncio.wait(
        {read_task, *stop_tasks},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    if any(stop_task in done for stop_task in stop_tasks):
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


def _visible_video_indices(item_count: int, selected: int) -> list[int]:
    if item_count <= 0:
        return []
    if item_count <= 3:
        return list(range(item_count))
    return [
        (selected - 1) % item_count,
        selected,
        (selected + 1) % item_count,
    ]


def _ellipsize(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:max(1, limit - 3)]}..."


def _image_to_rgb565_be(image: Image.Image) -> bytes:
    rgb = image.convert("RGB")
    output = bytearray()
    for red, green, blue in rgb.getdata():
        value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        output.extend((value >> 8, value & 0xFF))
    return bytes(output)


if __name__ == "__main__":
    asyncio.run(main())
