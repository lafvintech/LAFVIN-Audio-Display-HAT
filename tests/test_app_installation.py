import asyncio
import sys
from pathlib import Path

import yaml

from lafvin_hat.runtime.config import RuntimeEndpoint
from lafvin_hat.runtime.ipc.server import RuntimeServer
from lafvin_hat.sdk import RuntimeClient


def _write_app(app_dir: Path) -> None:
    app_dir.mkdir()
    (app_dir / "main.py").write_text(
        "print('persistent app output', flush=True)\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "id": "dev.lafvin.persistent-test",
        "name": "Persistent Test",
        "version": "0.1.0",
        "entrypoint": {
            "executable": Path(sys.executable).name,
            "args": ["main.py"],
            "working_directory": ".",
        },
        "permissions": ["display.declarative"],
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


def test_persistent_install_survives_runtime_restart(tmp_path: Path) -> None:
    async def scenario() -> None:
        source_dir = tmp_path / "source"
        data_dir = tmp_path / "data"
        log_dir = tmp_path / "logs"
        _write_app(source_dir)

        first = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0),
            data_dir=data_dir,
            log_dir=log_dir,
        )
        await first.start()
        first_client = RuntimeClient(first.bound_endpoint)
        installed = await first_client.request(
            "app.install",
            {"source_path": str(source_dir), "development": False},
        )
        assert installed["development"] is False
        installed_dir = data_dir / "apps" / installed["id"]
        assert installed_dir.is_dir()
        await first.close()

        (source_dir / "main.py").write_text(
            "print('changed source', flush=True)\n",
            encoding="utf-8",
        )

        second = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0),
            data_dir=data_dir,
            log_dir=log_dir,
        )
        await second.start()
        second_client = RuntimeClient(second.bound_endpoint)
        try:
            apps = (await second_client.request("app.list"))["apps"]
            assert [app["id"] for app in apps] == [installed["id"]]

            await second_client.request(
                "app.launch",
                {"app_id": installed["id"]},
            )
            for _ in range(100):
                apps = (await second_client.request("app.list"))["apps"]
                if apps[0]["state"] == "stopped":
                    break
                await asyncio.sleep(0.02)
            assert apps[0]["exit_code"] == 0

            logs = await second_client.request(
                "app.logs",
                {"app_id": installed["id"], "lines": 20},
            )
            assert "persistent app output" in "\n".join(logs["lines"])
            assert "changed source" not in "\n".join(logs["lines"])

            await second_client.request(
                "app.uninstall",
                {"app_id": installed["id"]},
            )
            assert not installed_dir.exists()
        finally:
            await second.close()

        third = RuntimeServer(
            RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=0),
            data_dir=data_dir,
            log_dir=log_dir,
        )
        await third.start()
        try:
            third_client = RuntimeClient(third.bound_endpoint)
            assert (await third_client.request("app.list"))["apps"] == []
        finally:
            await third.close()

    asyncio.run(scenario())
