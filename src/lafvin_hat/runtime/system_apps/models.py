from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SystemAppInfo:
    app_id: str
    name: str
    version: str
    description: str
    permissions: tuple[str, ...]
    ui_mode: str = "system"

    def to_public_dict(self, *, active: bool) -> dict[str, Any]:
        return {
            "id": self.app_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "permissions": list(self.permissions),
            "ui_mode": self.ui_mode,
            "state": "running" if active else "installed",
            "instance_id": None,
            "pid": None,
            "foreground": active,
            "exit_code": None,
            "development": False,
            "log_path": None,
            "system_app": True,
        }


class SystemApp(Protocol):
    info: SystemAppInfo

    @property
    def active(self) -> bool: ...

    async def launch(self) -> None: ...

    async def stop(self) -> None: ...

    async def handle_event(self, event: dict[str, Any]) -> bool: ...

    def public_state(self) -> dict[str, Any]: ...
