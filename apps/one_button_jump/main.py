from __future__ import annotations

import asyncio
import contextlib
import random
import time

from lafvin_hat.sdk import DeviceApp


WIDTH = 240
HEIGHT = 280
FRAME_INTERVAL = 1 / 30
MENU_CLICK_INTERVAL = 0.450
JUMP_VELOCITY = -240.0
GRAVITY = 430.0
BACKGROUND = 0x0843
GROUND = 0x5AEB
PLAYER = 0xFFE0
OBSTACLE = 0xF986
WHITE = 0xFFFF
PANEL = 0x2104
HIGHLIGHT = 0x3A7F
MUTED = 0x8C71
OBSTACLE_WIDTH = 18
OBSTACLE_SPAWN_OFFSET_MIN = 0
OBSTACLE_SPAWN_OFFSET_MAX = 20
OBSTACLE_SPACING_MIN = 160
OBSTACLE_SPACING_MAX = 260
BASE_OBSTACLE_SPEED = 85.0
SPEEDUP_SCORE_30_PERCENT = 15
SPEEDUP_SCORE_50_PERCENT = 30
HUD_SCORE_X = 20
GAME_OVER_SCORE_Y = 113
GAME_OVER_SCORE_SCALE = 3
GAME_OVER_OPTIONS = (("CONTINUE", 140), ("EXIT", 168))


class Game:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self.player_y = 220.0
        self.velocity = 0.0
        self.obstacles = [self._next_obstacle_x()]
        self._distance_until_next_obstacle = self._next_obstacle_spacing()
        self.score = 0
        self.game_over = False
        self.jump_requested = False
        self.menu_selected = 0
        self._menu_pending_release_at: float | None = None

    def press(self) -> None:
        if not self.game_over and self.player_y >= 219:
            self.jump_requested = True

    def release(self, timestamp: float) -> str | None:
        if not self.game_over:
            return None
        self.advance_menu(timestamp)
        pending = self._menu_pending_release_at
        if pending is not None and timestamp - pending <= MENU_CLICK_INTERVAL:
            self._menu_pending_release_at = None
            return "continue" if self.menu_selected == 0 else "exit"
        self._menu_pending_release_at = timestamp
        return None

    def update(self, elapsed: float) -> None:
        if self.game_over:
            return
        if self.jump_requested:
            self.velocity = JUMP_VELOCITY
            self.jump_requested = False
        self.velocity += GRAVITY * elapsed
        self.player_y = min(220.0, self.player_y + self.velocity * elapsed)
        if self.player_y >= 220:
            self.velocity = 0.0
        travelled = self.obstacle_speed() * elapsed
        self.obstacles = [position - travelled for position in self.obstacles]
        passed = sum(
            position < -OBSTACLE_WIDTH for position in self.obstacles
        )
        if passed:
            self.score += passed
            self.obstacles = [
                position
                for position in self.obstacles
                if position >= -OBSTACLE_WIDTH
            ]

        self._distance_until_next_obstacle -= travelled
        while self._distance_until_next_obstacle <= 0:
            self.obstacles.append(self._next_obstacle_x())
            self._distance_until_next_obstacle += self._next_obstacle_spacing()

        if self.player_y + 20 > 220 and any(
            position < 55 and position + OBSTACLE_WIDTH > 30
            for position in self.obstacles
        ):
            self.game_over = True

    def advance_menu(self, timestamp: float) -> None:
        pending = self._menu_pending_release_at
        if (
            self.game_over
            and pending is not None
            and timestamp - pending >= MENU_CLICK_INTERVAL
        ):
            self.menu_selected = 1 - self.menu_selected
            self._menu_pending_release_at = None

    def _next_obstacle_x(self) -> float:
        offset = self._rng.randint(
            OBSTACLE_SPAWN_OFFSET_MIN,
            OBSTACLE_SPAWN_OFFSET_MAX,
        )
        return float(WIDTH + offset)

    def _next_obstacle_spacing(self) -> float:
        return float(
            self._rng.randint(OBSTACLE_SPACING_MIN, OBSTACLE_SPACING_MAX)
        )

    def obstacle_speed(self) -> float:
        if self.score >= SPEEDUP_SCORE_50_PERCENT:
            return BASE_OBSTACLE_SPEED * 1.5
        if self.score >= SPEEDUP_SCORE_30_PERCENT:
            return BASE_OBSTACLE_SPEED * 1.3
        return BASE_OBSTACLE_SPEED


