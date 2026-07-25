import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lafvin_test_one_button_jump",
    ROOT / "apps" / "one_button_jump" / "main.py",
)
assert SPEC is not None and SPEC.loader is not None
one_button_jump = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(one_button_jump)


def test_game_over_single_click_toggles_menu_selection() -> None:
    game = one_button_jump.Game()
    game.game_over = True

    assert game.release(1.000) is None
    assert game.menu_selected == 0

    game.advance_menu(1.001 + one_button_jump.MENU_CLICK_INTERVAL)

    assert game.menu_selected == 1


def test_game_over_double_click_confirms_continue() -> None:
    game = one_button_jump.Game()
    game.game_over = True

    assert game.release(1.000) is None
    assert game.release(1.300) == "continue"


def test_game_over_double_click_confirms_exit_after_selection() -> None:
    game = one_button_jump.Game()
    game.game_over = True
    game.menu_selected = 1

    assert game.release(1.000) is None
    assert game.release(1.300) == "exit"


def test_game_over_frame_contains_menu_panel() -> None:
    game = one_button_jump.Game()
    game.game_over = True

    frame = one_button_jump.rgb565_frame(game)

    assert len(frame) == one_button_jump.WIDTH * one_button_jump.HEIGHT * 2
    assert frame != bytes(len(frame))
