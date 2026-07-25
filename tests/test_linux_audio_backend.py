import asyncio
import signal
from pathlib import Path

from lafvin_hat.hardware.audio import find_alsa_card
from lafvin_hat.runtime.audio.backends import LinuxAudioBackend


def _mixer_output(raw_value: int, percent: int, db: str) -> str:
    return f"""
Simple mixer control 'Speaker',0
  Capabilities: pvolume
  Playback channels: Front Left - Front Right
  Limits: Playback 0 - 127
  Mono:
  Front Left: Playback {raw_value} [{percent}%] [{db}]
  Front Right: Playback {raw_value} [{percent}%] [{db}]
"""


def test_find_alsa_card_matches_multiline_description() -> None:
    cards = """
 0 [vc4hdmi0      ]: vc4-hdmi - vc4-hdmi-0
                      vc4-hdmi-0
 1 [vc4hdmi1      ]: vc4-hdmi - vc4-hdmi-1
                      vc4-hdmi-1
 2 [wm8960soundcard]: simple-card - sound
                      wm8960-soundcard
"""

    assert find_alsa_card(cards, "wm8960") == "2"


def test_linux_recording_uses_verified_wm8960_format(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: list[tuple] = []

    class Process:
        returncode = None

    async def create_process(*args, **kwargs):
        captured.append(args)
        return Process()

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        create_process,
    )

    async def scenario() -> None:
        backend = LinuxAudioBackend(card="2")
        await backend.start_recording(
            tmp_path / "recording.wav",
            max_duration_sec=10,
        )

    asyncio.run(scenario())

    command = captured[0]
    assert command[:3] == ("arecord", "-D", "hw:2,0")
    assert ("-f", "S32_LE") == (
        command[command.index("-f")],
        command[command.index("-f") + 1],
    )
    assert command[command.index("-r") + 1] == "16000"
    assert command[command.index("-c") + 1] == "2"


def test_runtime_interrupt_is_a_successful_recording_stop() -> None:
    class Process:
        def __init__(self) -> None:
            self.returncode = None
            self.stderr = None
            self.signal = None

        def send_signal(self, value: int) -> None:
            self.signal = value

        async def wait(self) -> int:
            self.returncode = 1
            return self.returncode

    async def scenario() -> None:
        backend = LinuxAudioBackend(card="2")
        process = Process()

        await backend.stop_recording(process)  # type: ignore[arg-type]

        assert process.signal == signal.SIGINT
        assert process.returncode == 1
        assert backend.last_error is None

    asyncio.run(scenario())


def test_unexpected_recording_exit_preserves_error() -> None:
    class Stderr:
        async def read(self) -> bytes:
            return b"arecord: pcm_open: device is busy"

    class Process:
        returncode = 1
        stderr = Stderr()

        async def wait(self) -> int:
            return self.returncode

    async def scenario() -> None:
        backend = LinuxAudioBackend(card="2")

        await backend.stop_recording(Process())  # type: ignore[arg-type]

        assert backend.last_error == "arecord: pcm_open: device is busy"

    asyncio.run(scenario())


def test_linux_backend_syncs_measured_curve_on_start_and_write(
    monkeypatch,
) -> None:
    commands: list[tuple[str, ...]] = []
    readbacks = [
        _mixer_output(117, 92, "-4.00dB"),
        _mixer_output(109, 86, "-12.00dB"),
    ]

    class Process:
        def __init__(self, stdout: str = "") -> None:
            self.returncode: int | None = None
            self._stdout = stdout.encode("utf-8")

        async def communicate(self) -> tuple[bytes, bytes]:
            self.returncode = 0
            return self._stdout, b""

    async def create_process(*args, **kwargs):
        del kwargs
        command = tuple(str(value) for value in args)
        commands.append(command)
        if command[3] == "sget":
            return Process(readbacks.pop(0))
        return Process()

    monkeypatch.setattr(
        "lafvin_hat.runtime.audio.backends.shutil.which",
        lambda command: f"/usr/bin/{command}",
    )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    async def scenario() -> None:
        backend = LinuxAudioBackend(card="2")

        await backend.start()
        assert await backend.get_volume() == 70
        assert backend.mixer_snapshot() is not None
        assert backend.mixer_snapshot()["raw_value"] == 117  # type: ignore[index]
        assert backend.mixer_snapshot()["expected_raw"] == 117  # type: ignore[index]

        assert await backend.set_volume(40) == 40
        assert commands[1] == ("amixer", "-c", "2", "sset", "Speaker", "109")
        assert backend.mixer_snapshot()["raw_value"] == 109  # type: ignore[index]
        assert backend.mixer_snapshot()["expected_raw"] == 109  # type: ignore[index]

    asyncio.run(scenario())
