import asyncio
from pathlib import Path

from lafvin_hat.runtime.apps.catalog import load_app_catalog
from lafvin_hat.runtime.events import EventBus
from lafvin_hat.runtime.system_apps import HARDWARE_TEST_APP_ID
from lafvin_hat.runtime.shell import ShellService


ROOT = Path(__file__).resolve().parents[1]
FIRST_PARTY_APPS = load_app_catalog(ROOT / "apps/catalog.yaml", project_root=ROOT)


class AppManagerStub:
    def __init__(self) -> None:
        self.foreground_app_id = None
        self.launched: list[str] = []
        self.stopped: list[str] = []

    def list_apps(self) -> list[dict]:
        return [
            {
                "id": "dev.lafvin.chatbot",
                "name": "AI Chatbot",
                "state": "installed",
            },
            {
                "id": "dev.lafvin.system-status",
                "name": "System Status",
                "state": "installed",
            },
            {
                "id": "dev.lafvin.system-volume",
                "name": "Volume",
                "state": "installed",
            },
        ]

    async def launch(self, app_id: str) -> dict:
        self.launched.append(app_id)
        return {"app_id": app_id}

    async def stop(self, app_id: str) -> None:
        self.stopped.append(app_id)
        self.foreground_app_id = None


class UIServiceStub:
    def __init__(self) -> None:
        self.views: list[dict] = []

    async def set_system_view(self, view: dict) -> None:
        self.views.append(view)


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


class SystemAppsStub:
    def __init__(self, flow: HardwareTestFlowStub) -> None:
        self.flow = flow

    @property
    def active_app_id(self) -> str | None:
        return HARDWARE_TEST_APP_ID if self.flow.active else None

    def contains(self, app_id: str) -> bool:
        return app_id == HARDWARE_TEST_APP_ID

    def list_apps(self) -> list[dict]:
        return [
            {
                "id": HARDWARE_TEST_APP_ID,
                "name": "Hardware Test",
                "state": "running" if self.flow.active else "installed",
            }
        ]

    async def launch(self, app_id: str) -> dict:
        assert app_id == HARDWARE_TEST_APP_ID
        await self.flow.start()
        return self.list_apps()[0]

    async def stop_active(self) -> None:
        if self.flow.active:
            await self.flow.stop()

    async def handle_event(self, event: dict) -> bool:
        if not self.flow.active:
            return False
        return await self.flow.handle_event(event)


def test_shell_renders_and_handles_home_gestures() -> None:
    async def scenario() -> None:
        events = EventBus()
        ui = UIServiceStub()
        app_manager = AppManagerStub()
        system_apps = SystemAppsStub(HardwareTestFlowStub())
        shell = ShellService(
            app_manager,  # type: ignore[arg-type]
            ui,  # type: ignore[arg-type]
            events,
            system_apps=system_apps,  # type: ignore[arg-type]
            first_party_apps=FIRST_PARTY_APPS,
        )
        await shell.start()
        try:
            assert ui.views[-1]["title"] == "LAFVIN HAT"
            assert ui.views[-1]["selected"] == 0
            assert [
                item["id"] for item in ui.views[-1]["items"][:4]
            ] == [
                HARDWARE_TEST_APP_ID,
                "dev.lafvin.system-status",
                "dev.lafvin.system-volume",
                "dev.lafvin.chatbot",
            ]
            assert ui.views[-1]["items"][-1]["label"] == "AI Chatbot"

            await events.emit(
                "button.single_clicked",
                {"context": "home", "click_count": 1},
            )
            await asyncio.sleep(0)
            assert ui.views[-1]["selected"] == 1

            await events.emit(
                "button.double_clicked",
                {"context": "home", "click_count": 2},
            )
            await asyncio.sleep(0)
            assert app_manager.launched == ["dev.lafvin.system-status"]
            assert ui.views[-1]["items"][1]["meta"] == "Launching"
            assert shell.snapshot()["mode"] == "home"
            assert (
                shell.snapshot()["last_confirmed_id"]
                == "dev.lafvin.system-status"
            )
        finally:
            await shell.stop()

    asyncio.run(scenario())


def test_shell_launches_hardware_test_and_routes_button_events() -> None:
    async def scenario() -> None:
        events = EventBus()
        ui = UIServiceStub()
        app_manager = AppManagerStub()
        hardware_test = HardwareTestFlowStub()
        system_apps = SystemAppsStub(hardware_test)
        shell = ShellService(
            app_manager,  # type: ignore[arg-type]
            ui,  # type: ignore[arg-type]
            events,
            system_apps=system_apps,  # type: ignore[arg-type]
            first_party_apps=FIRST_PARTY_APPS,
        )
        await shell.start()
        try:
            assert ui.views[-1]["items"][0]["id"] == HARDWARE_TEST_APP_ID

            await events.emit(
                "button.double_clicked",
                {"context": "home", "click_count": 2},
            )
            await asyncio.sleep(0)

            assert hardware_test.started == 1
            assert shell.snapshot()["mode"] == "system_app"

            await events.emit("button.raw_pressed", {"pressed": True})
            await asyncio.sleep(0)
            assert hardware_test.events == ["button.raw_pressed"]

            await events.emit(
                "button.triple_clicked",
                {"context": "shell", "click_count": 3},
            )
            await asyncio.sleep(0)

            assert hardware_test.events[-1] == "button.triple_clicked"
            assert shell.snapshot()["mode"] == "home"
            assert ui.views[-1]["title"] == "LAFVIN HAT"
        finally:
            await shell.stop()

    asyncio.run(scenario())


def test_shell_launches_selected_app_and_stops_foreground() -> None:
    async def scenario() -> None:
        events = EventBus()
        ui = UIServiceStub()
        app_manager = AppManagerStub()
        system_apps = SystemAppsStub(HardwareTestFlowStub())
        shell = ShellService(
            app_manager,  # type: ignore[arg-type]
            ui,  # type: ignore[arg-type]
            events,
            system_apps=system_apps,  # type: ignore[arg-type]
            first_party_apps=FIRST_PARTY_APPS,
        )
        await shell.start()
        try:
            for _ in range(3):
                await events.emit(
                    "button.single_clicked",
                    {"context": "home", "click_count": 1},
                )
                await asyncio.sleep(0)
            assert ui.views[-1]["items"][3]["id"] == "dev.lafvin.chatbot"

            await events.emit(
                "button.double_clicked",
                {"context": "home", "click_count": 2},
            )
            await asyncio.sleep(0)
            assert app_manager.launched == ["dev.lafvin.chatbot"]
            assert ui.views[-1]["items"][3]["meta"] == "Launching"

            app_manager.foreground_app_id = "dev.lafvin.chatbot"
            await events.emit(
                "button.triple_clicked",
                {"context": "foreground", "click_count": 3},
            )
            await asyncio.sleep(0)
            assert app_manager.stopped == ["dev.lafvin.chatbot"]
        finally:
            await shell.stop()

    asyncio.run(scenario())
