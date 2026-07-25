from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import wave
from pathlib import Path
from typing import Any, Protocol

from lafvin_hat.hardware.audio import (
    Wm8960AudioProfile,
    Wm8960MixerState,
)


class AudioBackend(Protocol):
    name: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def start_recording(
        self,
        path: Path,
        *,
        max_duration_sec: int,
    ) -> Any: ...

    async def stop_recording(self, handle: Any) -> None: ...

    async def play(self, path: Path) -> Any: ...

    async def wait_playback(self, handle: Any) -> int: ...

    async def stop_playback(self, handle: Any) -> None: ...

    async def get_volume(self) -> int: ...

    async def set_volume(self, value: int) -> int: ...


class LinuxAudioProfile(Protocol):
    """Board-specific ALSA details consumed by the generic Linux backend."""

    name: str
    recording_format: str

    def find_card(self) -> str: ...

    def capture_device(self, card: str) -> str: ...

    def playback_device(self, card: str) -> str: ...

    def recording_command(
        self,
        device: str,
        path: Path,
        *,
        max_duration_sec: int,
    ) -> tuple[str, ...]: ...

    def volume_command(
        self,
        card: str,
        value: int,
        *,
        raw_min: int = 0,
        raw_max: int = 127,
    ) -> tuple[str, ...]: ...

    def volume_read_command(self, card: str) -> tuple[str, ...]: ...

    def parse_mixer_state(
        self,
        value: str,
        *,
        card: str,
    ) -> Wm8960MixerState: ...

    def logical_volume_to_raw(
        self,
        value: int,
        *,
        raw_min: int = 0,
        raw_max: int = 127,
    ) -> int: ...

    def raw_to_logical_volume(
        self,
        value: int,
        *,
        raw_min: int,
        raw_max: int,
    ) -> int: ...

    def snapshot(
        self,
        *,
        card: str | None,
        capture_device: str | None,
        playback_device: str | None,
    ) -> dict[str, str | None]: ...


