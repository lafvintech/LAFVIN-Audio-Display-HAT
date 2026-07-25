from __future__ import annotations

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


def test_video_player_resolves_fixed_project_asset_video(tmp_path: Path) -> None:
    app = _load_module()
    media_dir = tmp_path / "assets" / "videos"
    media_dir.mkdir(parents=True)
    expected = media_dir / "test.mp4"
    expected.write_bytes(b"placeholder")

    assert app.resolve_video_directory(project_root=tmp_path) == media_dir
    assert app.resolve_video_file(project_root=tmp_path) == expected


def test_video_player_uses_fixed_filename_even_with_other_videos(
    tmp_path: Path,
) -> None:
    app = _load_module()
    media_dir = tmp_path / "assets" / "videos"
    media_dir.mkdir(parents=True)
    (media_dir / "aaa.mp4").write_bytes(b"ignored")

    assert app.resolve_video_file(project_root=tmp_path) == media_dir / "test.mp4"


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
