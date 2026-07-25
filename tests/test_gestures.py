from lafvin_hat.runtime.gestures import (
    GestureContext,
    GestureRecognizer,
)


def test_home_single_click_is_delayed_until_timeout() -> None:
    recognizer = GestureRecognizer()

    released_at = 0.050
    deadline = released_at + recognizer.config.click_interval

    assert recognizer.press(0.000, GestureContext.HOME) == []
    assert recognizer.release(released_at, GestureContext.HOME) == []
    assert recognizer.advance(deadline - 0.001) == []

    events = recognizer.advance(deadline)

    assert [event.name for event in events] == ["button.single_clicked"]


def test_home_double_click_suppresses_single_click() -> None:
    recognizer = GestureRecognizer()
    second_pressed_at = 0.050 + recognizer.config.click_interval - 0.001
    second_released_at = second_pressed_at + 0.050

    recognizer.press(0.000, GestureContext.HOME)
    recognizer.release(0.050, GestureContext.HOME)
    recognizer.press(second_pressed_at, GestureContext.HOME)
    events = recognizer.release(second_released_at, GestureContext.HOME)

    assert [event.name for event in events] == ["button.double_clicked"]
    assert recognizer.advance(1.000) == []


def test_foreground_triple_click_is_recognized() -> None:
    recognizer = GestureRecognizer()

    for pressed_at, released_at in (
        (0.000, 0.040),
        (0.150, 0.190),
    ):
        assert recognizer.press(pressed_at, GestureContext.FOREGROUND) == []
        assert recognizer.release(released_at, GestureContext.FOREGROUND) == []

    recognizer.press(0.300, GestureContext.FOREGROUND)
    events = recognizer.release(0.340, GestureContext.FOREGROUND)

    assert [event.name for event in events] == ["button.triple_clicked"]
    assert recognizer.advance(1.000) == []


def test_foreground_single_and_double_clicks_are_recognized() -> None:
    recognizer = GestureRecognizer()

    recognizer.press(0.000, GestureContext.FOREGROUND)
    recognizer.release(0.050, GestureContext.FOREGROUND)
    single = recognizer.advance(0.050 + recognizer.config.click_interval)
    assert [event.name for event in single] == ["button.single_clicked"]

    recognizer.press(0.400, GestureContext.FOREGROUND)
    recognizer.release(0.450, GestureContext.FOREGROUND)
    recognizer.press(0.550, GestureContext.FOREGROUND)
    assert recognizer.release(0.600, GestureContext.FOREGROUND) == []
    double = recognizer.advance(0.600 + recognizer.config.click_interval)
    assert [event.name for event in double] == ["button.double_clicked"]


def test_shell_single_double_and_triple_clicks_are_recognized() -> None:
    recognizer = GestureRecognizer()

    recognizer.press(0.000, GestureContext.SHELL)
    recognizer.release(0.050, GestureContext.SHELL)
    single = recognizer.advance(0.050 + recognizer.config.click_interval)
    assert [event.name for event in single] == ["button.single_clicked"]
    assert [event.context for event in single] == [GestureContext.SHELL]

    recognizer.press(0.400, GestureContext.SHELL)
    recognizer.release(0.450, GestureContext.SHELL)
    recognizer.press(0.550, GestureContext.SHELL)
    assert recognizer.release(0.600, GestureContext.SHELL) == []
    double = recognizer.advance(0.600 + recognizer.config.click_interval)
    assert [event.name for event in double] == ["button.double_clicked"]
    assert [event.context for event in double] == [GestureContext.SHELL]

    for pressed_at, released_at in (
        (1.000, 1.040),
        (1.150, 1.190),
    ):
        assert recognizer.press(pressed_at, GestureContext.SHELL) == []
        assert recognizer.release(released_at, GestureContext.SHELL) == []

    recognizer.press(1.300, GestureContext.SHELL)
    triple = recognizer.release(1.340, GestureContext.SHELL)
    assert [event.name for event in triple] == ["button.triple_clicked"]
    assert [event.context for event in triple] == [GestureContext.SHELL]


def test_long_hold_cancels_pending_click_sequence() -> None:
    recognizer = GestureRecognizer()
    second_pressed_at = 0.050 + recognizer.config.click_interval / 2

    recognizer.press(0.000, GestureContext.HOME)
    recognizer.release(0.050, GestureContext.HOME)
    recognizer.press(second_pressed_at, GestureContext.HOME)
    assert recognizer.release(second_pressed_at + 0.400, GestureContext.HOME) == []

    assert recognizer.advance(1.000) == []
    assert recognizer.click_count == 0


def test_context_change_discards_home_click_and_tracks_foreground_click() -> None:
    recognizer = GestureRecognizer()

    recognizer.press(0.000, GestureContext.HOME)
    recognizer.release(0.050, GestureContext.HOME)
    assert recognizer.press(0.100, GestureContext.FOREGROUND) == []
    assert recognizer.release(0.140, GestureContext.FOREGROUND) == []

    events = recognizer.advance(1.000)
    assert [event.name for event in events] == ["button.single_clicked"]
    assert [event.context for event in events] == [GestureContext.FOREGROUND]


def test_slow_home_clicks_become_separate_single_clicks() -> None:
    recognizer = GestureRecognizer()

    recognizer.press(0.000, GestureContext.HOME)
    recognizer.release(0.050, GestureContext.HOME)
    first = recognizer.advance(0.050 + recognizer.config.click_interval)
    recognizer.press(0.400, GestureContext.HOME)
    recognizer.release(0.450, GestureContext.HOME)
    second = recognizer.advance(0.450 + recognizer.config.click_interval)

    assert [event.name for event in first + second] == [
        "button.single_clicked",
        "button.single_clicked",
    ]
