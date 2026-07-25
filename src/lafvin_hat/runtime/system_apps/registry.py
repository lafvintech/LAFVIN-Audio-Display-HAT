from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..ipc.protocol import ProtocolError
from .models import SystemApp


class SystemAppRegistry:
    """Runtime-owned system apps that run without subprocess startup."""

    def __init__(self, apps: Iterable[SystemApp] = ()) -> None:
        self._apps = {app.info.app_id: app for app in apps}

    @property
    def active_app_id(self) -> str | None:
        for app_id, app in self._apps.items():
            if app.active:
                return app_id
        return None

    def contains(self, app_id: str) -> bool:
        return app_id in self._apps

    def list_apps(self) -> list[dict[str, Any]]:
        return [
            app.public_state()
            for _app_id, app in sorted(self._apps.items())
        ]

    def snapshot(self) -> dict[str, Any]:
        return {
            "active_app_id": self.active_app_id,
            "apps": self.list_apps(),
        }

    async def launch(self, app_id: str) -> dict[str, Any]:
        app = self._require_app(app_id)
        active_app_id = self.active_app_id
        if active_app_id is not None:
            raise ProtocolError(
                "APP_ALREADY_RUNNING",
                f"System app is already running: {active_app_id}",
            )
        await app.launch()
        return app.public_state()

    async def stop(self, app_id: str) -> None:
        app = self._require_app(app_id)
        if not app.active:
            raise ProtocolError(
                "APP_NOT_RUNNING",
                f"System app is not running: {app_id}",
            )
        await app.stop()

    async def stop_active(self) -> None:
        active_app_id = self.active_app_id
        if active_app_id is not None:
            await self._apps[active_app_id].stop()

    async def handle_event(self, event: dict[str, Any]) -> bool:
        active_app_id = self.active_app_id
        if active_app_id is None:
            return False
        return bool(await self._apps[active_app_id].handle_event(event))

    def _require_app(self, app_id: str) -> SystemApp:
        app = self._apps.get(app_id)
        if app is None:
            raise ProtocolError("APP_NOT_FOUND", f"Unknown system app: {app_id}")
        return app
