from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .models import ToolCall, ToolDefinition


logger = logging.getLogger(__name__)
ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


DEVICE_TOOL_STATUS = {
    "get_device_status": "Checking device...",
    "get_volume": "Checking volume...",
    "set_volume": "Setting volume...",
    "set_rgb_led": "Setting RGB light...",
}


class DeviceToolSet:
    """Small allowlisted tool set backed by the authenticated Runtime SDK."""

    def __init__(self, app: Any) -> None:
        self._app = app
        self.definitions = (
            ToolDefinition(
                name="get_device_status",
                description=(
                    "Get the current device model, hostname, IP address, "
                    "Runtime uptime, CPU usage, memory usage, temperature, "
                    "storage usage, and installed application count."
                ),
                parameters=_empty_parameters(),
            ),
            ToolDefinition(
                name="get_volume",
                description="Get the current speaker volume percentage.",
                parameters=_empty_parameters(),
            ),
            ToolDefinition(
                name="set_volume",
                description="Set the speaker volume to an integer from 0 to 100.",
                parameters={
                    "type": "object",
                    "properties": {
                        "percent": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Target speaker volume percentage.",
                        }
                    },
                    "required": ["percent"],
                    "additionalProperties": False,
                },
            ),
            ToolDefinition(
                name="set_rgb_led",
                description=(
                    "Set the device RGB light using integer red, green, and "
                    "blue channel values from 0 to 255."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        channel: {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 255,
                            "description": f"{channel.title()} channel value.",
                        }
                        for channel in ("red", "green", "blue")
                    },
                    "required": ["red", "green", "blue"],
                    "additionalProperties": False,
                },
            ),
        )
        self._handlers: dict[str, ToolHandler] = {
            "get_device_status": self._get_device_status,
            "get_volume": self._get_volume,
            "set_volume": self._set_volume,
            "set_rgb_led": self._set_rgb_led,
        }

    async def execute(self, call: ToolCall) -> str:
        handler = self._handlers.get(call.name)
        if handler is None:
            return _result_json(
                ok=False,
                error=f"Unknown device tool: {call.name}",
            )
        logger.info("stage=device_tool event=start tool=%s", call.name)
        try:
            result = await handler(call.arguments)
        except ValueError as exc:
            logger.warning(
                "stage=device_tool event=invalid_arguments tool=%s error=%s",
                call.name,
                exc,
            )
            return _result_json(ok=False, error=str(exc))
        logger.info("stage=device_tool event=done tool=%s", call.name)
        return _result_json(ok=True, **result)

    async def _get_device_status(
        self,
        _arguments: dict[str, Any],
    ) -> dict[str, Any]:
        status = await self._app.client.request("runtime.status")
        system = _mapping(status.get("system"))
        device = _mapping(system.get("device"))
        network = _mapping(system.get("network"))
        runtime = _mapping(system.get("runtime"))
        resources = _mapping(system.get("resources"))
        cpu = _mapping(resources.get("cpu"))
        memory = _mapping(resources.get("memory"))
        storage = _mapping(system.get("storage"))
        apps = _mapping(system.get("apps"))
        return {
            "model": device.get("model"),
            "hostname": device.get("hostname"),
            "ip_address": network.get("ip_address"),
            "runtime_uptime_ms": runtime.get("uptime_ms"),
            "cpu_usage_percent": cpu.get("usage_percent"),
            "memory_usage_percent": memory.get("usage_percent"),
            "temperature_c": device.get("temperature_c"),
            "storage_usage_percent": storage.get("usage_percent"),
            "installed_app_count": apps.get("installed_count"),
        }

    async def _get_volume(
        self,
        _arguments: dict[str, Any],
    ) -> dict[str, Any]:
        return {"volume_percent": await self._app.audio.get_volume()}

    async def _set_volume(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        percent = _integer_argument(arguments, "percent", minimum=0, maximum=100)
        return {"volume_percent": await self._app.audio.set_volume(percent)}

    async def _set_rgb_led(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        red = _integer_argument(arguments, "red", minimum=0, maximum=255)
        green = _integer_argument(arguments, "green", minimum=0, maximum=255)
        blue = _integer_argument(arguments, "blue", minimum=0, maximum=255)
        state = await self._app.client.request(
            "device.set_led",
            {
                "app_id": self._app.app_id,
                "session_token": self._app.session_token,
                "r": red,
                "g": green,
                "b": blue,
            },
        )
        led = _mapping(state.get("led"))
        return {
            "red": led.get("r", red),
            "green": led.get("g", green),
            "blue": led.get("b", blue),
        }


def _empty_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def _integer_argument(
    arguments: dict[str, Any],
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = arguments.get(name)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not float(value).is_integer()
    ):
        raise ValueError(f"{name} must be an integer")
    normalized = int(value)
    if not minimum <= normalized <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return normalized


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _result_json(*, ok: bool, **values: Any) -> str:
    return json.dumps(
        {"ok": ok, **values},
        ensure_ascii=False,
        separators=(",", ":"),
    )