def rgb565_frame(game: Game) -> bytes:
    pixels = bytearray(_color_bytes(BACKGROUND) * (WIDTH * HEIGHT))
    _rect(pixels, 0, 240, WIDTH, 40, GROUND)
    _rect(pixels, 30, int(game.player_y), 25, 20, PLAYER)
    for obstacle_x in game.obstacles:
        _rect(
            pixels,
            int(obstacle_x),
            210,
            OBSTACLE_WIDTH,
            30,
            OBSTACLE,
        )
    _number(pixels, HUD_SCORE_X, 8, game.score, WHITE)
    if game.game_over:
        _game_over_menu(pixels, game)
    return bytes(pixels)


def _game_over_menu(pixels: bytearray, game: Game) -> None:
    _rect(pixels, 24, 72, 192, 132, PANEL)
    _text(pixels, 55, 88, "GAME OVER", WHITE, scale=3)
    _text(pixels, 55, 116, "SCORE", MUTED, scale=2)
    _number(
        pixels,
        125,
        GAME_OVER_SCORE_Y,
        game.score,
        WHITE,
        scale=GAME_OVER_SCORE_SCALE,
    )
    for index, (label, y) in enumerate(GAME_OVER_OPTIONS):
        if index == game.menu_selected:
            _rect(pixels, 45, y - 5, 150, 23, HIGHLIGHT)
            color = WHITE
        else:
            color = MUTED
        _text(pixels, 63, y, label, color, scale=2)


def _rect(
    pixels: bytearray,
    x: int,
    y: int,
    width: int,
    height: int,
    color: int,
) -> None:
    left = max(0, x)
    top = max(0, y)
    right = min(WIDTH, x + width)
    bottom = min(HEIGHT, y + height)
    row_data = _color_bytes(color) * (right - left)
    for row in range(top, bottom):
        start = (row * WIDTH + left) * 2
        pixels[start:start + len(row_data)] = row_data


def _number(
    pixels: bytearray,
    x: int,
    y: int,
    value: int,
    color: int,
    *,
    scale: int = 3,
) -> None:
    _text(pixels, x, y, str(value), color, scale=scale)


def _text(
    pixels: bytearray,
    x: int,
    y: int,
    text: str,
    color: int,
    *,
    scale: int = 3,
) -> None:
    cursor = x
    for char in text.upper():
        if char == " ":
            cursor += 2 * scale
            continue
        glyph = _GLYPHS.get(char)
        if glyph is None:
            cursor += 4 * scale
            continue
        for row, line in enumerate(glyph):
            for column, bit in enumerate(line):
                if bit == "1":
                    _rect(
                        pixels,
                        cursor + column * scale,
                        y + row * scale,
                        scale,
                        scale,
                        color,
                    )
        cursor += (len(glyph[0]) + 1) * scale


_GLYPHS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "A": ("010", "101", "111", "101", "101"),
    "C": ("111", "100", "100", "100", "111"),
    "E": ("111", "100", "111", "100", "111"),
    "G": ("111", "100", "101", "101", "111"),
    "I": ("111", "010", "010", "010", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("111", "101", "101", "101", "111"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("111", "100", "111", "001", "111"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "X": ("101", "101", "010", "101", "101"),
}


def _color_bytes(color: int) -> bytes:
    return bytes((color >> 8, color & 0xFF))


async def main() -> None:
    app = await DeviceApp.connect_from_environment()
    await app.acquire_foreground()
    frame = await app.frames.acquire()
    game = Game()
    events = app.subscribe(
        events=[
            "button.raw_pressed",
            "button.raw_released",
            "app.exit_requested",
        ]
    )
    event_task = asyncio.create_task(anext(events))
    previous = time.monotonic()
    pending_input_timestamp_ms: int | None = None
    try:
        while True:
            now = time.monotonic()
            elapsed = min(now - previous, 0.1)
            previous = now
            if event_task.done():
                event = event_task.result()
                if event["event"] == "app.exit_requested":
                    break
                if event["event"] == "button.raw_pressed":
                    game.press()
                    pending_input_timestamp_ms = event["timestamp_ms"]
                if event["event"] == "button.raw_released":
                    action = game.release(time.monotonic())
                    if action == "continue":
                        game = Game()
                    elif action == "exit":
                        break
                event_task = asyncio.create_task(anext(events))
            game.update(elapsed)
            game.advance_menu(now)
            frame.write(rgb565_frame(game))
            await frame.commit(
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
