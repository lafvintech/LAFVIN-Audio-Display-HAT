from __future__ import annotations

import asyncio
import copy
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .base import BatteryState, DeviceEventSink
from .metrics import DisplayMetrics


_INDEX_PATH = Path(__file__).with_name("simulator_index.html")


class SimulatorBackend:
    name = "simulator"
    requires_linux_audio = False
    display_width = 240
    display_height = 280

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 17880,
        web_enabled: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.web_enabled = web_enabled
        self._event_sink: DeviceEventSink | None = None
        self._web_server: asyncio.AbstractServer | None = None
        self._button_pressed = False
        self._backlight = 100
        self._led = (0, 0, 0)
        self._battery = BatteryState(level=100, charging=False)
        self._network_online = True
        self._view: dict[str, Any] | None = None
        self._view_revision = 0
        self._display_mode = "declarative"
        self._frame_sequence = 0
        self._last_frame: bytes | None = None
        self._display_metrics = DisplayMetrics()

    @property
    def bound_port(self) -> int:
        if self._web_server is None:
            return self.port
        return int(self._web_server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        if self.web_enabled and self._web_server is None:
            self._web_server = await asyncio.start_server(
                self._handle_http_client,
                host=self.host,
                port=self.port,
            )

    async def stop(self) -> None:
        if self._web_server is None:
            return
        self._web_server.close()
        await self._web_server.wait_closed()
        self._web_server = None

    def set_event_sink(self, sink: DeviceEventSink) -> None:
        self._event_sink = sink

    async def set_backlight(self, value: int) -> None:
        self._backlight = max(0, min(100, int(value)))

    async def set_led(self, r: int, g: int, b: int) -> None:
        self._led = tuple(max(0, min(255, int(value))) for value in (r, g, b))

    async def get_button_state(self) -> bool:
        return self._button_pressed

    async def get_battery_state(self) -> BatteryState:
        return self._battery

    async def present_frame(
        self,
        rgb565: bytes,
        *,
        width: int,
        height: int,
    ) -> None:
        expected = width * height * 2
        if width != self.display_width or height != self.display_height:
            raise ValueError("Frame dimensions do not match the simulator display")
        if len(rgb565) != expected:
            raise ValueError(f"RGB565 frame must contain {expected} bytes")
        started = time.perf_counter()
        self._last_frame = bytes(rgb565)
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

    async def inject_button(self, pressed: bool) -> None:
        pressed = bool(pressed)
        if pressed == self._button_pressed:
            return
        self._button_pressed = pressed
        await self._emit(
            "button.raw_pressed" if pressed else "button.raw_released",
            {"pressed": pressed},
        )

    async def set_simulated_state(
        self,
        *,
        battery_level: int | None = None,
        charging: bool | None = None,
        network_online: bool | None = None,
    ) -> None:
        if battery_level is not None or charging is not None:
            previous = self._battery
            self._battery = BatteryState(
                level=max(
                    0,
                    min(
                        100,
                        previous.level if battery_level is None else int(battery_level),
                    ),
                ),
                charging=(
                    previous.charging if charging is None else bool(charging)
                ),
            )
            if self._battery != previous:
                await self._emit(
                    "battery.changed",
                    {
                        "level": self._battery.level,
                        "charging": self._battery.charging,
                    },
                )
        if network_online is not None:
            next_value = bool(network_online)
            if next_value != self._network_online:
                self._network_online = next_value
                await self._emit(
                    "network.changed",
                    {"online": self._network_online},
                )

    def state_snapshot(self) -> dict[str, Any]:
        return {
            "backend": self.name,
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
            "battery": {
                "level": self._battery.level,
                "charging": self._battery.charging,
            },
            "network": {
                "online": self._network_online,
            },
            "ui": {
                "mode": self._display_mode,
                "revision": self._view_revision,
                "view": copy.deepcopy(self._view),
                "frame_sequence": self._frame_sequence,
            },
            "web_url": (
                f"http://{self.host}:{self.bound_port}" if self.web_enabled else None
            ),
        }

    async def _emit(self, event_name: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            await self._event_sink(event_name, payload)

    async def _handle_http_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if not request_line:
                return
            try:
                method, target, _http_version = (
                    request_line.decode("ascii").strip().split(" ", 2)
                )
            except (UnicodeDecodeError, ValueError):
                await self._send_response(writer, 400, b"Bad Request")
                return

            headers: dict[str, str] = {}
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=2.0)
                if line in {b"\r\n", b"\n", b""}:
                    break
                key, _, value = line.decode("latin-1").partition(":")
                headers[key.strip().lower()] = value.strip()

            content_length = int(headers.get("content-length", "0") or "0")
            body = (
                await asyncio.wait_for(reader.readexactly(content_length), timeout=2.0)
                if content_length
                else b""
            )
            path = urlsplit(target).path
            await self._route_http(writer, method.upper(), path, body)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ValueError):
            await self._send_response(writer, 400, b"Bad Request")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _route_http(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        path: str,
        body: bytes,
    ) -> None:
        if method == "GET" and path == "/":
            await self._send_response(
                writer,
                200,
                _INDEX_PATH.read_bytes(),
                content_type="text/html; charset=utf-8",
            )
            return
        if method == "GET" and path == "/api/state":
            await self._send_json(writer, 200, self.state_snapshot())
            return
        if method == "GET" and path == "/api/frame":
            await self._send_response(
                writer,
                200,
                self._last_frame or bytes(self.display_width * self.display_height * 2),
                content_type="application/octet-stream",
            )
            return
        if method == "POST" and path == "/api/button":
            payload = self._decode_json_object(body)
            await self.inject_button(bool(payload.get("pressed")))
            await self._send_json(writer, 200, self.state_snapshot())
            return
        if method == "POST" and path == "/api/state":
            payload = self._decode_json_object(body)
            await self.set_simulated_state(
                battery_level=payload.get("battery_level"),
                charging=payload.get("charging"),
                network_online=payload.get("network_online"),
            )
            await self._send_json(writer, 200, self.state_snapshot())
            return
        await self._send_response(writer, 404, b"Not Found")

    def _decode_json_object(self, body: bytes) -> dict[str, Any]:
        value = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    async def _send_json(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        payload: dict[str, Any],
    ) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        await self._send_response(
            writer,
            status,
            body,
            content_type="application/json",
        )

    async def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        body: bytes,
        *,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        reason = {
            200: "OK",
            400: "Bad Request",
            404: "Not Found",
        }.get(status, "Error")
        headers = (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "Cache-Control: no-store\r\n"
            "\r\n"
        ).encode("ascii")
        writer.write(headers + body)
        await writer.drain()
