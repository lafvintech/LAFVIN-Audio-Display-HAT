import importlib.util
import random
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


def test_score_layout_stays_clear_of_continue_option() -> None:
    score_height = (
        len(one_button_jump._GLYPHS["0"])
        * one_button_jump.GAME_OVER_SCORE_SCALE
    )
    score_bottom = one_button_jump.GAME_OVER_SCORE_Y + score_height
    continue_highlight_top = one_button_jump.GAME_OVER_OPTIONS[0][1] - 5

    assert one_button_jump.HUD_SCORE_X > 8
    assert score_bottom < continue_highlight_top


def test_obstacles_spawn_near_right_edge_with_random_spacing() -> None:
    game = one_button_jump.Game(random.Random(12345))
    spawn_positions = [game.obstacles[0]]
    spacings = [game._distance_until_next_obstacle]

    for _ in range(8):
        game._distance_until_next_obstacle = 0.0
        game.update(0.0)
        spawn_positions.append(game.obstacles[-1])
        spacings.append(game._distance_until_next_obstacle)

    minimum_x = (
        one_button_jump.WIDTH
        + one_button_jump.OBSTACLE_SPAWN_OFFSET_MIN
    )
    maximum_x = (
        one_button_jump.WIDTH
        + one_button_jump.OBSTACLE_SPAWN_OFFSET_MAX
    )
    assert all(minimum_x <= position <= maximum_x for position in spawn_positions)
    assert all(
        one_button_jump.OBSTACLE_SPACING_MIN
        <= spacing
        <= one_button_jump.OBSTACLE_SPACING_MAX
        for spacing in spacings
    )
    assert len(set(spawn_positions)) > 1
    assert len(set(spacings)) > 1


def test_passing_multiple_obstacles_scores_each_one() -> None:
    game = one_button_jump.Game(random.Random(1))
    game.obstacles = [
        -one_button_jump.OBSTACLE_WIDTH - 1,
        -one_button_jump.OBSTACLE_WIDTH - 10,
        180.0,
    ]

    game.update(0.0)

    assert game.score == 2
    assert game.obstacles == [180.0]


def test_obstacle_speed_uses_score_milestones() -> None:
    game = one_button_jump.Game(random.Random(1))

    game.score = 14
    assert game.obstacle_speed() == one_button_jump.BASE_OBSTACLE_SPEED

    game.score = 15
    assert game.obstacle_speed() == one_button_jump.BASE_OBSTACLE_SPEED * 1.3

    game.score = 29
    assert game.obstacle_speed() == one_button_jump.BASE_OBSTACLE_SPEED * 1.3

    game.score = 30
    assert game.obstacle_speed() == one_button_jump.BASE_OBSTACLE_SPEED * 1.5
