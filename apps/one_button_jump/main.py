from __future__ import annotations

import asyncio
import contextlib
import random
import time

from lafvin_hat.sdk import DeviceApp
from lafvin_hat.ui import Canvas, Theme


WIDTH = 240
HEIGHT = 280
FRAME_INTERVAL = 1 / 30

STATE_READY = "ready"
STATE_RUNNING = "running"
STATE_GAME_OVER = "game_over"

GROUND_Y = 220
DINO_X = 28
SPRITE_SCALE = 2
JUMP_VELOCITY = -300.0
GRAVITY = 520.0
GAME_OVER_RETRY_DELAY = 0.35
RUN_FRAME_INTERVAL = 0.12
CLOUD_SCALE = 2

OBSTACLE_SPAWN_OFFSET_MIN = 0
OBSTACLE_SPAWN_OFFSET_MAX = 20
OBSTACLE_SPACING_MIN = 155
OBSTACLE_SPACING_MAX = 235
BASE_OBSTACLE_SPEED = 88.0
SPEEDUP_SCORE_30_PERCENT = 15
SPEEDUP_SCORE_50_PERCENT = 30

DINO_THEME = Theme(
    background=(247, 247, 247),
    text=(45, 45, 45),
    muted=(112, 112, 112),
    line=(69, 69, 69),
    accent=(45, 45, 45),
    danger=(178, 54, 54),
)

DINO_RUN_A = (
    "            ######",
    "           ########",
    "           ##  ####",
    "           ########",
    "           ####    ",
    "           ######  ",
    "#         ####     ",
    "##       #######   ",
    "###     #########  ",
    "####   ########    ",
    "###############    ",
    " #############     ",
    "  ###########      ",
    "    #######        ",
    "    ###  ##        ",
    "    ##   ##        ",
    "    ###            ",
    "         ###       ",
)

DINO_RUN_B = (
    "            ######",
    "           ########",
    "           ##  ####",
    "           ########",
    "           ####    ",
    "           ######  ",
    "#         ####     ",
    "##       #######   ",
    "###     #########  ",
    "####   ########    ",
    "###############    ",
    " #############     ",
    "  ###########      ",
    "    #######        ",
    "    ###  ##        ",
    "    ##   ###       ",
    "    ###            ",
    "    ##             ",
)

DINO_JUMP = (
    "            ######",
    "           ########",
    "           ##  ####",
    "           ########",
    "           ####    ",
    "           ######  ",
    "#         ####     ",
    "##       #######   ",
    "###     #########  ",
    "####   ########    ",
    "###############    ",
    " #############     ",
    "  ###########      ",
    "    #######        ",
    "    ### ###        ",
    "    ##   ##        ",
    "     ##  ##        ",
    "      ####         ",
)

CACTUS_SMALL = (
    "   ##  ",
    "   ##  ",
    "#  ##  ",
    "#  ## #",
    "## ## #",
    " ##### ",
    "   ##  ",
    "   ##  ",
    "   ##  ",
    "   ##  ",
    "   ##  ",
    "   ##  ",
    "   ##  ",
    "  #### ",
)

CACTUS_TALL = (
    "   ##   ",
    "   ##   ",
    "   ##   ",
    "#  ##   ",
    "#  ##  #",
    "## ##  #",
    " ##### ##",
    "   ##### ",
    "   ##    ",
    "   ##    ",
    "   ##    ",
    "   ##    ",
    "   ##    ",
    "   ##    ",
    "   ##    ",
    "   ##    ",
    "   ##    ",
    "  ####   ",
)

CACTUS_PAIR = (
    "  ##       ## ",
    "  ##       ## ",
    "  ##  #    ## ",
    "# ##  #  # ## ",
    "# ##  ## # ## ",
    "####   ####### ",
    "  ##       ##  ",
    "  ##       ##  ",
    "  ##       ##  ",
    "  ##       ##  ",
    "  ##       ##  ",
    "  ##       ##  ",
    "  ##       ##  ",
    " ####     #### ",
)

CACTUS_SPRITES = (CACTUS_SMALL, CACTUS_TALL, CACTUS_PAIR)

