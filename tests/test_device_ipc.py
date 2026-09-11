from __future__ import annotations

import asyncio
from pathlib import Path

from lafvin_hat.runtime.config import RuntimeEndpoint
from lafvin_hat.runtime.ipc.protocol import Request
from lafvin_hat.runtime.ipc.server import RuntimeServer


class _Authorizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, bool]] = []

    async def authorize(
        self,
        app_id: str,
        session_token: str,
        *,
        permission: str,
        require_foreground: bool = False,
        ui_mode: str | None = None,
    ) -> Path:
        del ui_mode
        self.calls.append(
            (app_id, session_token, permission, require_foreground)
        )
        return Path(".")


def test_device_led_write_requires_foreground_led_permission() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        authorizer = _Authorizer()
        server._app_manager = authorizer  # type: ignore[assignment]

        result = await server._handle_device_set_led(
            Request(
                request_id="led-1",
                method="device.set_led",
                params={
                    "app_id": "dev.lafvin.chatbot",
                    "session_token": "session-token",
                    "r": 145,
                    "g": 91,
                    "b": 220,
                },
            )
        )

        assert authorizer.calls == [
            ("dev.lafvin.chatbot", "session-token", "led", True)
        ]
        assert result["led"] == {"r": 145, "g": 91, "b": 220}

    asyncio.run(scenario())
