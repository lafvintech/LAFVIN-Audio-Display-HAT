import importlib.util
import random
from pathlib import Path

from lafvin_hat.ui import Canvas


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lafvin_test_one_button_jump",
    ROOT / "apps" / "one_button_jump" / "main.py",
)
assert SPEC is not None and SPEC.loader is not None
one_button_jump = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(one_button_jump)


def test_ready_press_starts_game_with_immediate_jump() -> None:
    game = one_button_jump.Game(random.Random(1))

    assert game.state == one_button_jump.STATE_READY

    game.press()
    game.update(0.05)

    assert game.state == one_button_jump.STATE_RUNNING
    assert game.player_y < one_button_jump.DINO_REST_Y
    assert game.velocity < 0


def test_press_while_airborne_does_not_request_second_jump() -> None:
    game = one_button_jump.Game(random.Random(1))
    game.press()
    game.update(0.05)

    game.press()

    assert game.grounded is False
    assert game.jump_requested is False


def test_jump_has_tall_arc_and_long_airborne_travel() -> None:
    game = one_button_jump.Game(random.Random(1))
    game.state = one_button_jump.STATE_RUNNING
    game.obstacles = [one_button_jump.Obstacle(x=1000.0, variant=0)]
    game._distance_until_next_obstacle = 1000.0
    minimum_y = game.player_y

    game.press()
    elapsed = 0.0
    while elapsed < 2.0:
        game.update(1 / 120)
        elapsed += 1 / 120
        minimum_y = min(minimum_y, game.player_y)
        if elapsed > 0.1 and game.grounded:
            break

    jump_height = one_button_jump.DINO_REST_Y - minimum_y

    assert jump_height >= 80
    assert elapsed >= 1.0
    assert game.world_distance >= 90


def test_game_over_single_click_retries_after_input_guard() -> None:
    game = one_button_jump.Game(random.Random(1))
    game.state = one_button_jump.STATE_GAME_OVER
    game.state_elapsed = one_button_jump.GAME_OVER_RETRY_DELAY - 0.01
    game.score = 7
    game.high_score = 7

    assert game.retry() is False

    game.update(0.02)

    assert game.retry() is True
    assert game.state == one_button_jump.STATE_RUNNING
    assert game.score == 0
    assert game.high_score == 7


def test_event_contract_uses_raw_press_retry_and_runtime_exit() -> None:
    game = one_button_jump.Game(random.Random(1))

    assert one_button_jump.handle_event(game, "button.raw_pressed") is None
    assert game.state == one_button_jump.STATE_RUNNING

    game.state = one_button_jump.STATE_GAME_OVER
    game.state_elapsed = one_button_jump.GAME_OVER_RETRY_DELAY
    assert one_button_jump.handle_event(game, "button.single_clicked") is None
    assert game.state == one_button_jump.STATE_RUNNING

    assert one_button_jump.handle_event(game, "app.exit_requested") == "exit"


def test_game_frame_is_rendered_by_toolkit_canvas() -> None:
    game = one_button_jump.Game(random.Random(1))
    canvas = Canvas(
        width=one_button_jump.WIDTH,
        height=one_button_jump.HEIGHT,
        theme=one_button_jump.DINO_THEME,
    )

    rendered = one_button_jump.render_game(canvas, game)
    frame = rendered.render()

    assert rendered is canvas
    assert len(frame) == one_button_jump.WIDTH * one_button_jump.HEIGHT * 2
    assert canvas.theme.background in set(canvas.image.getdata())
    assert canvas.theme.text in set(canvas.image.getdata())


def test_game_over_frame_contains_overlay_and_failed_dino() -> None:
    game = one_button_jump.Game(random.Random(1))
    game.state = one_button_jump.STATE_GAME_OVER
    canvas = Canvas(
        width=one_button_jump.WIDTH,
        height=one_button_jump.HEIGHT,
        theme=one_button_jump.DINO_THEME,
    )

    one_button_jump.render_game(canvas, game)

    colors = set(canvas.image.getdata())
    assert canvas.theme.danger in colors
    assert canvas.theme.text in colors


def test_obstacles_spawn_near_right_edge_with_random_spacing() -> None:
    game = one_button_jump.Game(random.Random(12345))
    game.state = one_button_jump.STATE_RUNNING
    spawn_positions = [game.obstacles[0].x]
    spacings = [game._distance_until_next_obstacle]

    for _ in range(8):
        game._distance_until_next_obstacle = 0.0
        game.update(0.0)
        spawn_positions.append(game.obstacles[-1].x)
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
    game.state = one_button_jump.STATE_RUNNING
    first = one_button_jump.Obstacle(x=-20.0, variant=0)
    second = one_button_jump.Obstacle(x=-30.0, variant=1)
    survivor = one_button_jump.Obstacle(x=180.0, variant=2)
    game.obstacles = [first, second, survivor]
    game._distance_until_next_obstacle = 1000.0

    game.update(0.0)

    assert game.score == 2
    assert game.obstacles == [survivor]


def test_collision_ends_round_and_records_high_score() -> None:
    game = one_button_jump.Game(random.Random(1))
    game.state = one_button_jump.STATE_RUNNING
    game.score = 9
    game.obstacles = [
        one_button_jump.Obstacle(
            x=float(one_button_jump.DINO_X + 8),
            variant=0,
        )
    ]
    game._distance_until_next_obstacle = 1000.0

    game.update(0.0)

    assert game.state == one_button_jump.STATE_GAME_OVER
    assert game.high_score == 9


def test_jump_can_clear_an_approaching_small_cactus() -> None:
    game = one_button_jump.Game(random.Random(1))
    game.state = one_button_jump.STATE_RUNNING
    game.obstacles = [one_button_jump.Obstacle(x=70.0, variant=0)]
    game._distance_until_next_obstacle = 1000.0

    game.press()
    for _ in range(4):
        game.update(0.05)

    assert game.state == one_button_jump.STATE_RUNNING
    assert game.player_y + one_button_jump.DINO_HEIGHT < (
        one_button_jump.GROUND_Y
        - game.obstacles[0].height
        + 2
    )


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
