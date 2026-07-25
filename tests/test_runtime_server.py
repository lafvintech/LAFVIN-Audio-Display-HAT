import asyncio
import sys
from pathlib import Path

import pytest
import yaml

from lafvin_hat.runtime.ipc import server as ipc_server
from lafvin_hat.runtime.config import RuntimeEndpoint
from lafvin_hat.runtime.audio.backends import LinuxAudioBackend
from lafvin_hat.runtime.backends import LafvinHatBackend
from lafvin_hat.runtime.ipc.server import RuntimeServer
from lafvin_hat.runtime.system_apps import HARDWARE_TEST_APP_ID
from lafvin_hat.sdk import RuntimeClient, RuntimeClientError


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_ping_over_tcp() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        try:
            client = RuntimeClient(server.bound_endpoint)
            result = await client.ping()
        finally:
            await server.close()

        assert result == {
            "service": "lafvin-hat-runtime",
            "protocol_version": 1,
        }

    asyncio.run(scenario())


def test_lafvin_hat_backend_selects_linux_audio_without_name_matching() -> None:
    server = RuntimeServer(
        RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0),
        backend=LafvinHatBackend(),
    )

    assert isinstance(server._audio_service._backend, LinuxAudioBackend)


def test_runtime_reports_unknown_method() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        try:
            client = RuntimeClient(server.bound_endpoint)
            with pytest.raises(RuntimeClientError) as exc_info:
                await client.request("runtime.missing")
        finally:
            await server.close()

        assert exc_info.value.code == "METHOD_NOT_FOUND"

    asyncio.run(scenario())


def test_runtime_status_contains_uptime() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        try:
            client = RuntimeClient(server.bound_endpoint)
            result = await client.request("runtime.status")
        finally:
            await server.close()

        assert result["state"] == "running"
        assert result["uptime_ms"] >= 0
        assert result["foreground_app_id"] is None
        assert result["shell"]["active"] is True
        assert result["gestures"]["context"] == "home"
        assert result["ui"]["view"]["kind"] == "list"
        assert result["backend"]["display_metrics"]["present_count"] >= 1

    asyncio.run(scenario())


def test_runtime_diagnostic_audio_endpoints_use_system_audio_owner() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        try:
            client = RuntimeClient(server.bound_endpoint)
            changed = await client.request(
                "diagnostics.audio.volume.set",
                {"value": 65},
            )
            assert changed == {"value": 65}

            status = await client.request("runtime.status")
            assert status["audio"]["volume"] == 65

            tone = await client.request(
                "diagnostics.audio.tone.play",
                {"frequency_hz": 440, "duration_ms": 100},
            )
            assert tone["completed"] is True
            assert tone["frequency_hz"] == 440
            assert tone["duration_ms"] == 100
        finally:
            await server.close()

    asyncio.run(scenario())


def test_runtime_diagnostic_tone_rejects_invalid_duration() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        try:
            client = RuntimeClient(server.bound_endpoint)
            with pytest.raises(RuntimeClientError) as exc_info:
                await client.request(
                    "diagnostics.audio.tone.play",
                    {"duration_ms": 99},
                )
        finally:
            await server.close()

        assert exc_info.value.code == "INVALID_REQUEST"

    asyncio.run(scenario())


def test_runtime_diagnostic_reference_audio_uses_checkout_asset(
    monkeypatch,
    tmp_path: Path,
) -> None:
    reference = tmp_path / "assets" / "audio" / "audio_test.wav"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"test wav fixture")
    monkeypatch.setattr(ipc_server, "default_project_root", lambda: tmp_path)

    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        try:
            client = RuntimeClient(server.bound_endpoint)
            result = await client.request("diagnostics.audio.reference.play")
        finally:
            await server.close()

        assert result["completed"] is True
        assert result["resource"] == "assets/audio/audio_test.wav"

    asyncio.run(scenario())


def test_runtime_home_single_click_changes_selection() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        client = RuntimeClient(server.bound_endpoint)
        try:
            await client.request(
                "app.install",
                {
                    "source_path": str(ROOT / "apps" / "system_volume"),
                    "development": True,
                },
            )
            initial = await client.request("runtime.status")
            assert initial["shell"]["selected"] == 0

            await client.request(
                "simulator.button.set",
                {"pressed": True},
            )
            await client.request(
                "simulator.button.set",
                {"pressed": False},
            )
            await asyncio.sleep(0.4)

            status = await client.request("runtime.status")
            assert status["shell"]["selected"] == 1
            assert (
                status["shell"]["selected_item_id"]
                == "dev.lafvin.system-volume"
            )
            assert status["ui"]["view"]["selected"] == 1
            assert (
                status["gestures"]["last_event"]["name"]
                == "button.single_clicked"
            )
        finally:
            await server.close()

    asyncio.run(scenario())