class FakeAudioBackend:
    name = "fake"

    def __init__(self, *, playback_delay: float = 0.01) -> None:
        self.playback_delay = playback_delay
        self.volume = 70
        self.played_paths: list[Path] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def start_recording(
        self,
        path: Path,
        *,
        max_duration_sec: int,
    ) -> dict[str, Any]:
        return {"path": path, "max_duration_sec": max_duration_sec}

    async def stop_recording(self, handle: dict[str, Any]) -> None:
        path = handle["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(bytes(3200))

    async def play(self, path: Path) -> asyncio.Task[int]:
        self.played_paths.append(path)

        async def finish() -> int:
            await asyncio.sleep(self.playback_delay)
            return 0

        return asyncio.create_task(finish())

    async def wait_playback(self, handle: asyncio.Task[int]) -> int:
        try:
            return await handle
        except asyncio.CancelledError:
            return -1

    async def stop_playback(self, handle: asyncio.Task[int]) -> None:
        handle.cancel()
        await asyncio.gather(handle, return_exceptions=True)

    async def get_volume(self) -> int:
        return self.volume

    async def set_volume(self, value: int) -> int:
        self.volume = max(0, min(100, int(value)))
        return self.volume


class LinuxAudioBackend:
    name = "linux-alsa"

    def __init__(
        self,
        *,
        card: str | None = None,
        profile: LinuxAudioProfile | None = None,
    ) -> None:
        self.card = card or os.getenv("LAFVIN_AUDIO_CARD")
        self.profile = profile or Wm8960AudioProfile()
        self.volume = 70
        self.last_error: str | None = None
        self.capture_device: str | None = None
        self.playback_device: str | None = None
        self._mixer_state: Wm8960MixerState | None = None

    @property
    def recording_format(self) -> str:
        return self.profile.recording_format

    async def start(self) -> None:
        for command in ("arecord", "aplay", "amixer"):
            if shutil.which(command) is None:
                raise RuntimeError(f"Required audio command not found: {command}")
        if self.card is None:
            self.card = await asyncio.to_thread(self.profile.find_card)
        self.capture_device = self.profile.capture_device(self.card)
        self.playback_device = self.profile.playback_device(self.card)
        await self._sync_volume_from_mixer()

    async def stop(self) -> None:
        return None

    async def start_recording(
        self,
        path: Path,
        *,
        max_duration_sec: int,
    ) -> asyncio.subprocess.Process:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.last_error = None
        return await asyncio.create_subprocess_exec(
            *self.profile.recording_command(
                self.capture_device or self.profile.capture_device(str(self.card)),
                path,
                max_duration_sec=max_duration_sec,
            ),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

    async def stop_recording(
        self,
        handle: asyncio.subprocess.Process,
    ) -> None:
        interrupted_by_runtime = handle.returncode is None
        if handle.returncode is None:
            if hasattr(signal, "SIGINT"):
                handle.send_signal(signal.SIGINT)
            else:
                handle.terminate()
        try:
            await asyncio.wait_for(handle.wait(), timeout=2)
        except asyncio.TimeoutError:
            handle.kill()
            await handle.wait()
        if not interrupted_by_runtime and handle.returncode != 0:
            self.last_error = await self._read_stderr(handle)

    async def play(self, path: Path) -> asyncio.subprocess.Process:
        self.last_error = None
        return await asyncio.create_subprocess_exec(
            "aplay",
            "-D",
            self.playback_device or f"plughw:{self.card},0",
            str(path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

    async def wait_playback(
        self,
        handle: asyncio.subprocess.Process,
    ) -> int:
        return_code = await handle.wait()
        if return_code != 0:
            self.last_error = await self._read_stderr(handle)
        return return_code

    async def stop_playback(
        self,
        handle: asyncio.subprocess.Process,
    ) -> None:
        if handle.returncode is None:
            handle.terminate()
            try:
                await asyncio.wait_for(handle.wait(), timeout=1)
            except asyncio.TimeoutError:
                handle.kill()
                await handle.wait()

    async def get_volume(self) -> int:
        return self.volume

    async def set_volume(self, value: int) -> int:
        logical_value = max(0, min(100, int(value)))
        state = self._mixer_state or await self._sync_volume_from_mixer()
        command = self.profile.volume_command(
            str(self.card),
            logical_value,
            raw_min=state.raw_min,
            raw_max=state.raw_max,
        )
        await self._run_mixer_command(command, action="set volume")
        await self._sync_volume_from_mixer()
        return self.volume

    def profile_snapshot(self) -> dict[str, Any]:
        return self.profile.snapshot(
            card=self.card,
            capture_device=self.capture_device,
            playback_device=self.playback_device,
        )

    def mixer_snapshot(self) -> dict[str, Any] | None:
        """Return the most recent Runtime-owned Speaker readback."""

        state = self._mixer_state
        if state is None:
            return None
        primary = state.primary
        return {
            "control": state.control,
            "raw_min": state.raw_min,
            "raw_max": state.raw_max,
            "raw_value": primary.raw_value,
            "alsa_percent": primary.percent,
            "decibels": primary.db,
            "expected_raw": self.profile.logical_volume_to_raw(
                self.volume,
                raw_min=state.raw_min,
                raw_max=state.raw_max,
            ),
            "channels": [
                {
                    "name": channel.name,
                    "raw_value": channel.raw_value,
                    "alsa_percent": channel.percent,
                    "decibels": channel.db,
                }
                for channel in state.channels
            ],
        }

    def _find_wm8960_card(self) -> str:
        """Compatibility helper retained for direct backend callers."""

        return self.profile.find_card()

    async def _read_stderr(
        self,
        handle: asyncio.subprocess.Process,
    ) -> str:
        if handle.stderr is None:
            return f"ALSA process exited with code {handle.returncode}"
        value = await handle.stderr.read()
        text = value.decode("utf-8", errors="replace").strip()
        return text[-1000:] or f"ALSA process exited with code {handle.returncode}"

    async def _sync_volume_from_mixer(self) -> Wm8960MixerState:
        """Read Speaker state and make logical volume match real hardware."""

        try:
            output = await self._run_mixer_command(
                self.profile.volume_read_command(str(self.card)),
                action="read volume",
            )
            state = self.profile.parse_mixer_state(
                output,
                card=str(self.card),
            )
            self._mixer_state = state
            self.volume = self.profile.raw_to_logical_volume(
                state.primary.raw_value,
                raw_min=state.raw_min,
                raw_max=state.raw_max,
            )
            self.last_error = None
            return state
        except Exception as exc:
            self.last_error = str(exc)
            raise

    async def _run_mixer_command(
        self,
        command: tuple[str, ...],
        *,
        action: str,
    ) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Required audio command not found: amixer") from exc
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=5,
            )
        except asyncio.TimeoutError as exc:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with contextlib.suppress(Exception):
                await process.wait()
            raise RuntimeError(f"amixer did not finish while attempting to {action}") from exc
        if process.returncode != 0:
            detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"amixer failed to {action}: "
                f"{detail or f'exit code {process.returncode}'}"
            )
        return stdout.decode("utf-8", errors="replace")
