from pathlib import Path

from lafvin_hat.runtime.ui import PillowRenderer
from lafvin_hat.ui import Canvas
from lafvin_hat.ui.fonts import (
    BUNDLED_HARMONYOS_SANS_SC,
    BUNDLED_NOTO_SANS_KR,
    bundled_font_paths,
    bundled_korean_font_paths,
    font_candidates,
    load_korean_ui_font,
    load_ui_font,
)


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_FONT = ROOT / BUNDLED_HARMONYOS_SANS_SC
BUNDLED_LICENSE = BUNDLED_FONT.parent / "LICENSE-update.txt"
BUNDLED_KOREAN_FONT = ROOT / BUNDLED_NOTO_SANS_KR
BUNDLED_KOREAN_LICENSE = BUNDLED_KOREAN_FONT.parent / "OFL.txt"


def test_bundled_harmony_font_is_the_default_candidate(monkeypatch) -> None:
    monkeypatch.delenv("LAFVIN_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("LAFVIN_UI_FONT", raising=False)
    monkeypatch.delenv("LAFVIN_UI_FONT_BOLD", raising=False)

    assert BUNDLED_FONT.is_file()
    assert BUNDLED_LICENSE.is_file()

    candidates = font_candidates()

    assert candidates[0] == BUNDLED_FONT
    assert any("NotoSansCJK-Regular.ttc" in str(path) for path in candidates)


def test_relative_font_override_resolves_against_project_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAFVIN_PROJECT_ROOT", str(tmp_path))

    candidates = font_candidates(font_path="fonts/custom.ttf")

    assert candidates[0] == tmp_path / "fonts" / "custom.ttf"


def test_harmony_variable_font_uses_regular_and_bold_weights() -> None:
    regular = load_ui_font(22, font_path=BUNDLED_FONT)
    medium = load_ui_font(22, font_path=BUNDLED_FONT, weight="Medium")
    bold = load_ui_font(22, bold=True, font_path=BUNDLED_FONT)

    regular_width = regular.getbbox("LAFVIN HAT")[2]
    medium_width = medium.getbbox("LAFVIN HAT")[2]
    bold_width = bold.getbbox("LAFVIN HAT")[2]

    assert regular_width < medium_width < bold_width


def test_bundled_noto_sans_kr_is_available_for_korean_message_bodies() -> None:
    assert BUNDLED_KOREAN_FONT.is_file()
    assert BUNDLED_KOREAN_LICENSE.is_file()
    assert bundled_korean_font_paths()[0] == BUNDLED_KOREAN_FONT

    font = load_korean_ui_font(19)

    assert font is not None
    assert font.getbbox("\uc548\ub155\ud558\uc138\uc694")[2] > 0


def test_toolkit_and_runtime_views_share_the_font_policy(monkeypatch) -> None:
    monkeypatch.delenv("LAFVIN_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("LAFVIN_UI_FONT", raising=False)
    monkeypatch.delenv("LAFVIN_UI_FONT_BOLD", raising=False)

    canvas = Canvas()
    renderer = PillowRenderer()

    assert canvas.title_font.getbbox("LAFVIN HAT")[2] > canvas.body_font.getbbox(
        "LAFVIN HAT"
    )[2]
    assert canvas.small_font.getbbox("LAFVIN HAT")[2] == load_ui_font(
        14,
        font_path=BUNDLED_FONT,
        weight="Medium",
    ).getbbox("LAFVIN HAT")[2]
    assert renderer.title_font.getbbox("LAFVIN HAT")[2] > renderer.body_font.getbbox(
        "LAFVIN HAT"
    )[2]
    assert renderer.menu_font.getbbox("LAFVIN HAT")[2] > renderer.body_font.getbbox(
        "LAFVIN HAT"
    )[2]
    assert bundled_font_paths()[0] == BUNDLED_FONT
