from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


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
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _status() -> dict:
    return {
        "uptime_ms": (12 * 24 + 8) * 60 * 60 * 1000,
        "system": {
            "runtime": {"uptime_ms": (12 * 24 + 8) * 60 * 60 * 1000},
            "device": {
                "model": "Raspberry Pi 5 Model B Rev 1.0",
                "hostname": "lafvin-pi",
                "temperature_c": 52.0,
            },
            "network": {"ip_address": "192.168.1.108"},
            "apps": {"installed_count": 7},
            "resources": {
                "cpu": {"usage_percent": 34.2},
                "memory": {"usage_percent": 48.1},
            },
            "storage": {
                "used_bytes": 61,
                "total_bytes": 100,
                "usage_percent": 61.0,
            },
        },
    }


def test_system_monitor_formats_all_four_metrics() -> None:
    app = _load_module()

    metrics = app.monitor_metrics(_status())

    assert [(metric.label, metric.value) for metric in metrics] == [
        ("CPU", "34%"),
        ("MEMORY", "48%"),
        ("TEMP °C", "52"),
        ("STORAGE", "61%"),
    ]
    assert metrics[3].accent == app.STORAGE_ACCENT
    assert metrics[3].progress == 0.61


def test_device_info_page_formats_rows_and_long_uptime() -> None:
    app = _load_module()

    rows = app.device_info_rows(_status())

    assert [(row.label, row.value) for row in rows] == [
        ("Runtime", "12d 08h"),
        ("Model", "RPI 5 Model B"),
        ("IP", "192.168.1.108"),
        ("Apps", "7"),
        ("Host", "lafvin-pi"),
    ]


def test_monitor_uses_purple_storage_accent_and_first_page_indicator() -> None:
    app = _load_module()
    canvas = app.Canvas(width=240, height=280)

    app.render_monitor_page(canvas, _status())

    assert app.STORAGE_ACCENT in set(canvas.image.getdata())
    assert canvas.image.getpixel((109, 262)) == canvas.theme.button_selected
    assert canvas.image.getpixel((131, 262)) == canvas.theme.background


def test_device_info_uses_black_labels_and_second_page_indicator() -> None:
    app = _load_module()
    canvas = app.Canvas(width=240, height=280)

    app.render_device_info_page(canvas, _status())

    label_area = canvas.image.crop((8, 50, 80, 84))
    assert canvas.theme.text in set(label_area.getdata())
    assert canvas.image.getpixel((109, 262)) == canvas.theme.background
    assert canvas.image.getpixel((131, 262)) == canvas.theme.button_selected


def test_missing_resource_values_use_placeholders() -> None:
    app = _load_module()

    metrics = app.monitor_metrics({"system": {}})

    assert [metric.value for metric in metrics] == ["--", "--", "--", "--"]
    assert all(metric.progress is None for metric in metrics)


def test_system_status_app_shortens_supported_pi_model_names() -> None:
    app = _load_module()

    assert app._short_model("Raspberry Pi 4 Model B Rev 1.5") == "RPI 4 Model B"
    assert (
        app._short_model("Raspberry Pi 3 Model B Plus Rev 1.3")
        == "RPI 3 Model B Plus"
    )
