from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import RuntimeClient, RuntimeClientError


@dataclass(slots=True)
class RecordingSession:
    _audio: "AudioClient"
    recording_session: str
    max_duration_sec: int
    _stopped: bool = False

    async def stop(self) -> dict[str, Any]:
        if self._stopped:
            raise RuntimeError("Recording session is already stopped")
        result = await self._audio._request(
            "audio.record.stop",
            {"recording_session": self.recording_session},
        )
        self._stopped = True
        return result


class AudioClient:
    def __init__(
        self,
        client: RuntimeClient,
        app_id: str,
        session_token: str,
    ) -> None:
        self._client = client
        self._session = {
            "app_id": app_id,
            "session_token": session_token,
        }
        self._recording: RecordingSession | None = None

    async def start_recording(
        self,
        *,
        max_duration_sec: int = 30,
    ) -> RecordingSession:
        result = await self._request(
            "audio.record.start",
            {"max_duration_sec": max_duration_sec},
        )
        recording = RecordingSession(
            self,
            result["recording_session"],
            result["max_duration_sec"],
        )
        self._recording = recording
        return recording

    async def play_file(self, path: str | Path) -> dict[str, Any]:
        return await self._request("audio.play", {"path": str(path)})

    async def play_feedback_tone(self, kind: str) -> dict[str, Any]:
        """Play a fixed Runtime-generated feedback sound.

        The Runtime currently supports the ``volume`` kind. This API keeps
        generated system feedback inside Runtime audio ownership rather than
        asking Apps to invoke a platform player directly.
        """

        return await self._request("audio.feedback.play", {"kind": kind})

    async def stop(self) -> dict[str, Any]:
        return await self._request("audio.stop")

    async def get_volume(self) -> int:
        result = await self._request("audio.volume.get")
        return int(result["value"])

    async def set_volume(self, value: int) -> int:
        result = await self._request(
            "audio.volume.set",
            {"value": value},
        )
        return int(result["value"])

    async def close(self) -> None:
        if self._recording is not None and not self._recording._stopped:
            try:
                await self._recording.stop()
            except RuntimeClientError as exc:
                if exc.code not in {
                    "INVALID_AUDIO_SESSION",
                    "INVALID_SESSION",
                }:
                    raise
        try:
            await self.stop()
        except RuntimeClientError as exc:
            if exc.code != "INVALID_SESSION":
                raise

    async def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._client.request(
            method,
            {**self._session, **(params or {})},
        )
