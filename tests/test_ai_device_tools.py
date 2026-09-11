from __future__ import annotations

import asyncio
import json
from typing import Any

from lafvin_hat.ai import DeviceToolSet, ToolCall


class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((method, dict(params or {})))
        if method == "runtime.status":
            return {
                "system": {
                    "runtime": {"uptime_ms": 123_000},
                    "device": {
                        "model": "Raspberry Pi 4",
                        "hostname": "lafvin-pi",
                        "temperature_c": 48.5,
                    },
                    "network": {"ip_address": "192.168.1.20"},
                    "resources": {
                        "cpu": {"usage_percent": 12.5},
                        "memory": {"usage_percent": 40.0},
                    },
                    "storage": {"usage_percent": 55.0},
                    "apps": {"installed_count": 7},
                }
            }
        if method == "device.set_led":
            return {
                "led": {
                    "r": params["r"],
                    "g": params["g"],
                    "b": params["b"],
                }
            }
        raise AssertionError(f"Unexpected request: {method}")


class _Audio:
    def __init__(self) -> None:
        self.volume = 70
        self.set_values: list[int] = []

    async def get_volume(self) -> int:
        return self.volume

    async def set_volume(self, value: int) -> int:
        self.set_values.append(value)
        self.volume = value
        return value


class _App:
    app_id = "dev.lafvin.chatbot"
    session_token = "session-token"

    def __init__(self) -> None:
        self.client = _Client()
        self.audio = _Audio()


def test_device_tool_set_exposes_only_four_allowlisted_tools() -> None:
    tools = DeviceToolSet(_App())

    assert [definition.name for definition in tools.definitions] == [
        "get_device_status",
        "get_volume",
        "set_volume",
        "set_rgb_led",
    ]


def test_device_status_and_volume_tools_use_runtime_sdk() -> None:
    async def scenario() -> None:
        app = _App()
        tools = DeviceToolSet(app)

        status = json.loads(
            await tools.execute(ToolCall("status-1", "get_device_status", {}))
        )
        volume = json.loads(
            await tools.execute(ToolCall("volume-1", "get_volume", {}))
        )
        changed = json.loads(
            await tools.execute(
                ToolCall("volume-2", "set_volume", {"percent": 60})
            )
        )

        assert status == {
            "ok": True,
            "model": "Raspberry Pi 4",
            "hostname": "lafvin-pi",
            "ip_address": "192.168.1.20",
            "runtime_uptime_ms": 123_000,
            "cpu_usage_percent": 12.5,
            "memory_usage_percent": 40.0,
            "temperature_c": 48.5,
            "storage_usage_percent": 55.0,
            "installed_app_count": 7,
        }
        assert volume == {"ok": True, "volume_percent": 70}
        assert changed == {"ok": True, "volume_percent": 60}
        assert app.audio.set_values == [60]
        assert app.client.calls == [("runtime.status", {})]

    asyncio.run(scenario())


def test_rgb_tool_sends_authenticated_integer_channels() -> None:
    async def scenario() -> None:
        app = _App()
        tools = DeviceToolSet(app)

        result = json.loads(
            await tools.execute(
                ToolCall(
                    "rgb-1",
                    "set_rgb_led",
                    {"red": 145, "green": 91, "blue": 220},
                )
            )
        )

        assert result == {
            "ok": True,
            "red": 145,
            "green": 91,
            "blue": 220,
        }
        assert app.client.calls == [
            (
                "device.set_led",
                {
                    "app_id": app.app_id,
                    "session_token": app.session_token,
                    "r": 145,
                    "g": 91,
                    "b": 220,
                },
            )
        ]

    asyncio.run(scenario())


def test_device_tools_reject_invalid_arguments_without_hardware_write() -> None:
    async def scenario() -> None:
        app = _App()
        tools = DeviceToolSet(app)

        volume = json.loads(
            await tools.execute(
                ToolCall("volume-1", "set_volume", {"percent": 101})
            )
        )
        rgb = json.loads(
            await tools.execute(
                ToolCall(
                    "rgb-1",
                    "set_rgb_led",
                    {"red": True, "green": 0, "blue": 0},
                )
            )
        )

        assert volume == {
            "ok": False,
            "error": "percent must be between 0 and 100",
        }
        assert rgb == {"ok": False, "error": "red must be an integer"}
        assert app.audio.set_values == []
        assert app.client.calls == []

    asyncio.run(scenario())
