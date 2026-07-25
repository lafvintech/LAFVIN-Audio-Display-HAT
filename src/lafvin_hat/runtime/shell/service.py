from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from ..apps import AppManager
from ..apps.catalog import FirstPartyApp
from ..events import EventBus, EventSubscription
from ..ipc.protocol import ProtocolError
from ..system_apps import SystemAppRegistry
from ..ui import UIService


_HOME_TITLE = "LAFVIN HAT"


class ShellService:
    def __init__(
        self,
        app_manager: AppManager,
        ui_service: UIService,
        event_bus: EventBus,
        *,
        system_apps: SystemAppRegistry | None = None,
        first_party_apps: Sequence[FirstPartyApp] = (),
    ) -> None:
        self._app_manager = app_manager
        self._ui_service = ui_service
        self._event_bus = event_bus
        self._system_apps = system_apps
        self._first_party_apps = tuple(first_party_apps)
        self._mode = "home"
        self._selected = 0
        self._panel_selected = 0
        self._panel_items_cache: list[dict[str, str]] = []
        self._last_confirmed_id: str | None = None
        self._item_overrides: dict[str, str] = {}
        self._items: list[dict[str, str]] = []
        self._subscription: EventSubscription | None = None
        self._event_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._subscription = self._event_bus.subscribe(
            event_names={
                "button.raw_pressed",
                "button.raw_released",
                "button.single_clicked",
                "button.double_clicked",
                "button.triple_clicked",
                "app.installed",
                "app.uninstalled",
                "app.started",
                "app.foreground_acquired",
                "app.foreground_revoked",
                "app.stopped",
                "app.crashed",
            }
        )
        self._rebuild_items()
        await self._render()
        self._event_task = asyncio.create_task(
            self._watch_events(),
            name="system-shell-events",
        )

    async def stop(self) -> None:
        if self._system_apps is not None:
            await self._system_apps.stop_active()
        if self._event_task is not None:
            self._event_task.cancel()
            await asyncio.gather(self._event_task, return_exceptions=True)
            self._event_task = None
        if self._subscription is not None:
            self._event_bus.unsubscribe(self._subscription)
            self._subscription = None

    def snapshot(self) -> dict[str, Any]:
        items = self._current_items()
        selected = self._current_selected()
        selected_item = items[selected] if items else None
        return {
            "active": self._app_manager.foreground_app_id is None,
            "mode": self._mode,
            "selected": selected,
            "selected_item_id": (
                selected_item["id"] if selected_item is not None else None
            ),
            "last_confirmed_id": self._last_confirmed_id,
            "item_count": len(items),
        }

    def is_system_panel_active(self) -> bool:
        return self._mode != "home"

    def _rebuild_items(self) -> None:
        system_items: dict[str, dict[str, str]] = {}
        if self._system_apps is not None:
            for app in self._system_apps.list_apps():
                app_id = app["id"]
                system_items[app_id] = {
                    "id": app_id,
                    "label": app["name"],
                    "meta": self._item_overrides.get(
                        app_id,
                        app["state"],
                    ),
                }
        app_items: dict[str, dict[str, str]] = {}
        for app in self._app_manager.list_apps():
            app_id = app["id"]
            app_items[app_id] = {
                "id": app_id,
                "label": app["name"],
                "meta": self._item_overrides.get(
                    app_id,
                    app["state"],
                ),
            }

        items: list[dict[str, str]] = []
        used: set[str] = set()
        for catalog_app in self._first_party_apps:
            item_id = catalog_app.app_id
            item = system_items.get(item_id) or app_items.get(item_id)
            if item is None:
                continue
            item["label"] = catalog_app.name
            items.append(item)
            used.add(item_id)
        for item_id, item in system_items.items():
            if item_id not in used:
                items.append(item)
                used.add(item_id)
        for item_id, item in app_items.items():
            if item_id not in used:
                items.append(item)
                used.add(item_id)
        self._items = items
        self._selected = min(self._selected, max(0, len(items) - 1))

    async def _watch_events(self) -> None:
        assert self._subscription is not None
        while True:
            event = await self._subscription.queue.get()
            name = event["event"]
            if name in {"button.raw_pressed", "button.raw_released"}:
                if await self._route_system_flow_event(event):
                    continue
                continue
            if name.startswith("button.") and await self._route_system_flow_event(
                event,
            ):
                continue
            if name == "button.single_clicked":
                context = event["payload"].get("context")
                expected_context = "home" if self._mode == "home" else "shell"
                if context != expected_context:
                    continue
                self._last_confirmed_id = None
                if self._mode == "home" and self._items:
                    self._selected = (self._selected + 1) % len(self._items)
                elif self._mode != "home":
                    items = await self._load_panel_items()
                    if items:
                        self._panel_selected = (
                            self._panel_selected + 1
                        ) % len(items)
                await self._render()
            elif name == "button.double_clicked":
                context = event["payload"].get("context")
                expected_context = "home" if self._mode == "home" else "shell"
                if context != expected_context:
                    continue
                if self._mode == "home":
                    await self._activate_selected()
                else:
                    await self._confirm_panel_selection()
            elif name == "button.triple_clicked":
                context = event["payload"].get("context")
                if context == "foreground":
                    await self._return_home()
                elif context == "shell":
                    await self._return_shell_home()
            else:
                payload = event["payload"]
                app_id = payload.get("app_id")
                if name == "app.started" and isinstance(app_id, str):
                    self._item_overrides[app_id] = "launching"
                elif name == "app.foreground_acquired" and isinstance(app_id, str):
                    self._item_overrides[app_id] = "running"
                elif name == "app.foreground_revoked" and isinstance(app_id, str):
                    self._item_overrides.pop(app_id, None)
                elif name == "app.stopped" and isinstance(app_id, str):
                    self._item_overrides[app_id] = "stopped"
                elif name == "app.crashed" and isinstance(app_id, str):
                    self._item_overrides[app_id] = "crashed"
                elif name == "app.uninstalled" and isinstance(app_id, str):
                    self._item_overrides.pop(app_id, None)
                self._rebuild_items()
                await self._render()

    async def _activate_selected(self) -> None:
        if not self._items:
            return
        item = self._items[self._selected]
        item_id = item["id"]
        self._last_confirmed_id = item_id
        if self._system_apps is not None and self._system_apps.contains(item_id):
            self._mode = "system_app"
            self._panel_selected = 0
            self._panel_items_cache = []
            try:
                await self._system_apps.launch(item_id)
            except ProtocolError as exc:
                self._mode = "home"
                self._item_overrides[item_id] = exc.message
                await self._render()
            return
        if item_id.startswith("system."):
            self._item_overrides[item_id] = "Unavailable"
            await self._render()
            return
        self._item_overrides[item_id] = "Launching"
        await self._render()
        try:
            await self._app_manager.launch(item_id)
        except ProtocolError as exc:
            self._item_overrides[item_id] = exc.message
            await self._render()

    async def _return_home(self) -> None:
        app_id = self._app_manager.foreground_app_id
        if app_id is None:
            return
        self._item_overrides[app_id] = "returning"
        await self._render()
        try:
            await self._app_manager.stop(app_id)
        except ProtocolError as exc:
            self._item_overrides[app_id] = exc.message
            await self._render()

    async def _return_shell_home(self) -> None:
        if self._mode == "home":
            return
        if self._mode == "system_app" and self._system_apps is not None:
            await self._system_apps.stop_active()
        self._mode = "home"
        self._panel_selected = 0
        await self._render()

    async def _render(self) -> None:
        if self._mode == "system_app":
            self._panel_items_cache = []
            return
        items = [dict(item) for item in self._items]
        if self._last_confirmed_id is not None:
            for item in items:
                if item["id"] == self._last_confirmed_id:
                    item["meta"] = self._item_overrides.get(
                        item["id"],
                        item["meta"],
                    )
                    break
        await self._ui_service.set_system_view(
            {
                "kind": "list",
                "title": _HOME_TITLE,
                "items": items,
                "selected": self._selected,
            }
        )

    def _current_items(self) -> list[dict[str, str]]:
        if self._mode == "home":
            return self._items
        return self._panel_items_cache

    def _current_selected(self) -> int:
        return self._selected if self._mode == "home" else self._panel_selected

    async def _load_panel_items(self) -> list[dict[str, str]]:
        if self._mode == "system_app":
            self._panel_items_cache = []
        return (
            self._items
            if self._mode == "home"
            else self._panel_items_cache
        )

    async def _confirm_panel_selection(self) -> None:
        items = await self._load_panel_items()
        if not items:
            return
        item_id = items[self._panel_selected]["id"]
        self._last_confirmed_id = item_id
        if item_id.endswith(".back"):
            self._mode = "home"
            self._panel_selected = 0
            await self._render()
            return
        await self._render()

    async def _route_system_flow_event(self, event: dict[str, Any]) -> bool:
        if self._system_apps is not None:
            consumed = bool(await self._system_apps.handle_event(event))
            if consumed and self._system_apps.active_app_id is None:
                self._mode = "home"
                self._panel_selected = 0
                await self._render()
            return consumed
        return False