CLOUD_SPRITE = (
    "       ####       ",
    "    ###    ###    ",
    "  ##          ##  ",
    "##              ##",
    "##################",
)

DINO_WIDTH = max(len(row) for row in DINO_RUN_A) * SPRITE_SCALE
DINO_HEIGHT = len(DINO_RUN_A) * SPRITE_SCALE
DINO_REST_Y = float(GROUND_Y - DINO_HEIGHT)


class Obstacle:
    __slots__ = ("scored", "variant", "x")

    def __init__(self, x: float, variant: int, scored: bool = False) -> None:
        self.x = x
        self.variant = variant
        self.scored = scored

    @property
    def sprite(self) -> tuple[str, ...]:
        return CACTUS_SPRITES[self.variant]

    @property
    def width(self) -> int:
        return max(len(row) for row in self.sprite) * SPRITE_SCALE

    @property
    def height(self) -> int:
        return len(self.sprite) * SPRITE_SCALE


class Game:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self.high_score = 0
        self._reset_round(STATE_READY)

    @property
    def game_over(self) -> bool:
        return self.state == STATE_GAME_OVER

    @property
    def grounded(self) -> bool:
        return self.player_y >= DINO_REST_Y - 0.01

    def press(self) -> None:
        if self.state == STATE_READY:
            self.state = STATE_RUNNING
            self.state_elapsed = 0.0
            self.jump_requested = True
            return
        if self.state == STATE_RUNNING and self.grounded:
            self.jump_requested = True

    def retry(self) -> bool:
        if (
            self.state != STATE_GAME_OVER
            or self.state_elapsed < GAME_OVER_RETRY_DELAY
        ):
            return False
        self._reset_round(STATE_RUNNING)
        return True

    def update(self, elapsed: float) -> None:
        elapsed = max(0.0, float(elapsed))
        self.state_elapsed += elapsed
        if self.state != STATE_RUNNING:
            return

        if self.jump_requested:
            self.velocity = JUMP_VELOCITY
            self.jump_requested = False
        self.velocity += GRAVITY * elapsed
        self.player_y = min(
            DINO_REST_Y,
            self.player_y + self.velocity * elapsed,
        )
        if self.grounded and self.velocity > 0:
            self.velocity = 0.0

        travelled = self.obstacle_speed() * elapsed
        self.world_distance += travelled
        for obstacle in self.obstacles:
            obstacle.x -= travelled
            if (
                not obstacle.scored
                and obstacle.x + obstacle.width < DINO_X + 4
            ):
                obstacle.scored = True
                self.score += 1
        self.obstacles = [
            obstacle
            for obstacle in self.obstacles
            if obstacle.x + obstacle.width >= 0
        ]

        self._distance_until_next_obstacle -= travelled
        while self._distance_until_next_obstacle <= 0:
            self.obstacles.append(self._new_obstacle())
            self._distance_until_next_obstacle += self._next_obstacle_spacing()

        if self._collides():
            self.state = STATE_GAME_OVER
            self.state_elapsed = 0.0
            self.high_score = max(self.high_score, self.score)

    def obstacle_speed(self) -> float:
        if self.score >= SPEEDUP_SCORE_50_PERCENT:
            return BASE_OBSTACLE_SPEED * 1.5
        if self.score >= SPEEDUP_SCORE_30_PERCENT:
            return BASE_OBSTACLE_SPEED * 1.3
        return BASE_OBSTACLE_SPEED

    def _reset_round(self, state: str) -> None:
        self.state = state
        self.state_elapsed = 0.0
        self.player_y = DINO_REST_Y
        self.velocity = 0.0
        self.jump_requested = False
        self.world_distance = 0.0
        self.score = 0
        self.obstacles = [self._new_obstacle()]
        self._distance_until_next_obstacle = self._next_obstacle_spacing()

    def _new_obstacle(self) -> Obstacle:
        return Obstacle(
            x=float(
                WIDTH
                + self._rng.randint(
                    OBSTACLE_SPAWN_OFFSET_MIN,
                    OBSTACLE_SPAWN_OFFSET_MAX,
                )
            ),
            variant=self._rng.randrange(len(CACTUS_SPRITES)),
        )

    def _next_obstacle_spacing(self) -> float:
        return float(
            self._rng.randint(OBSTACLE_SPACING_MIN, OBSTACLE_SPACING_MAX)
        )

    def _collides(self) -> bool:
        dino_left = DINO_X + 6
        dino_top = int(self.player_y) + 4
        dino_right = DINO_X + DINO_WIDTH - 5
        dino_bottom = int(self.player_y) + DINO_HEIGHT - 2
        for obstacle in self.obstacles:
            obstacle_left = int(obstacle.x) + 2
            obstacle_top = GROUND_Y - obstacle.height + 2
            obstacle_right = int(obstacle.x) + obstacle.width - 2
            obstacle_bottom = GROUND_Y
            if (
                dino_left < obstacle_right
                and dino_right > obstacle_left
                and dino_top < obstacle_bottom
                and dino_bottom > obstacle_top
            ):
                return True
        return False