def test_runtime_home_double_click_starts_hardware_test_without_moving() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        client = RuntimeClient(server.bound_endpoint)
        try:
            for pressed in (True, False, True, False):
                await client.request(
                    "simulator.button.set",
                    {"pressed": pressed},
                )

            await asyncio.sleep(0.05)
            status = await client.request("runtime.status")
            assert status["shell"]["selected"] == 0
            assert (
                status["shell"]["last_confirmed_id"]
                == HARDWARE_TEST_APP_ID
            )
            assert status["shell"]["mode"] == "system_app"
            assert status["system_apps"]["active_app_id"] == HARDWARE_TEST_APP_ID
            assert status["diagnostics"]["active"] is True
            assert status["diagnostics"]["phase"] in {
                "starting",
                "lcd",
                "rgb",
            }
            assert (
                status["gestures"]["last_event"]["name"]
                == "button.double_clicked"
            )
        finally:
            await server.close()

    asyncio.run(scenario())


def test_runtime_shell_launches_app_and_triple_click_returns_home(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        app_dir = tmp_path / "shell-app"
        app_dir.mkdir()
        ready_path = app_dir / "ready"
        (app_dir / "app.py").write_text(
            "\n".join(
                [
                    "import asyncio",
                    "from pathlib import Path",
                    "from lafvin_hat.sdk import DeviceApp",
                    "",
                    "async def main():",
                    "    app = await DeviceApp.connect_from_environment()",
                    "    await app.acquire_foreground()",
                    "    await app.ui.set_view({",
                    "        'kind': 'text',",
                    "        'title': 'Shell Launch',",
                    "        'text': 'App launched from Home',",
                    "    })",
                    "    Path('ready').write_text('ready', encoding='utf-8')",
                    "    stream = app.subscribe(events=['app.exit_requested'])",
                    "    await anext(stream)",
                    "    await stream.aclose()",
                    "    await app.close()",
                    "",
                    "asyncio.run(main())",
                ]
            ),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "id": "dev.lafvin.shell-test",
            "name": "Shell Test",
            "version": "0.1.0",
            "entrypoint": {
                "executable": Path(sys.executable).name,
                "args": ["app.py"],
                "working_directory": ".",
            },
            "permissions": ["display.declarative", "button"],
            "ui": {"mode": "declarative"},
            "lifecycle": {
                "startup_timeout_sec": 10,
                "exit_timeout_sec": 2,
                "restart": "never",
                "max_restarts": 0,
            },
        }
        (app_dir / "manifest.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False),
            encoding="utf-8",
        )

        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        client = RuntimeClient(server.bound_endpoint)

        async def pulse() -> None:
            await client.request("simulator.button.set", {"pressed": True})
            await client.request("simulator.button.set", {"pressed": False})

        try:
            await client.request(
                "app.install",
                {"source_path": str(app_dir), "development": True},
            )
            for _ in range(1):
                await pulse()
                await asyncio.sleep(0.25)
            status = await client.request("runtime.status")
            assert status["shell"]["selected_item_id"] == manifest["id"]

            await pulse()
            await pulse()
            for _ in range(200):
                if ready_path.exists():
                    break
                await asyncio.sleep(0.02)
            assert ready_path.exists()
            status = await client.request("runtime.status")
            assert status["foreground_app_id"] == manifest["id"]
            assert status["shell"]["active"] is False

            await pulse()
            await pulse()
            await pulse()
            apps = []
            for _ in range(200):
                apps = (await client.request("app.list"))["apps"]
                if apps[0]["state"] == "stopped":
                    break
                await asyncio.sleep(0.02)
            assert apps[0]["state"] == "stopped"
            status = await client.request("runtime.status")
            assert status["foreground_app_id"] is None
            assert status["shell"]["active"] is True
        finally:
            await server.close()

    asyncio.run(scenario())


def test_runtime_launches_system_volume_app_and_updates_volume() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        client = RuntimeClient(server.bound_endpoint)

        async def pulse() -> None:
            await client.request("simulator.button.set", {"pressed": True})
            await client.request("simulator.button.set", {"pressed": False})

        try:
            await client.request(
                "app.install",
                {
                    "source_path": str(ROOT / "apps" / "system_volume"),
                    "development": True,
                },
            )

            for _ in range(1):
                await pulse()
                await asyncio.sleep(0.25)
            status = await client.request("runtime.status")
            assert (
                status["shell"]["selected_item_id"]
                == "dev.lafvin.system-volume"
            )

            await pulse()
            await pulse()
            status = {}
            for _ in range(200):
                status = await client.request("runtime.status")
                if (
                    status["foreground_app_id"]
                    == "dev.lafvin.system-volume"
                    and status["frame"]["owner_app_id"]
                    == "dev.lafvin.system-volume"
                    and status["backend"]["ui"]["mode"] == "raw_frame"
                    and status["frame"]["metrics"]["commit_count"] > 0
                ):
                    break
                await asyncio.sleep(0.02)
            assert status["foreground_app_id"] == "dev.lafvin.system-volume"
            assert status["shell"]["active"] is False
            assert status["ui"]["view"] is None
            assert status["frame"]["active"] is True
            assert (
                status["frame"]["owner_app_id"]
                == "dev.lafvin.system-volume"
            )
            assert status["backend"]["ui"]["mode"] == "raw_frame"
            assert status["system"]["audio"]["volume"] == 70
            initial_commits = status["frame"]["metrics"]["commit_count"]

            await pulse()
            await pulse()

            for _ in range(200):
                status = await client.request("runtime.status")
                if (
                    status["system"]["audio"]["volume"] == 80
                    and status["frame"]["metrics"]["commit_count"]
                    > initial_commits
                ):
                    break
                await asyncio.sleep(0.02)
            assert status["system"]["audio"]["volume"] == 80
            assert (
                status["frame"]["metrics"]["commit_count"]
                > initial_commits
            )

            await pulse()
            await asyncio.sleep(0.05)
            await pulse()
            await asyncio.sleep(0.05)
            await pulse()
            await asyncio.sleep(0.05)

            status = await client.request("runtime.status")
            for _ in range(200):
                apps = (await client.request("app.list"))["apps"]
                if apps[0]["state"] == "stopped":
                    break
                await asyncio.sleep(0.02)
            status = await client.request("runtime.status")
            assert status["foreground_app_id"] is None
            assert status["shell"]["active"] is True
            assert status["system"]["audio"]["volume"] == 80
            assert status["ui"]["view"]["title"] == "LAFVIN HAT"
        finally:
            await server.close()

    asyncio.run(scenario())


def test_runtime_launches_system_status_app_and_triple_click_returns_home() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        client = RuntimeClient(server.bound_endpoint)

        async def pulse() -> None:
            await client.request("simulator.button.set", {"pressed": True})
            await client.request("simulator.button.set", {"pressed": False})

        try:
            await client.request(
                "app.install",
                {
                    "source_path": str(ROOT / "apps" / "system_status"),
                    "development": True,
                },
            )

            for _ in range(1):
                await pulse()
                await asyncio.sleep(0.25)
            status = await client.request("runtime.status")
            assert (
                status["shell"]["selected_item_id"]
                == "dev.lafvin.system-status"
            )

            await pulse()
            await pulse()
            status = {}
            for _ in range(200):
                status = await client.request("runtime.status")
                if (
                    status["foreground_app_id"]
                    == "dev.lafvin.system-status"
                    and status["frame"]["owner_app_id"]
                    == "dev.lafvin.system-status"
                    and status["backend"]["ui"]["mode"] == "raw_frame"
                    and status["frame"]["metrics"]["commit_count"] > 0
                ):
                    break
                await asyncio.sleep(0.02)
            assert status["foreground_app_id"] == "dev.lafvin.system-status"
            assert status["shell"]["active"] is False
            assert status["ui"]["view"] is None
            assert status["frame"]["active"] is True
            assert (
                status["frame"]["owner_app_id"]
                == "dev.lafvin.system-status"
            )
            assert status["backend"]["ui"]["mode"] == "raw_frame"

            await pulse()
            await asyncio.sleep(0.05)
            await pulse()
            await asyncio.sleep(0.05)
            await pulse()
            await asyncio.sleep(0.05)
            status = await client.request("runtime.status")
            for _ in range(200):
                apps = (await client.request("app.list"))["apps"]
                if apps[0]["state"] == "stopped":
                    break
                await asyncio.sleep(0.02)
            status = await client.request("runtime.status")
            assert status["foreground_app_id"] is None
            assert status["shell"]["active"] is True
            assert status["ui"]["view"]["title"] == "LAFVIN HAT"
        finally:
            await server.close()

    asyncio.run(scenario())


def test_runtime_streams_simulator_button_event() -> None:
    async def scenario() -> None:
        server = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0)
        )
        await server.start()
        event_client = RuntimeClient(server.bound_endpoint)
        command_client = RuntimeClient(server.bound_endpoint)
        stream = event_client.subscribe(events=["button.raw_pressed"])
        next_event = asyncio.create_task(anext(stream))
        try:
            await asyncio.sleep(0.05)
            await command_client.request(
                "simulator.button.set",
                {"pressed": True},
            )
            event = await asyncio.wait_for(next_event, timeout=2)
            assert event["event"] == "button.raw_pressed"
            assert event["payload"] == {"pressed": True}
        finally:
            if not next_event.done():
                next_event.cancel()
                await asyncio.gather(next_event, return_exceptions=True)
            await stream.aclose()
            await server.close()

    asyncio.run(scenario())
