from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "video_player" / "main.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "lafvin_video_player_app",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_video_player_discovers_supported_project_asset_videos(
    tmp_path: Path,
) -> None:
    app = _load_module()
    media_dir = tmp_path / "assets" / "videos"
    media_dir.mkdir(parents=True)
    first = media_dir / "Alpha.MKV"
    second = media_dir / "beta.mp4"
    first.write_bytes(b"placeholder")
    second.write_bytes(b"placeholder")
    (media_dir / "notes.txt").write_text("ignored", encoding="utf-8")
    (media_dir / ".hidden.mov").write_bytes(b"ignored")
    (media_dir / "folder.avi").mkdir()

    assert app.resolve_video_directory(project_root=tmp_path) == media_dir
    assert app.discover_video_files(project_root=tmp_path) == [first, second]


def test_video_player_returns_empty_list_when_directory_is_missing(
    tmp_path: Path,
) -> None:
    app = _load_module()

    assert app.discover_video_files(project_root=tmp_path) == []


def test_video_player_prefers_deployed_project_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _load_module()
    media_dir = tmp_path / "assets" / "videos"
    media_dir.mkdir(parents=True)
    monkeypatch.setenv("LAFVIN_PROJECT_ROOT", str(tmp_path))

    assert app.resolve_video_directory() == media_dir


def test_video_player_ffmpeg_command_outputs_rgb565_rawvideo() -> None:
    app = _load_module()

    cmd = app.build_ffmpeg_cmd(
        Path("clip.mp4"),
        width=240,
        height=280,
        fps=30,
        model="Raspberry Pi Zero 2 W Rev 1.0",
    )

    assert cmd[0] == "ffmpeg"
    assert "-nostdin" in cmd
    assert "-analyzeduration" in cmd
    assert "-probesize" in cmd
    assert "-threads" in cmd
    assert "scale=240:280:flags=fast_bilinear,fps=30" in cmd
    assert "-pix_fmt" in cmd
    assert "rgb565be" in cmd
    assert "-f" in cmd
    assert "rawvideo" in cmd
    assert cmd[-1] == "-"


def test_video_player_message_frame_matches_rgb565_size() -> None:
    app = _load_module()

    frame = app.render_message_frame(
        "Video Player",
        ["No video file found."],
        width=240,
        height=280,
    )

    assert len(frame) == 240 * 280 * 2


def test_video_player_selector_frame_matches_rgb565_size() -> None:
    app = _load_module()

    frame = app.render_selector_frame(
        [Path("first.mp4"), Path("second.webm")],
        1,
        width=240,
        height=280,
    )

    assert len(frame) == 240 * 280 * 2


def test_video_player_selection_wraps_and_centers_long_lists() -> None:
    app = _load_module()

    assert app.next_selection(0, 0) == 0
    assert app.next_selection(0, 3) == 1
    assert app.next_selection(2, 3) == 0
    assert app._visible_video_indices(2, 1) == [0, 1]
    assert app._visible_video_indices(5, 0) == [4, 0, 1]
    assert app._visible_video_indices(5, 3) == [2, 3, 4]


def test_video_player_single_click_stops_playback_without_queueing() -> None:
    async def scenario() -> None:
        app = _load_module()
        command_queue: asyncio.Queue[str] = asyncio.Queue()
        stop_event = asyncio.Event()
        selection_active = asyncio.Event()
        playback_stop_event = asyncio.Event()
        after_double = asyncio.Event()
        send_single = asyncio.Event()
        send_exit = asyncio.Event()

        async def events():
            yield {"event": "button.double_clicked"}
            after_double.set()
            await send_single.wait()
            yield {"event": "button.single_clicked"}
            await send_exit.wait()
            yield {"event": "app.exit_requested"}

        task = asyncio.create_task(
            app._watch_events(
                events(),
                command_queue,
                stop_event,
                selection_active,
                playback_stop_event,
            )
        )
        await asyncio.wait_for(after_double.wait(), timeout=0.5)
        assert command_queue.empty()
        assert playback_stop_event.is_set() is False

        send_single.set()
        await asyncio.wait_for(playback_stop_event.wait(), timeout=0.5)
        assert command_queue.empty()
        assert stop_event.is_set() is False

        send_exit.set()
        await asyncio.wait_for(task, timeout=0.5)
        assert stop_event.is_set() is True

    asyncio.run(scenario())


def test_video_player_frame_read_stops_when_returning_to_selector() -> None:
    async def scenario() -> None:
        app = _load_module()
        stream = asyncio.StreamReader()
        app_stop_event = asyncio.Event()
        playback_stop_event = asyncio.Event()
        read_task = asyncio.create_task(
            app._read_frame_or_stop(
                stream,
                2,
                app_stop_event,
                playback_stop_event,
            )
        )

        await asyncio.sleep(0)
        playback_stop_event.set()

        assert await asyncio.wait_for(read_task, timeout=0.5) is None

    asyncio.run(scenario())


def test_video_player_loops_selected_video_until_playback_stops(monkeypatch) -> None:
    async def scenario() -> None:
        app = _load_module()
        stop_event = asyncio.Event()
        playback_stop_event = asyncio.Event()
        play_count = 0

        async def play_once(*_args) -> None:
            nonlocal play_count
            play_count += 1
            if play_count == 2:
                playback_stop_event.set()

        monkeypatch.setattr(app, "_play_video_once", play_once)

        await app._play_video(
            object(),
            Path("selected.mp4"),
            stop_event,
            playback_stop_event,
        )

        assert play_count == 2

    asyncio.run(scenario())
