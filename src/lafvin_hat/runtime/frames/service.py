from __future__ import annotations

import asyncio
import contextlib
import os
import secrets
import tempfile
import time
from collections import deque
from pathlib import Path
from typing import Any

from ..apps import AppManager
from ..backends import DeviceBackend
from ..events import EventBus, EventSubscription
from ..ipc.protocol import ProtocolError


class FrameService:
    pixel_format = "RGB565_BE"

    def __init__(
        self,
        app_manager: AppManager,
        backend: DeviceBackend,
        event_bus: EventBus,
        *,
        buffer_root: Path | None = None,
    ) -> None:
        self._app_manager = app_manager
        self._backend = backend
        self._event_bus = event_bus
        self._buffer_root = buffer_root
        self._owner_app_id: str | None = None
        self._frame_session: str | None = None
        self._buffer_path: Path | None = None
        self._next_sequence = 1
        self._commit_times: deque[float] = deque()
        self._commit_count = 0
        self._last_commit_ms: float | None = None
        self._last_input_latency_ms: float | None = None
        self._lock = asyncio.Lock()
        self._subscription: EventSubscription | None = None
        self._event_task: asyncio.Task[None] | None = None
        self._stale_paths: set[Path] = set()

    @property
    def frame_bytes(self) -> int:
        return self._backend.display_width * self._backend.display_height * 2

    async def start(self) -> None:
        self._subscription = self._event_bus.subscribe(
            event_names={
                "app.foreground_revoked",
                "app.stopped",
                "app.crashed",
            }
        )
        self._event_task = asyncio.create_task(
            self._watch_lifecycle(),
            name="frame-lifecycle-watch",
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
            self._invalidate_locked()
            for path in tuple(self._stale_paths):
                self._unlink(path)

    async def acquire(
        self,
        app_id: str,
        session_token: str,
    ) -> dict[str, Any]:
        await self._app_manager.authorize(
            app_id,
            session_token,
            permission="display.raw_frame",
            require_foreground=True,
            ui_mode="raw_frame",
        )
        async with self._lock:
            if self._owner_app_id is not None:
                if self._owner_app_id == app_id:
                    raise ProtocolError(
                        "FRAME_ALREADY_ACQUIRED",
                        "App already owns a Raw Frame session",
                    )
                raise ProtocolError(
                    "FRAME_BUSY",
                    f"Raw Frame is owned by {self._owner_app_id}",
                )
            root = self._ensure_buffer_root()
            frame_session = secrets.token_urlsafe(32)
            fd, raw_path = tempfile.mkstemp(
                prefix="frame-",
                suffix=".rgb565",
                dir=root,
            )
            try:
                with contextlib.suppress(AttributeError, OSError):
                    os.fchmod(fd, 0o600)
                os.ftruncate(fd, self.frame_bytes)
            finally:
                os.close(fd)
            self._owner_app_id = app_id
            self._frame_session = frame_session
            self._buffer_path = Path(raw_path)
            self._next_sequence = 1
            self._commit_times.clear()
            self._commit_count = 0
            self._last_commit_ms = None
            self._last_input_latency_ms = None
            return self._session_snapshot()

    async def commit(
        self,
        app_id: str,
        session_token: str,
        frame_session: str,
        sequence: int,
        dirty_rects: Any,
        input_timestamp_ms: Any = None,
    ) -> dict[str, Any]:
        await self._app_manager.authorize(
            app_id,
            session_token,
            permission="display.raw_frame",
            require_foreground=True,
            ui_mode="raw_frame",
        )
        async with self._lock:
            self._require_frame_session(app_id, frame_session)
            if isinstance(sequence, bool) or not isinstance(sequence, int):
                raise ProtocolError(
                    "INVALID_REQUEST",
                    "sequence must be an integer",
                )
            if sequence != self._next_sequence:
                raise ProtocolError(
                    "INVALID_FRAME_SEQUENCE",
                    f"Expected sequence {self._next_sequence}, got {sequence}",
                )
            rects = self._validate_dirty_rects(dirty_rects)
            input_latency_ms = self._input_latency(input_timestamp_ms)
            assert self._buffer_path is not None
            started = time.perf_counter()
            try:
                frame = await asyncio.to_thread(self._buffer_path.read_bytes)
            except OSError as exc:
                raise ProtocolError(
                    "FRAME_BUFFER_UNAVAILABLE",
                    f"Failed to read Raw Frame buffer: {exc}",
                ) from exc
            if len(frame) != self.frame_bytes:
                raise ProtocolError(
                    "INVALID_FRAME_BUFFER",
                    f"Raw Frame buffer must contain {self.frame_bytes} bytes",
                )
            await self._backend.present_frame(
                frame,
                width=self._backend.display_width,
                height=self._backend.display_height,
            )
            await self._backend.set_display_mode("raw_frame")
            now = time.monotonic()
            self._commit_times.append(now)
            while self._commit_times and now - self._commit_times[0] > 1.0:
                self._commit_times.popleft()
            self._commit_count += 1
            self._last_commit_ms = (time.perf_counter() - started) * 1000
            if input_latency_ms is not None:
                self._last_input_latency_ms = input_latency_ms
            self._next_sequence += 1
            return {
                "sequence": sequence,
                "next_sequence": self._next_sequence,
                "dirty_rects": rects,
                "metrics": self._metrics(),
            }

    async def release(
        self,
        app_id: str,
        session_token: str,
        frame_session: str,
    ) -> dict[str, Any]:
        await self._app_manager.authorize(
            app_id,
            session_token,
            permission="display.raw_frame",
            ui_mode="raw_frame",
        )
        async with self._lock:
            self._require_frame_session(app_id, frame_session)
            self._invalidate_locked()
            return self.snapshot()

    async def invalidate_for_app(
        self,
        app_id: str,
    ) -> None:
        async with self._lock:
            if self._owner_app_id == app_id:
                self._invalidate_locked()

    def snapshot(self) -> dict[str, Any]:
        return {
            "owner_app_id": self._owner_app_id,
            "active": self._frame_session is not None,
            "next_sequence": (
                self._next_sequence if self._frame_session is not None else None
            ),
            "pixel_format": self.pixel_format,
            "width": self._backend.display_width,
            "height": self._backend.display_height,
            "stride": self._backend.display_width * 2,
            "metrics": self._metrics(),
        }

    def _session_snapshot(self) -> dict[str, Any]:
        assert self._buffer_path is not None
        assert self._frame_session is not None
        return {
            **self.snapshot(),
            "buffer_path": str(self._buffer_path),
            "frame_session": self._frame_session,
        }

    def _metrics(self) -> dict[str, Any]:
        now = time.monotonic()
        while self._commit_times and now - self._commit_times[0] > 1.0:
            self._commit_times.popleft()
        return {
            "commit_count": self._commit_count,
            "fps": len(self._commit_times),
            "last_commit_ms": self._last_commit_ms,
            "last_input_latency_ms": self._last_input_latency_ms,
        }

    def _input_latency(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProtocolError(
                "INVALID_REQUEST",
                "input_timestamp_ms must be an integer",
            )
        return max(0.0, time.time() * 1000 - value)

    def _require_frame_session(
        self,
        app_id: str,
        frame_session: str,
    ) -> None:
        if (
            self._owner_app_id != app_id
            or self._frame_session is None
            or not secrets.compare_digest(self._frame_session, frame_session)
        ):
            raise ProtocolError(
                "INVALID_FRAME_SESSION",
                "Raw Frame session is invalid or expired",
            )

    def _validate_dirty_rects(self, value: Any) -> list[dict[str, int]]:
        if value is None:
            return [
                {
                    "x": 0,
                    "y": 0,
                    "width": self._backend.display_width,
                    "height": self._backend.display_height,
                }
            ]
        if not isinstance(value, list) or not value:
            raise ProtocolError(
                "INVALID_REQUEST",
                "dirty_rects must be a non-empty array",
            )
        if len(value) > 32:
            raise ProtocolError(
                "INVALID_REQUEST",
                "dirty_rects cannot contain more than 32 rectangles",
            )
        result: list[dict[str, int]] = []
        for index, rect in enumerate(value):
            if not isinstance(rect, dict) or set(rect) != {
                "x",
                "y",
                "width",
                "height",
            }:
                raise ProtocolError(
                    "INVALID_REQUEST",
                    f"dirty_rects.{index} has invalid fields",
                )
            if any(
                isinstance(rect[name], bool) or not isinstance(rect[name], int)
                for name in rect
            ):
                raise ProtocolError(
                    "INVALID_REQUEST",
                    f"dirty_rects.{index} values must be integers",
                )
            x, y = rect["x"], rect["y"]
            width, height = rect["width"], rect["height"]
            if (
                x < 0
                or y < 0
                or width <= 0
                or height <= 0
                or x + width > self._backend.display_width
                or y + height > self._backend.display_height
            ):
                raise ProtocolError(
                    "INVALID_REQUEST",
                    f"dirty_rects.{index} is outside the display",
                )
            result.append(dict(rect))
        return result

    def _invalidate_locked(self) -> None:
        path = self._buffer_path
        self._owner_app_id = None
        self._frame_session = None
        self._buffer_path = None
        self._next_sequence = 1
        if path is not None and not self._unlink(path):
            self._stale_paths.add(path)

    def _ensure_buffer_root(self) -> Path:
        root = self._buffer_root
        if root is None:
            root = Path(tempfile.gettempdir()) / "lafvin-hat" / str(os.getpid())
        root.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(root, 0o700)
        return root

    def _unlink(self, path: Path) -> bool:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
        self._stale_paths.discard(path)
        return True

    async def _watch_lifecycle(self) -> None:
        assert self._subscription is not None
        while True:
            event = await self._subscription.queue.get()
            app_id = event["payload"].get("app_id")
            if isinstance(app_id, str):
                await self.invalidate_for_app(app_id)
