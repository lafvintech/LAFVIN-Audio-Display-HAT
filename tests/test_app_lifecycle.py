import asyncio
import sys
from pathlib import Path

import yaml

from lafvin_hat.runtime.config import RuntimeEndpoint
from lafvin_hat.runtime.ipc.server import RuntimeServer
from lafvin_hat.sdk import RuntimeClient


def test_development_app_lifecycle(tmp_path: Path) -> None:
    async def scenario() -> None:
        app_dir = tmp_path / "demo-app"
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
                    "        'title': 'Lifecycle Test',",
                    "        'text': 'Runtime UI is ready',",
                    "        'status': 'idle',",
                    "    })",
                    "    stream = app.subscribe(events=['app.exit_requested'])",
                    "    event_task = asyncio.create_task(anext(stream))",
                    "    await asyncio.sleep(0.05)",
                    "    Path('ready').write_text('ready', encoding='utf-8')",
                    "    event = await event_task",
                    "    assert event['event'] == 'app.exit_requested'",
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
            "id": "dev.lafvin.lifecycle-test",
            "name": "Lifecycle Test",
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
        try:
            installed = await client.request(
                "app.install",
                {"source_path": str(app_dir), "development": True},
            )
            assert installed["state"] == "installed"

            launched = await client.request(
                "app.launch",
                {"app_id": manifest["id"]},
            )
            assert launched["state"] == "starting"

            for _ in range(200):
                if ready_path.exists():
                    break
                await asyncio.sleep(0.02)
            assert ready_path.exists()

            status = await client.request("runtime.status")
            assert status["foreground_app_id"] == manifest["id"]
            assert status["ui"]["owner_app_id"] == manifest["id"]
            assert status["ui"]["view"]["kind"] == "text"
            assert status["backend"]["ui"]["view"]["text"] == (
                "Runtime UI is ready"
            )
            assert status["backend"]["ui"]["frame_sequence"] >= 2

            await client.request(
                "app.stop",
                {"app_id": manifest["id"]},
            )
            apps = []
            for _ in range(100):
                apps = (await client.request("app.list"))["apps"]
                if apps[0]["state"] == "stopped":
                    break
                await asyncio.sleep(0.02)
            assert apps[0]["state"] == "stopped"
            assert apps[0]["foreground"] is False
            assert apps[0]["exit_code"] == 0
            status = await client.request("runtime.status")
            assert status["ui"]["owner_app_id"] is None
            assert status["ui"]["view"]["kind"] == "list"
            assert status["shell"]["active"] is True
        finally:
            await server.close()

    asyncio.run(scenario())
