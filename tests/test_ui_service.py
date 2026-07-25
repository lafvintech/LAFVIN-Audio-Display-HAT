import asyncio
from pathlib import Path

from lafvin_hat.runtime.backends import SimulatorBackend
from lafvin_hat.runtime.events import EventBus
from lafvin_hat.runtime.shell import ShellService
from lafvin_hat.runtime.ui import UIService


class AppManagerStub:
    def __init__(self) -> None:
        self.foreground_app_id: str | None = None
        self.state = "installed"

    def list_apps(self) -> list[dict[str, str]]:
        return [
            {
                "id": "dev.lafvin.raw",
                "name": "Raw App",
                "state": self.state,
            }
        ]

    async def authorize(
        self,
        app_id: str,
        session_token: str,
        *,
        permission: str,
        require_foreground: bool = False,
        ui_mode: str | None = None,
    ) -> Path:
        return Path(".")


def test_system_home_is_presented_once_per_visibility_transition() -> None:
    async def scenario() -> None:
        app_manager = AppManagerStub()
        backend = SimulatorBackend(web_enabled=False)
        events = EventBus()
        service = UIService(
            app_manager,  # type: ignore[arg-type]
            backend,
            events,
        )
        home = {
            "kind": "list",
            "title": "LAFVIN HAT",
            "items": [],
            "selected": 0,
        }

        await backend.start()
        await service.start()
        try:
            assert backend.state_snapshot()["ui"]["frame_sequence"] == 0

            await service.set_system_view(home)
            assert backend.state_snapshot()["ui"]["frame_sequence"] == 1

            await service.set_system_view(home)
            assert backend.state_snapshot()["ui"]["frame_sequence"] == 1

            app_manager.foreground_app_id = "dev.lafvin.raw"
            await events.emit(
                "app.foreground_acquired",
                {"app_id": "dev.lafvin.raw"},
                app_id="dev.lafvin.raw",
            )
            await asyncio.sleep(0)

            app_manager.foreground_app_id = None
            await events.emit(
                "app.foreground_revoked",
                {"app_id": "dev.lafvin.raw"},
                app_id="dev.lafvin.raw",
            )
            await asyncio.sleep(0)
            assert backend.state_snapshot()["ui"]["frame_sequence"] == 1

            await service.set_system_view(home)
            assert backend.state_snapshot()["ui"]["frame_sequence"] == 2

            await service.set_system_view(home)
            assert backend.state_snapshot()["ui"]["frame_sequence"] == 2
        finally:
            await service.stop()
            await backend.stop()

    asyncio.run(scenario())


def test_raw_frame_exit_restores_home_with_one_display_write() -> None:
    async def wait_for_home(backend: SimulatorBackend) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 1.0
        while loop.time() < deadline:
            snapshot = backend.state_snapshot()["ui"]
            view = snapshot.get("view")
            if (
                snapshot["mode"] == "declarative"
                and isinstance(view, dict)
                and view.get("title") == "LAFVIN HAT"
            ):
                return
            await asyncio.sleep(0.01)
        raise AssertionError("Home view was not restored within one second")

    async def scenario() -> None:
        app_manager = AppManagerStub()
        backend = SimulatorBackend(web_enabled=False)
        events = EventBus()
        ui = UIService(
            app_manager,  # type: ignore[arg-type]
            backend,
            events,
        )
        shell = ShellService(
            app_manager,  # type: ignore[arg-type]
            ui,
            events,
        )

        await backend.start()
        await ui.start()
        await shell.start()
        try:
            assert backend.state_snapshot()["ui"]["frame_sequence"] == 1

            app_manager.foreground_app_id = "dev.lafvin.raw"
            app_manager.state = "foreground"
            await events.emit(
                "app.foreground_acquired",
                {"app_id": "dev.lafvin.raw"},
                app_id="dev.lafvin.raw",
            )
            await asyncio.sleep(0)

            await backend.present_frame(
                bytes(backend.display_width * backend.display_height * 2),
                width=backend.display_width,
                height=backend.display_height,
            )
            await backend.set_display_mode("raw_frame")
            before_exit = backend.state_snapshot()["ui"]["frame_sequence"]

            app_manager.foreground_app_id = None
            app_manager.state = "stopped"
            await events.emit(
                "app.foreground_revoked",
                {"app_id": "dev.lafvin.raw"},
                app_id="dev.lafvin.raw",
            )
            await events.emit(
                "app.stopped",
                {"app_id": "dev.lafvin.raw", "exit_code": 0},
                app_id="dev.lafvin.raw",
            )
            await wait_for_home(backend)

            snapshot = backend.state_snapshot()["ui"]
            assert snapshot["frame_sequence"] == before_exit + 1
            assert snapshot["mode"] == "declarative"
            assert snapshot["view"]["title"] == "LAFVIN HAT"
        finally:
            await shell.stop()
            await ui.stop()
            await backend.stop()

    asyncio.run(scenario())
