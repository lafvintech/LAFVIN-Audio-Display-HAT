from __future__ import annotations

from typing import Any

from .models import SystemAppInfo


HARDWARE_TEST_APP_ID = "dev.lafvin.hardware-test"


class HardwareTestSystemApp:
    def __init__(self, flow: Any) -> None:
        self._flow = flow
        self.info = SystemAppInfo(
            app_id=HARDWARE_TEST_APP_ID,
            name="Hardware Test",
            version="runtime",
            description="Runtime-hosted LCD, RGB, button, speaker, and mic test",
            permissions=(
                "display.system",
                "button",
                "speaker",
                "microphone",
                "device.led",
            ),
        )

    @property
    def active(self) -> bool:
        return bool(self._flow.active)

    async def launch(self) -> None:
        await self._flow.start()

    async def stop(self) -> None:
        await self._flow.stop()

    async def handle_event(self, event: dict[str, Any]) -> bool:
        return bool(await self._flow.handle_event(event))

    def public_state(self) -> dict[str, Any]:
        return self.info.to_public_dict(active=self.active)
