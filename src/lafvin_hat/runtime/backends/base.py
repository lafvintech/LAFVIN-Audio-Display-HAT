from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class BatteryState:
    level: int
    charging: bool = False


class DeviceEventSink(Protocol):
    async def __call__(
        self,
        event_name: str,
        payload: dict[str, Any],
    ) -> None: ...


class DeviceBackend(Protocol):
    name: str
    requires_linux_audio: bool
    display_width: int
    display_height: int

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def set_backlight(self, value: int) -> None: ...

    async def set_led(self, r: int, g: int, b: int) -> None: ...

    async def get_button_state(self) -> bool: ...

    async def get_battery_state(self) -> BatteryState | None: ...

    async def present_frame(
        self,
        rgb565: bytes,
        *,
        width: int,
        height: int,
    ) -> None: ...

    async def set_declarative_view(
        self,
        view: dict[str, Any] | None,
        *,
        revision: int,
    ) -> None: ...

    async def set_display_mode(self, mode: str) -> None: ...

    def set_event_sink(self, sink: DeviceEventSink) -> None: ...

    def state_snapshot(self) -> dict[str, Any]: ...
