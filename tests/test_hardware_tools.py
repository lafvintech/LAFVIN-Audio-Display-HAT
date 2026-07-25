from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lafvin_hardware_test_tool",
    ROOT / "tools" / "hardware_test.py",
)
assert SPEC is not None and SPEC.loader is not None
hardware_test = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hardware_test)


def test_parse_wm8960_card_index() -> None:
    value = """
 0 [vc4hdmi0      ]: vc4-hdmi - vc4-hdmi-0
 2 [wm8960soundcard]: wm8960-soundcard - wm8960-soundcard
"""

    assert hardware_test._parse_wm8960_card(value) == "2"


def test_parse_wm8960_card_returns_none_when_missing() -> None:
    value = " 0 [vc4hdmi0]: vc4-hdmi - vc4-hdmi-0"

    assert hardware_test._parse_wm8960_card(value) is None


def test_display_test_enables_backlight(monkeypatch) -> None:
    class Backlight:
        def __init__(self) -> None:
            self.values: list[int] = []

        def set(self, value: int) -> None:
            self.values.append(value)

    class Display:
        def __init__(self) -> None:
            self.colors: list[int] = []

        def fill_rgb565(self, color: int) -> None:
            self.colors.append(color)

    class Board:
        def __init__(self) -> None:
            self.backlight = Backlight()
            self.display = Display()

    board = Board()
    monkeypatch.setattr(hardware_test.time, "sleep", lambda _value: None)
    monkeypatch.setattr(hardware_test, "_confirm", lambda _prompt: True)

    assert hardware_test._test_display(board) is True
    assert board.backlight.values == [100]
    assert board.display.colors == [0xF800, 0x07E0, 0x001F, 0x0000]