def handle_event(game: Game, event_name: str) -> str | None:
    if event_name == "app.exit_requested":
        return "exit"
    if event_name == "button.raw_pressed":
        game.press()
    elif event_name == "button.single_clicked" and game.game_over:
        game.retry()
    return None


def render_game(canvas: Canvas, game: Game) -> Canvas:
    canvas.clear()
    _draw_clouds(canvas, game.world_distance)
    _draw_ground(canvas, game.world_distance)
    for obstacle in game.obstacles:
        _draw_pixel_sprite(
            canvas,
            obstacle.sprite,
            x=int(obstacle.x),
            y=GROUND_Y - obstacle.height,
            scale=SPRITE_SCALE,
            fill=canvas.theme.text,
        )

    dino_sprite = _active_dino_sprite(game)
    _draw_pixel_sprite(
        canvas,
        dino_sprite,
        x=DINO_X,
        y=int(game.player_y),
        scale=SPRITE_SCALE,
        fill=canvas.theme.text,
    )
    if game.game_over:
        canvas.draw.line(
            (DINO_X + 29, int(game.player_y) + 5, DINO_X + 35, int(game.player_y) + 11),
            fill=canvas.theme.danger,
            width=2,
        )
        canvas.draw.line(
            (DINO_X + 35, int(game.player_y) + 5, DINO_X + 29, int(game.player_y) + 11),
            fill=canvas.theme.danger,
            width=2,
        )

    _draw_hud(canvas, game)
    if game.state == STATE_READY:
        canvas.draw.rectangle(
            (28, 76, canvas.width - 28, 135),
            fill=canvas.theme.background,
        )
        canvas.center_text("PRESS TO START", y=94, font=canvas.body_font)
        canvas.center_text(
            "3 CLICKS: HOME",
            y=122,
            fill=canvas.theme.muted,
            font=canvas.small_font,
        )
    elif game.state == STATE_GAME_OVER:
        canvas.draw.rectangle(
            (22, 54, canvas.width - 22, 176),
            fill=canvas.theme.background,
        )
        canvas.center_text("GAME OVER", y=78, size="large")
        canvas.center_text(
            f"SCORE {game.score:05d}",
            y=110,
            font=canvas.body_font,
        )
        canvas.center_text(
            "SINGLE: RETRY",
            y=140,
            fill=canvas.theme.muted,
            font=canvas.small_font,
        )
        canvas.center_text(
            "3 CLICKS: HOME",
            y=160,
            fill=canvas.theme.muted,
            font=canvas.small_font,
        )
    return canvas


def rgb565_frame(game: Game, canvas: Canvas | None = None) -> bytes:
    active_canvas = canvas or Canvas(width=WIDTH, height=HEIGHT, theme=DINO_THEME)
    return render_game(active_canvas, game).render()


def _draw_hud(canvas: Canvas, game: Game) -> None:
    canvas.draw.text(
        (10, 8),
        "DINO RUN",
        fill=canvas.theme.text,
        font=canvas.small_font,
    )
    _draw_right_text(
        canvas,
        f"{game.score:05d}",
        x=canvas.width - 10,
        y=8,
        fill=canvas.theme.text,
    )
    _draw_right_text(
        canvas,
        f"HI {game.high_score:05d}",
        x=canvas.width - 10,
        y=28,
        fill=canvas.theme.muted,
    )


