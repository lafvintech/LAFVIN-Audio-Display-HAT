from __future__ import annotations

import mmap
from pathlib import Path
from typing import Any

from .client import RuntimeClient, RuntimeClientError


class RawFrameSession:
    def __init__(
        self,
        client: RuntimeClient,
        app_id: str,
        session_token: str,
        descriptor: dict[str, Any],
    ) -> None:
        self._client = client
        self._session = {
            "app_id": app_id,
            "session_token": session_token,
        }
        self.width = int(descriptor["width"])
        self.height = int(descriptor["height"])
        self.stride = int(descriptor["stride"])
        self.pixel_format = str(descriptor["pixel_format"])
        self.frame_session = str(descriptor["frame_session"])
        self.next_sequence = int(descriptor["next_sequence"])
        self._path = Path(descriptor["buffer_path"])
        self._file = self._path.open("r+b")
        self._buffer = mmap.mmap(
            self._file.fileno(),
            self.stride * self.height,
            access=mmap.ACCESS_WRITE,
        )
        self._closed = False

    @property
    def size(self) -> int:
        return self.stride * self.height

    @property
    def closed(self) -> bool:
        return self._closed

    def write(self, frame: bytes | bytearray | memoryview) -> None:
        self._ensure_open()
        if len(frame) != self.size:
            raise ValueError(f"Raw Frame must contain {self.size} bytes")
        self._buffer.seek(0)
        self._buffer.write(frame)

    def clear(self, value: int = 0) -> None:
        self._ensure_open()
        if not 0 <= value <= 255:
            raise ValueError("value must be between 0 and 255")
        self._buffer.seek(0)
        self._buffer.write(bytes([value]) * self.size)

    async def commit(
        self,
        *,
        dirty_rects: list[dict[str, int]] | None = None,
        input_timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        self._ensure_open()
        self._buffer.flush()
        params: dict[str, Any] = {
            **self._session,
            "frame_session": self.frame_session,
            "sequence": self.next_sequence,
        }
        if dirty_rects is not None:
            params["dirty_rects"] = dirty_rects
        if input_timestamp_ms is not None:
            params["input_timestamp_ms"] = input_timestamp_ms
        result = await self._client.request("frame.commit", params)
        self.next_sequence = int(result["next_sequence"])
        return result

    async def close(self) -> None:
        if self._closed:
            return
        self._buffer.close()
        self._file.close()
        self._closed = True
        try:
            await self._client.request(
                "frame.release",
                {
                    **self._session,
                    "frame_session": self.frame_session,
                },
            )
        except RuntimeClientError as exc:
            if exc.code not in {
                "INVALID_FRAME_SESSION",
                "INVALID_SESSION",
                "APP_NOT_FOREGROUND",
            }:
                raise

    async def __aenter__(self) -> "RawFrameSession":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Raw Frame session is closed")


class FrameClient:
    def __init__(
        self,
        client: RuntimeClient,
        app_id: str,
        session_token: str,
    ) -> None:
        self._client = client
        self._app_id = app_id
        self._session_token = session_token
        self._active: RawFrameSession | None = None

    async def acquire(self) -> RawFrameSession:
        if self._active is not None and not self._active.closed:
            raise RuntimeError("Raw Frame session is already acquired")
        descriptor = await self._client.request(
            "frame.acquire",
            {
                "app_id": self._app_id,
                "session_token": self._session_token,
            },
        )
        self._active = RawFrameSession(
            self._client,
            self._app_id,
            self._session_token,
            descriptor,
        )
        return self._active

    async def close(self) -> None:
        if self._active is not None:
            await self._active.close()
            self._active = None
