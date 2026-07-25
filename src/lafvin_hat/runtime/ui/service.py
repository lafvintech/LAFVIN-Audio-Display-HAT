from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

from ..apps import AppManager
from ..backends import DeviceBackend
from ..events import EventBus, EventSubscription
from ..ipc.protocol import ProtocolError
from .views import UIModelError, PillowRenderer, apply_patch, validate_view


class UIService:
    def __init__(
        self,
        app_manager: AppManager,
        backend: DeviceBackend,
        event_bus: EventBus,
    ) -> None:
        self._app_manager = app_manager
        self._backend = backend
        self._event_bus = event_bus
        self._renderer = PillowRenderer(
            backend.display_width,
            backend.display_height,
        )
        self._owner_app_id: str | None = None
        self._view: dict[str, Any] | None = None
        self._system_view: dict[str, Any] | None = None
        self._revision = 0
        self._system_view_visible = False
        self._lock = asyncio.Lock()
        self._subscription: EventSubscription | None = None
        self._event_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._subscription = self._event_bus.subscribe(
            event_names={
                "app.foreground_acquired",
                "app.foreground_revoked",
                "app.stopped",
                "app.crashed",
            }
        )
        self._event_task = asyncio.create_task(
            self._watch_lifecycle(),
            name="ui-lifecycle-watch",
        )

    async def stop(self) -> None:
        if self._event_task is not None:
            self._event_task.cancel()
            await asyncio.gather(self._event_task, return_exceptions=True)
            self._event_task = None
        if self._subscription is not None:
            self._event_bus.unsubscribe(self._subscription)
            self._subscription = None

    async def set_view(
        self,
        app_id: str,
        session_token: str,
        view: Any,
    ) -> dict[str, Any]:
        asset_root = await self._app_manager.authorize(
            app_id,
            session_token,
            permission="display.declarative",
            require_foreground=True,
            ui_mode="declarative",
        )
        try:
            validated = validate_view(view)
        except UIModelError as exc:
            raise ProtocolError("INVALID_VIEW", str(exc)) from exc
        async with self._lock:
            self._owner_app_id = app_id
            self._view = validated
            self._revision += 1
            revision = self._revision
            await self._present(validated, asset_root=asset_root)
            self._system_view_visible = False
        return self.snapshot(revision=revision)

    async def patch_view(
        self,
        app_id: str,
        session_token: str,
        operations: Any,
    ) -> dict[str, Any]:
        asset_root = await self._app_manager.authorize(
            app_id,
            session_token,
            permission="display.declarative",
            require_foreground=True,
            ui_mode="declarative",
        )
        async with self._lock:
            if self._owner_app_id != app_id or self._view is None:
                raise ProtocolError(
                    "INVALID_VIEW",
                    "The app has no current declarative view",
                )
            try:
                patched = apply_patch(self._view, operations)
            except UIModelError as exc:
                raise ProtocolError("INVALID_VIEW", str(exc)) from exc
            self._view = patched
            self._revision += 1
            revision = self._revision
            await self._present(patched, asset_root=asset_root)
            self._system_view_visible = False
        return self.snapshot(revision=revision)

    async def clear(
        self,
        app_id: str,
        session_token: str,
    ) -> dict[str, Any]:
        await self._app_manager.authorize(
            app_id,
            session_token,
            permission="display.declarative",
            require_foreground=True,
            ui_mode="declarative",
        )
        await self.clear_for_app(app_id)
        return self.snapshot()

    async def clear_for_app(self, app_id: str) -> None:
        async with self._lock:
            if self._owner_app_id == app_id:
                self._owner_app_id = None
                self._view = None
                self._revision += 1

    async def set_system_view(self, view: Any) -> None:
        try:
            validated = validate_view(view)
        except UIModelError as exc:
            raise ValueError(f"Invalid system view: {exc}") from exc
        async with self._lock:
            changed = validated != self._system_view
            self._system_view = validated
            if changed:
                self._revision += 1
            if (
                self._app_manager.foreground_app_id is None
                and self._owner_app_id is None
                and (changed or not self._system_view_visible)
            ):
                await self._present(validated, asset_root=None)
                self._system_view_visible = True

    def snapshot(self, *, revision: int | None = None) -> dict[str, Any]:
        active_view = self._view
        if (
            self._owner_app_id is None
            and self._app_manager.foreground_app_id is None
        ):
            active_view = self._system_view
        return {
            "owner_app_id": self._owner_app_id,
            "revision": self._revision if revision is None else revision,
            "view": copy.deepcopy(active_view),
        }

    async def _present(
        self,
        view: dict[str, Any] | None,
        *,
        asset_root: Path | None,
    ) -> None:
        frame = await asyncio.to_thread(
            self._renderer.render,
            view,
            asset_root=asset_root,
        )
        await self._backend.present_frame(
            frame.rgb565,
            width=frame.width,
            height=frame.height,
        )
        await self._backend.set_display_mode("declarative")
        await self._backend.set_declarative_view(
            copy.deepcopy(view),
            revision=self._revision,
        )

    async def _watch_lifecycle(self) -> None:
        assert self._subscription is not None
        while True:
            event = await self._subscription.queue.get()
            if event["event"] == "app.foreground_acquired":
                async with self._lock:
                    self._system_view_visible = False
                # Keep the previous shell frame visible until the foreground app
                # submits its own view or Raw Frame. Painting an intermediate
                # empty frame can race with Raw Frame startup on SPI hardware.
                continue
            app_id = event["payload"].get("app_id")
            if isinstance(app_id, str):
                await self.clear_for_app(app_id)
