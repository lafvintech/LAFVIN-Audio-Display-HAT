from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "system_status" / "main.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "lafvin_system_status_app",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_system_status_app_formats_runtime_snapshot() -> None:
    app = _load_module()

    rows = app.status_rows(
        {
            "uptime_ms": 12_000,
            "system": {
                "runtime": {"uptime_ms": 12_000},
                "device": {
                    "model": "Raspberry Pi Zero 2 W Rev 1.0",
                    "temperature_c": 42.5,
                },
                "network": {"ip_address": "192.0.2.10"},
                "apps": {"installed_count": 6},
                "storage": {
                    "used_bytes": 5 * 1024 ** 3,
                    "total_bytes": 32 * 1024 ** 3,
                },
            },
        }
    )

    message = "\n".join(f"{row.label}:{row.value}" for row in rows)
    assert "Runtime:12s" in message
    assert "Model:RPI Zero 2 W" in message
    assert "IP:192.0.2.10" in message
    assert "APP:6" in message
    assert "Temp:42.5C" in message
    assert "Storage:5.0/32G" in message
