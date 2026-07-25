import asyncio

import pytest

from lafvin_hat.runtime.ipc.protocol import ProtocolError
from lafvin_hat.runtime.system_apps import (
    HARDWARE_TEST_APP_ID,
    HardwareTestSystemApp,
    SystemAppRegistry,
)


class HardwareTestFlowStub:
    def __init__(self) -> None:
        self.active = False
        self.started = 0
        self.stopped = 0
        self.events: list[str] = []

    async def start(self) -> None:
        self.active = True
        self.started += 1

    async def stop(self) -> None:
        self.active = False
        self.stopped += 1

    async def handle_event(self, event: dict) -> bool:
        self.events.append(event["event"])
        if event["event"] == "button.triple_clicked":
            self.active = False
        return True


def test_system_app_registry_launches_and_routes_hardware_test() -> None:
    async def scenario() -> None:
        flow = HardwareTestFlowStub()
        registry = SystemAppRegistry([HardwareTestSystemApp(flow)])

        assert registry.contains(HARDWARE_TEST_APP_ID)
        assert registry.active_app_id is None
        assert registry.list_apps()[0]["state"] == "installed"

        result = await registry.launch(HARDWARE_TEST_APP_ID)

        assert result["id"] == HARDWARE_TEST_APP_ID
        assert result["system_app"] is True
        assert result["state"] == "running"
        assert flow.started == 1
        assert registry.active_app_id == HARDWARE_TEST_APP_ID

        consumed = await registry.handle_event({
            "event": "button.raw_pressed",
            "payload": {"pressed": True},
        })

        assert consumed is True
        assert flow.events == ["button.raw_pressed"]

        consumed = await registry.handle_event({
            "event": "button.triple_clicked",
            "payload": {"context": "shell", "click_count": 3},
        })

        assert consumed is True
        assert registry.active_app_id is None

    asyncio.run(scenario())


def test_system_app_registry_rejects_unknown_app() -> None:
    async def scenario() -> None:
        registry = SystemAppRegistry([
            HardwareTestSystemApp(HardwareTestFlowStub())
        ])

        with pytest.raises(ProtocolError) as exc_info:
            await registry.launch("dev.lafvin.unknown")

        assert exc_info.value.code == "APP_NOT_FOUND"

    asyncio.run(scenario())
