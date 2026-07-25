from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lafvin_test_chatbot",
    ROOT / "apps" / "chatbot" / "main.py",
)
assert SPEC is not None and SPEC.loader is not None
chatbot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chatbot)

TRANSLATOR_SPEC = importlib.util.spec_from_file_location(
    "lafvin_test_translator",
    ROOT / "apps" / "translator" / "main.py",
)
assert TRANSLATOR_SPEC is not None and TRANSLATOR_SPEC.loader is not None
translator = importlib.util.module_from_spec(TRANSLATOR_SPEC)
TRANSLATOR_SPEC.loader.exec_module(translator)


class _UI:
    def __init__(self) -> None:
        self.views: list[dict] = []
        self.patches: list[list[dict]] = []

    async def set_view(self, view: dict) -> None:
        self.views.append(view)

    async def patch_view(self, operations: list[dict]) -> None:
        self.patches.append(operations)
        for operation in operations:
            if (
                operation["op"] == "replace"
                and operation["path"] == "/selected"
                and self.views
            ):
                self.views[-1]["selected"] = operation["value"]


class _Audio:
    async def start_recording(self, *, max_duration_sec: int):
        raise RuntimeError("capture device unavailable")


class _Frame:
    width = 240
    height = 280

    def __init__(self) -> None:
        self.data = b""
        self.commits = 0

    def write(self, frame: bytes) -> None:
        self.data = frame

    async def commit(self) -> dict:
        self.commits += 1
        return {"next_sequence": self.commits + 1}


class _Frames:
    def __init__(self, frame: _Frame) -> None:
        self.frame = frame

    async def acquire(self) -> _Frame:
        return self.frame


class _App:
    def __init__(self) -> None:
        self.frame = _Frame()
        self.frames = _Frames(self.frame)
        self.ui = _UI()
        self.audio = _Audio()
        self.closed = False

    async def acquire_foreground(self) -> None:
        return None

    async def subscribe(self, *, events: list[str]):
        yield {"event": "button.raw_pressed"}
        await asyncio.sleep(chatbot.HOLD_THRESHOLD_SEC + 0.05)
        yield {"event": "app.exit_requested"}

    async def close(self) -> None:
        self.closed = True


def test_recording_start_failure_does_not_crash_chatbot(
    monkeypatch,
    tmp_path,
) -> None:
    app = _App()

    async def connect(*, timeout: int):
        return app

    monkeypatch.setenv("LAFVIN_AI_PROVIDER", "fake")
    monkeypatch.setattr(
        chatbot.DeviceApp,
        "connect_from_environment",
        connect,
    )
    monkeypatch.setattr(
        chatbot,
        "configure_ai_logging",
        lambda *args, **kwargs: tmp_path / "chatbot.log",
    )

    asyncio.run(chatbot.main())

    assert app.closed is True
    assert app.frame.commits >= 2
    assert app.frame.data


class _SequenceApp:
    def __init__(
        self,
        app_module,
        events: list[dict],
    ) -> None:
        self.app_module = app_module
        self.events = events
        self.frame = _Frame()
        self.frames = _Frames(self.frame)
        self.ui = _UI()
        self.audio = _Audio()
        self.closed = False

    async def acquire_foreground(self) -> None:
        return None

    async def subscribe(self, *, events: list[str]):
        for event in self.events:
            delay = event.pop("_delay", 0)
            if delay:
                await asyncio.sleep(delay)
            yield event

    async def close(self) -> None:
        self.closed = True


def _short_click() -> list[dict]:
    return [
        {"event": "button.raw_pressed"},
        {"event": "button.raw_released"},
    ]


@pytest.mark.parametrize("app_module", [chatbot, translator])
def test_voice_app_short_click_toggles_between_actions(
    monkeypatch,
    tmp_path,
    app_module,
) -> None:
    events = [
        *_short_click(),
        {"event": "button.raw_pressed", "_delay": app_module.CLICK_INTERVAL_SEC + 0.05},
        {"event": "button.raw_released"},
        {"event": "app.exit_requested", "_delay": app_module.CLICK_INTERVAL_SEC + 0.05},
    ]
    app = _SequenceApp(app_module, events)

    async def connect(*, timeout: int):
        return app

    monkeypatch.setenv("LAFVIN_AI_PROVIDER", "fake")
    monkeypatch.setattr(app_module.DeviceApp, "connect_from_environment", connect)
    monkeypatch.setattr(
        app_module,
        "configure_ai_logging",
        lambda *args, **kwargs: tmp_path / "app.log",
    )
    selected_values: list[int] = []
    display_class = (
        chatbot.ChatbotDisplay
        if app_module is chatbot
        else translator.TranslatorDisplay
    )
    original_set_selected = display_class.set_selected

    async def record_set_selected(self, index: int) -> None:
        selected_values.append(index)
        await original_set_selected(self, index)

    monkeypatch.setattr(
        display_class,
        "set_selected",
        record_set_selected,
    )

    asyncio.run(app_module.main())

    assert selected_values[:2] == [
        app_module.ACTION_BACK,
        app_module.ACTION_TALK,
    ]


@pytest.mark.parametrize("app_module", [chatbot, translator])
def test_voice_app_double_click_on_back_exits(
    monkeypatch,
    tmp_path,
    app_module,
) -> None:
    events = [
        *_short_click(),
        {"event": "button.raw_pressed", "_delay": app_module.CLICK_INTERVAL_SEC + 0.05},
        {"event": "button.raw_released"},
        {"event": "button.raw_pressed", "_delay": 0.05},
        {"event": "button.raw_released"},
    ]
    app = _SequenceApp(app_module, events)

    async def connect(*, timeout: int):
        return app

    monkeypatch.setenv("LAFVIN_AI_PROVIDER", "fake")
    monkeypatch.setattr(app_module.DeviceApp, "connect_from_environment", connect)
    monkeypatch.setattr(
        app_module,
        "configure_ai_logging",
        lambda *args, **kwargs: tmp_path / "app.log",
    )

    asyncio.run(app_module.main())

    assert app.closed is True