def _draw_right_text(
    canvas: Canvas,
    text: str,
    *,
    x: int,
    y: int,
    fill: tuple[int, int, int],
) -> None:
    bounds = canvas.draw.textbbox((0, 0), text, font=canvas.small_font)
    canvas.draw.text(
        (x - (bounds[2] - bounds[0]), y),
        text,
        fill=fill,
        font=canvas.small_font,
    )


def _draw_clouds(canvas: Canvas, world_distance: float) -> None:
    wrap_width = canvas.width + 100
    for start_x, y in ((78, 64), (196, 104), (322, 82)):
        x = int((start_x - world_distance * 0.18) % wrap_width) - 40
        _draw_pixel_sprite(
            canvas,
            CLOUD_SPRITE,
            x=x,
            y=y,
            scale=CLOUD_SCALE,
            fill=(198, 198, 198),
        )


def _draw_ground(canvas: Canvas, world_distance: float) -> None:
    canvas.draw.line(
        (0, GROUND_Y, canvas.width, GROUND_Y),
        fill=canvas.theme.line,
        width=2,
    )
    offset = int(world_distance) % 20
    for x in range(-offset, canvas.width + 20, 20):
        canvas.draw.line(
            (x, GROUND_Y + 7, x + 8, GROUND_Y + 7),
            fill=(160, 160, 160),
            width=1,
        )


def _active_dino_sprite(game: Game) -> tuple[str, ...]:
    if not game.grounded:
        return DINO_JUMP
    if game.state != STATE_RUNNING:
        return DINO_RUN_A
    frame_index = int(game.state_elapsed / RUN_FRAME_INTERVAL) % 2
    return (DINO_RUN_A, DINO_RUN_B)[frame_index]


def _draw_pixel_sprite(
    canvas: Canvas,
    sprite: tuple[str, ...],
    *,
    x: int,
    y: int,
    scale: int,
    fill: tuple[int, int, int],
) -> None:
    for row_index, row in enumerate(sprite):
        run_start: int | None = None
        for column, value in enumerate(f"{row} "):
            if value != " " and run_start is None:
                run_start = column
                continue
            if value == " " and run_start is not None:
                canvas.draw.rectangle(
                    (
                        x + run_start * scale,
                        y + row_index * scale,
                        x + column * scale - 1,
                        y + (row_index + 1) * scale - 1,
                    ),
                    fill=fill,
                )
                run_start = None


async def main() -> None:
    app = await DeviceApp.connect_from_environment()
    await app.acquire_foreground()
    frame = await app.frames.acquire()
    canvas = Canvas(width=frame.width, height=frame.height, theme=DINO_THEME)
    game = Game()
    events = app.subscribe(
        events=[
            "button.raw_pressed",
            "button.single_clicked",
            "app.exit_requested",
        ]
    )
    event_task = asyncio.create_task(anext(events), name="dino-runner-events")
    previous = time.monotonic()
    pending_input_timestamp_ms: int | None = None
    try:
        while True:
            now = time.monotonic()
            elapsed = min(now - previous, 0.1)
            previous = now
            if event_task.done():
                try:
                    event = event_task.result()
                except StopAsyncIteration:
                    break
                if handle_event(game, event["event"]) == "exit":
                    break
                timestamp_ms = event.get("timestamp_ms")
                if isinstance(timestamp_ms, int):
                    pending_input_timestamp_ms = timestamp_ms
                event_task = asyncio.create_task(
                    anext(events),
                    name="dino-runner-events",
                )

            game.update(elapsed)
            render_game(canvas, game)
            await canvas.present(
                frame,
                input_timestamp_ms=pending_input_timestamp_ms,
            )
            pending_input_timestamp_ms = None
            delay = FRAME_INTERVAL - (time.monotonic() - now)
            if delay > 0:
                await asyncio.sleep(delay)
    finally:
        event_task.cancel()
        await asyncio.gather(event_task, return_exceptions=True)
        with contextlib.suppress(Exception):
            await events.aclose()
        await app.close()


if __name__ == "__main__":
    asyncio.run(main())
