from __future__ import annotations

import asyncio
import contextlib
import math
import secrets
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

from ..apps import AppManager
from ..events import EventBus, EventSubscription
from ..ipc.protocol import ProtocolError
from .backends import AudioBackend


_SYSTEM_AUDIO_ID = "system.diagnostics"
_VOLUME_FEEDBACK_KIND = "volume"
_VOLUME_FEEDBACK_SEGMENTS = (
    (660, 160),
    (880, 100),
)


class AudioService:
    def __init__(
        self,
        app_manager: AppManager,
        event_bus: EventBus,
        backend: AudioBackend,
        *,
        temp_root: Path | None = None,
    ) -> None:
        self._app_manager = app_manager
        self._event_bus = event_bus
        self._backend = backend
        self._temp_root = temp_root
        self._recording: dict[str, Any] | None = None
        self._playback: dict[str, Any] | None = None
        self._owned_files: dict[Path, str] = {}
        self._metrics: dict[str, int | None] = {
            "recording_count": 0,
            "playback_count": 0,
            "interrupted_recording_count": 0,
            "interrupted_playback_count": 0,
            "last_recording_duration_ms": None,
            "last_playback_duration_ms": None,
        }
        self._lock = asyncio.Lock()
        self._subscription: EventSubscription | None = None
        self._event_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._backend.start()
        self._subscription = self._event_bus.subscribe(
            event_names={
                "app.foreground_revoked",
                "app.stopped",
                "app.crashed",
            }
        )
        self._event_task = asyncio.create_task(
            self._watch_lifecycle(),
            name="audio-lifecycle-watch",
        )

    async def stop(self) -> None:
        if self._event_task is not None:
            self._event_task.cancel()
            await asyncio.gather(self._event_task, return_exceptions=True)
            self._event_task = None
        if self._subscription is not None:
            self._event_bus.unsubscribe(self._subscription)
            self._subscription = None
        async with self._lock:
            await self._stop_recording_locked()
            await self._stop_playback_locked()
        await self._backend.stop()

    async def start_recording(
        self,
        app_id: str,
        session_token: str,
        max_duration_sec: int,
    ) -> dict[str, Any]:
        await self._app_manager.authorize(
            app_id,
            session_token,
            permission="microphone",
            require_foreground=True,
        )
        if (
            isinstance(max_duration_sec, bool)
            or not isinstance(max_duration_sec, int)
            or not 1 <= max_duration_sec <= 60
        ):
            raise ProtocolError(
                "INVALID_REQUEST",
                "max_duration_sec must be between 1 and 60",
            )
        async with self._lock:
            if self._recording is not None:
                raise ProtocolError(
                    "AUDIO_BUSY",
                    "A recording session is already active",
                )
            await self._stop_playback_locked()
            token = secrets.token_urlsafe(24)
            root = self._ensure_temp_root() / app_id
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"recording-{secrets.token_hex(8)}.wav"
            handle = await self._backend.start_recording(
                path,
                max_duration_sec=max_duration_sec,
            )
            self._recording = {
                "app_id": app_id,
                "token": token,
                "path": path,
                "handle": handle,
                "started_at": time.monotonic(),
            }
            return {
                "recording_session": token,
                "format": "wav",
                "max_duration_sec": max_duration_sec,
            }

    async def stop_recording(
        self,
        app_id: str,
        session_token: str,
        recording_session: str,
    ) -> dict[str, Any]:
        await self._app_manager.authorize(
            app_id,
            session_token,
            permission="microphone",
        )
        async with self._lock:
            recording = self._require_recording(app_id, recording_session)
            await self._backend.stop_recording(recording["handle"])
            path = recording["path"]
            duration_ms = int(
                (time.monotonic() - recording["started_at"]) * 1000
            )
            self._recording = None
            self._increment_metric("recording_count")
            self._metrics["last_recording_duration_ms"] = duration_ms
            backend_error = getattr(self._backend, "last_error", None)
            if backend_error:
                raise ProtocolError(
                    "AUDIO_FAILED",
                    f"Recording failed: {backend_error}",
                )
            if not path.is_file() or path.stat().st_size <= 44:
                raise ProtocolError(
                    "AUDIO_FAILED",
                    "Recording did not produce usable WAV audio",
                )
            self._owned_files[path.resolve()] = app_id
            return {
                "path": str(path),
                "format": "wav",
                "duration_ms": duration_ms,
                "size_bytes": path.stat().st_size,
            }

    async def play_file(
        self,
        app_id: str,
        session_token: str,
        value: str,
    ) -> dict[str, Any]:
        app_root = await self._app_manager.authorize(
            app_id,
            session_token,
            permission="speaker",
            require_foreground=True,
        )
        path = self._resolve_playback_path(app_id, app_root, value)
        return await self._play_path(path, app_id=app_id)

    async def play_feedback_tone(
        self,
        app_id: str,
        session_token: str,
        *,
        kind: str,
    ) -> dict[str, Any]:
        """Play a fixed Runtime-generated feedback sound for a foreground App."""

        await self._app_manager.authorize(
            app_id,
            session_token,
            permission="speaker",
            require_foreground=True,
        )
        if kind != _VOLUME_FEEDBACK_KIND:
            raise ProtocolError(
                "INVALID_REQUEST",
                f"Unsupported audio feedback kind: {kind}",
            )

        root = self._ensure_temp_root() / app_id
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"feedback-{kind}-{secrets.token_hex(8)}.wav"
        await asyncio.to_thread(
            _write_tone_sequence_wav,
            path,
            segments=_VOLUME_FEEDBACK_SEGMENTS,
            gap_ms=35,
        )
        try:
            result = await self._play_path(path, app_id=app_id)
        finally:
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
        return {**result, "kind": kind}

    async def start_system_recording(
        self,
        *,
        max_duration_sec: int,
    ) -> dict[str, Any]:
        if (
            isinstance(max_duration_sec, bool)
            or not isinstance(max_duration_sec, int)
            or not 1 <= max_duration_sec <= 60
        ):
            raise ProtocolError(
                "INVALID_REQUEST",
                "max_duration_sec must be between 1 and 60",
            )
        async with self._lock:
            if self._recording is not None:
                await self._stop_recording_locked()
            await self._stop_playback_locked()
            token = secrets.token_urlsafe(24)
            root = self._ensure_temp_root() / _SYSTEM_AUDIO_ID
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"recording-{secrets.token_hex(8)}.wav"
            handle = await self._backend.start_recording(
                path,
                max_duration_sec=max_duration_sec,
            )
            self._recording = {
                "app_id": _SYSTEM_AUDIO_ID,
                "token": token,
                "path": path,
                "handle": handle,
                "started_at": time.monotonic(),
            }
            return {
                "recording_session": token,
                "format": "wav",
                "max_duration_sec": max_duration_sec,
            }

    async def stop_system_recording(
        self,
        recording_session: str,
    ) -> dict[str, Any]:
        async with self._lock:
            recording = self._require_recording(
                _SYSTEM_AUDIO_ID,
                recording_session,
            )
            await self._backend.stop_recording(recording["handle"])
            path = recording["path"]
            duration_ms = int(
                (time.monotonic() - recording["started_at"]) * 1000
            )
            self._recording = None
            self._increment_metric("recording_count")
            self._metrics["last_recording_duration_ms"] = duration_ms
            backend_error = getattr(self._backend, "last_error", None)
            if backend_error:
                raise ProtocolError(
                    "AUDIO_FAILED",
                    f"Recording failed: {backend_error}",
                )
            if not path.is_file() or path.stat().st_size <= 44:
                raise ProtocolError(
                    "AUDIO_FAILED",
                    "Recording did not produce usable WAV audio",
                )
            self._owned_files[path.resolve()] = _SYSTEM_AUDIO_ID
            return {
                "path": str(path),
                "format": "wav",
                "duration_ms": duration_ms,
                "size_bytes": path.stat().st_size,
            }

    async def play_system_file(self, value: str | Path) -> dict[str, Any]:
        path = Path(value).resolve()
        if path.suffix.lower() != ".wav" or not path.is_file():
            raise ProtocolError(
                "INVALID_REQUEST",
                "Audio playback requires an existing WAV file",
            )
        return await self._play_path(path, app_id=_SYSTEM_AUDIO_ID)

    async def play_system_tone(
        self,
        *,
        frequency_hz: int = 880,
        duration_ms: int = 700,
    ) -> dict[str, Any]:
        root = self._ensure_temp_root() / _SYSTEM_AUDIO_ID
        root.mkdir(parents=True, exist_ok=True)
        path = root / "speaker-test.wav"
        await asyncio.to_thread(
            _write_tone_wav,
            path,
            frequency_hz=frequency_hz,
            duration_ms=duration_ms,
        )
        return await self.play_system_file(path)

    async def _play_path(
        self,
        path: Path,
        *,
        app_id: str,
    ) -> dict[str, Any]:
        started_at = time.monotonic()
        async with self._lock:
            await self._stop_playback_locked()
            token = secrets.token_urlsafe(24)
            handle = await self._backend.play(path)
            self._playback = {
                "app_id": app_id,
                "token": token,
                "path": path,
                "handle": handle,
            }
        return_code = await self._backend.wait_playback(handle)
        async with self._lock:
            if self._playback and self._playback["token"] == token:
                self._playback = None
            self._increment_metric("playback_count")
            self._metrics["last_playback_duration_ms"] = int(
                (time.monotonic() - started_at) * 1000
            )
        if return_code != 0:
            detail = getattr(self._backend, "last_error", None)
            message = "Audio playback failed"
            if detail:
                message = f"{message}: {detail}"
            raise ProtocolError("AUDIO_FAILED", message)
        return {"path": str(path), "completed": True}

    async def stop_for_app(self, app_id: str) -> None:
        async with self._lock:
            if self._recording and self._recording["app_id"] == app_id:
                await self._stop_recording_locked()
            if self._playback and self._playback["app_id"] == app_id:
                await self._stop_playback_locked()

    async def stop_playback(
        self,
        app_id: str,
        session_token: str,
    ) -> dict[str, Any]:
        await self._app_manager.authorize(
            app_id,
            session_token,
            permission="speaker",
        )
        async with self._lock:
            if self._playback and self._playback["app_id"] == app_id:
                await self._stop_playback_locked()
        return self.snapshot()

    async def get_volume(
        self,
        app_id: str,
        session_token: str,
    ) -> dict[str, Any]:
        await self._app_manager.authorize(
            app_id,
            session_token,
            permission="speaker",
        )
        return {"value": await self._backend.get_volume()}

    async def get_system_volume(self) -> int:
        return await self._backend.get_volume()

    async def set_volume(
        self,
        app_id: str,
        session_token: str,
        value: int,
    ) -> dict[str, Any]:
        await self._app_manager.authorize(
            app_id,
            session_token,
            permission="speaker",
        )
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProtocolError("INVALID_REQUEST", "value must be an integer")
        return {"value": await self._backend.set_volume(value)}

    async def set_system_volume(self, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProtocolError("INVALID_REQUEST", "value must be an integer")
        return await self._backend.set_volume(value)

    def snapshot(self) -> dict[str, Any]:
        profile_snapshot = getattr(self._backend, "profile_snapshot", None)
        profile = profile_snapshot() if callable(profile_snapshot) else None
        mixer_snapshot = getattr(self._backend, "mixer_snapshot", None)
        mixer = mixer_snapshot() if callable(mixer_snapshot) else None
        return {
            "backend": self._backend.name,
            "profile": profile,
            "mixer": mixer,
            "card": getattr(self._backend, "card", None),
            "capture_device": getattr(
                self._backend,
                "capture_device",
                None,
            ),
            "playback_device": getattr(
                self._backend,
                "playback_device",
                None,
            ),
            "recording_format": getattr(
                self._backend,
                "recording_format",
                "fake-wav",
            ),
            "last_error": getattr(self._backend, "last_error", None),
            "volume": getattr(self._backend, "volume", None),
            "recording_app_id": (
                self._recording["app_id"] if self._recording else None
            ),
            "playing_app_id": (
                self._playback["app_id"] if self._playback else None
            ),
            "metrics": dict(self._metrics),
        }

    def _increment_metric(self, name: str) -> None:
        self._metrics[name] = int(self._metrics[name] or 0) + 1

    def _require_recording(
        self,
        app_id: str,
        token: str,
    ) -> dict[str, Any]:
        if (
            self._recording is None
            or self._recording["app_id"] != app_id
            or not secrets.compare_digest(self._recording["token"], token)
        ):
            raise ProtocolError(
                "INVALID_AUDIO_SESSION",
                "Recording session is invalid or expired",
            )
        return self._recording

    async def _stop_recording_locked(self) -> None:
        recording, self._recording = self._recording, None
        if recording is not None:
            self._increment_metric("interrupted_recording_count")
            with contextlib.suppress(Exception):
                await self._backend.stop_recording(recording["handle"])

    async def _stop_playback_locked(self) -> None:
        playback, self._playback = self._playback, None
        if playback is not None:
            self._increment_metric("interrupted_playback_count")
            with contextlib.suppress(Exception):
                await self._backend.stop_playback(playback["handle"])

    def _resolve_playback_path(
        self,
        app_id: str,
        app_root: Path,
        value: str,
    ) -> Path:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = app_root / candidate
        candidate = candidate.resolve()
        root = app_root.resolve()
        owned = self._owned_files.get(candidate) == app_id
        if not owned and candidate != root and root not in candidate.parents:
            raise ProtocolError(
                "PERMISSION_DENIED",
                "Audio file is outside the app directory",
            )
        if candidate.suffix.lower() != ".wav" or not candidate.is_file():
            raise ProtocolError(
                "INVALID_REQUEST",
                "Audio playback requires an existing WAV file",
            )
        return candidate

    def _ensure_temp_root(self) -> Path:
        root = self._temp_root
        if root is None:
            root = Path(tempfile.gettempdir()) / "lafvin-hat-audio"
        root.mkdir(parents=True, exist_ok=True)
        return root

    async def _watch_lifecycle(self) -> None:
        assert self._subscription is not None
        while True:
            event = await self._subscription.queue.get()
            app_id = event["payload"].get("app_id")
            if isinstance(app_id, str):
                await self.stop_for_app(app_id)


def _write_tone_wav(
    path: Path,
    *,
    frequency_hz: int,
    duration_ms: int,
) -> None:
    _write_tone_sequence_wav(
        path,
        segments=((frequency_hz, duration_ms),),
        gap_ms=0,
    )


def _write_tone_sequence_wav(
    path: Path,
    *,
    segments: tuple[tuple[int, int], ...],
    gap_ms: int,
) -> None:
    sample_rate = 16_000
    amplitude = int(32767 * 0.35)
    frames = bytearray()
    gap_frames = max(0, int(sample_rate * gap_ms / 1000))

    for segment_index, (frequency_hz, duration_ms) in enumerate(segments):
        sample_count = max(
            1,
            int(sample_rate * max(1, duration_ms) / 1000),
        )
        fade_frames = min(sample_count // 2, sample_rate // 125)
        for index in range(sample_count):
            envelope = 1.0
            if fade_frames:
                if index < fade_frames:
                    envelope = index / fade_frames
                elif index >= sample_count - fade_frames:
                    envelope = (sample_count - index - 1) / fade_frames
            t = index / sample_rate
            value = int(
                math.sin(2 * math.pi * frequency_hz * t)
                * amplitude
                * envelope
            )
            frames.extend(value.to_bytes(2, byteorder="little", signed=True))
        if segment_index < len(segments) - 1 and gap_frames:
            frames.extend(b"\x00\x00" * gap_frames)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(bytes(frames))
