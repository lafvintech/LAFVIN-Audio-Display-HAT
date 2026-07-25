from __future__ import annotations

import asyncio
import copy
import importlib
import importlib.util
import time
from pathlib import Path
from types import ModuleType
from typing import Any

from .base import BatteryState, DeviceEventSink
from .metrics import DisplayMetrics


class LafvinHatBackend:
    """Runtime backend for the supported LAFVIN HAT board."""

    name = "lafvin-hat"
    requires_linux_audio = True
    display_width = 240
    display_height = 280

    def __init__(self, driver_path: Path | None = None) -> None:
        self.driver_path = driver_path.resolve() if driver_path else None
        self._board: Any = None
        self._event_sink: DeviceEventSink | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._button_pressed = False
        self._backlight = 100
        self._led = (0, 0, 0)
        self._display_mode = "declarative"
        self._view: dict[str, Any] | None = None
        self._view_revision = 0
        self._frame_sequence = 0
        self._hardware_lock = asyncio.Lock()
        self._display_metrics = DisplayMetrics()

    async def start(self) -> None:
        if self._board is not None:
            return
        self._loop = asyncio.get_running_loop()
        module = await asyncio.to_thread(self._load_driver)
        self._board = await asyncio.to_thread(self._create_board, module)
        self._board.button.bind(
            self._on_button_pressed,
            self._on_button_released,
        )
        await self.set_backlight(self._backlight)

    async def stop(self) -> None:
        board, self._board = self._board, None
        self._loop = None
        if board is not None:
            async with self._hardware_lock:
                await asyncio.to_thread(board.cleanup)

    def set_event_sink(self, sink: DeviceEventSink) -> None:
        self._event_sink = sink

    async def set_backlight(self, value: int) -> None:
        self._backlight = max(0, min(100, int(value)))
        if self._board is not None:
            async with self._hardware_lock:
                await asyncio.to_thread(
                    self._board.backlight.set,
                    self._backlight,
                )

    async def set_led(self, r: int, g: int, b: int) -> None:
        self._led = tuple(
            max(0, min(255, int(value))) for value in (r, g, b)
        )
        if self._board is not None:
            async with self._hardware_lock:
                await asyncio.to_thread(self._board.led.set, *self._led)

    async def get_button_state(self) -> bool:
        return self._button_pressed

    async def get_battery_state(self) -> BatteryState | None:
        return None

    async def present_frame(
        self,
        rgb565: bytes,
        *,
        width: int,
        height: int,
    ) -> None:
        if width != self.display_width or height != self.display_height:
            raise ValueError("Frame dimensions do not match the LAFVIN HAT display")
        if len(rgb565) != width * height * 2:
            raise ValueError("RGB565 frame size is invalid")
        if self._board is None:
            raise RuntimeError("LAFVIN HAT backend is not started")
        started = time.perf_counter()
        async with self._hardware_lock:
            await asyncio.to_thread(
                self._board.display.present_rgb565,
                rgb565,
                width=width,
                height=height,
            )
        self._frame_sequence += 1
        self._display_metrics.record_present(
            (time.perf_counter() - started) * 1000
        )

    async def set_declarative_view(
        self,
        view: dict[str, Any] | None,
        *,
        revision: int,
    ) -> None:
        self._view = copy.deepcopy(view)
        self._view_revision = revision

    async def set_display_mode(self, mode: str) -> None:
        if mode not in {"declarative", "raw_frame"}:
            raise ValueError(f"Unsupported display mode: {mode}")
        self._display_mode = mode

    def state_snapshot(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "device_backend": self.name,
            "hardware_profile": {
                "name": self._board.profile_name if self._board else "lafvin-hat-rpi",
                "implementation": (
                    self._board.implementation
                    if self._board
                    else "lafvin-native-rpi"
                ),
            },
            "display": {
                "width": self.display_width,
                "height": self.display_height,
            },
            "display_metrics": self._display_metrics.snapshot(),
            "button_pressed": self._button_pressed,
            "backlight": self._backlight,
            "led": {
                "r": self._led[0],
                "g": self._led[1],
                "b": self._led[2],
            },
            "battery": None,
            "network": None,
            "ui": {
                "mode": self._display_mode,
                "revision": self._view_revision,
                "view": copy.deepcopy(self._view),
                "frame_sequence": self._frame_sequence,
            },
            "driver_source": (
                str(self.driver_path) if self.driver_path else "bundled"
            ),
        }

    def _load_driver(self) -> ModuleType:
        if self.driver_path is None:
            try:
                return importlib.import_module("lafvin_hat.hardware.lafvin_hat")
            except ImportError as exc:
                raise RuntimeError(
                    f"Cannot load bundled LAFVIN HAT board: {exc}"
                ) from exc
        if not self.driver_path.is_file():
            raise RuntimeError(f"LAFVIN HAT driver not found: {self.driver_path}")
        spec = importlib.util.spec_from_file_location(
            "lafvin_hat_external_driver",
            self.driver_path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load LAFVIN HAT driver: {self.driver_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _create_board(module: ModuleType) -> Any:
        board_type = getattr(module, "LafvinHatBoard", None)
        if board_type is None:
            raise RuntimeError("Driver must export LafvinHatBoard")
        return board_type()

    def _on_button_pressed(self) -> None:
        self._dispatch_button(True)

    def _on_button_released(self) -> None:
        self._dispatch_button(False)

    def _dispatch_button(self, pressed: bool) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._emit_button(pressed))
        )

    async def _emit_button(self, pressed: bool) -> None:
        if pressed == self._button_pressed:
            return
        self._button_pressed = pressed
        if self._event_sink is not None:
            await self._event_sink(
                "button.raw_pressed" if pressed else "button.raw_released",
                {"pressed": pressed},
            )
