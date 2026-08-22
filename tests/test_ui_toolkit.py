from __future__ import annotations

import asyncio

import lafvin_hat.ui.toolkit as toolkit_module
from lafvin_hat.ui import Canvas, ChatMessage, StatusRow, image_to_rgb565_be


class FakeFrame:
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


def test_canvas_renders_rgb565_status_page() -> None:
    canvas = Canvas(width=240, height=280).system_status_page(
        [
            StatusRow("Runtime", "12s"),
            StatusRow("Model", "RPI Zero 2 W"),
        ]
    )

    frame = canvas.render()

    assert len(frame) == 240 * 280 * 2
    assert frame != bytes(len(frame))


def test_canvas_renders_center_text_and_button_row() -> None:
    canvas = Canvas(width=240, height=280)
    canvas.clear()
    canvas.title("Volume")
    canvas.divider()
    canvas.center_text("70%", y=96, size="large")
    canvas.button_row(["-10%", "+10%"], selected=1, y=176)

    frame = canvas.render()

    assert len(frame) == 240 * 280 * 2
    assert canvas.image.getpixel((45, 189)) == canvas.theme.button
    assert canvas.image.getpixel((141, 189)) == canvas.theme.button_selected


def test_canvas_renders_text_page_with_action_bar() -> None:
    canvas = Canvas(width=240, height=280).text_page(
        "Chatbot",
        "Hold the button and speak.",
        status="idle",
        actions=["Talk", "Back"],
        selected=0,
    )

    frame = canvas.render()

    assert len(frame) == 240 * 280 * 2
    assert canvas.image.getpixel((31, 250)) == canvas.theme.button_selected
    assert canvas.image.getpixel((131, 250)) == canvas.theme.button


def test_canvas_renders_message_list() -> None:
    canvas = Canvas(width=240, height=280).clear().message_list(
        [
            ChatMessage("user", "Hi"),
            ChatMessage("assistant", "Hello"),
        ],
        y=50,
        height=126,
        scroll_to_bottom=False,
    )

    frame = canvas.render()

    assert len(frame) == 240 * 280 * 2
    assert canvas.image.getpixel((20, 56)) == canvas.theme.user_message
    assert canvas.image.getpixel((20, 123)) == canvas.theme.assistant_message


def test_canvas_renders_chat_page_from_dict_messages() -> None:
    canvas = Canvas(width=240, height=280).chat_page(
        "Translator",
        [
            {"role": "user", "text": "hello"},
            {"role": "assistant", "text": "bonjour"},
        ],
        status="answering",
        streaming=True,
        actions=["Translate", "Back"],
        selected=1,
    )

    frame = canvas.render()

    assert len(frame) == 240 * 280 * 2
    assert canvas.image.getpixel((31, 250)) == canvas.theme.button
    assert canvas.image.getpixel((131, 250)) == canvas.theme.button_selected


def test_streaming_chat_hides_empty_assistant_placeholder_until_first_text() -> None:
    waiting = Canvas(width=240, height=280).chat_page(
        "Translator",
        [
            ChatMessage("user", "hello"),
            ChatMessage("assistant", ""),
        ],
        status="answering",
        streaming=True,
        actions=["Translate", "Back"],
    )

    assert waiting.image.getpixel((20, 76)) == waiting.theme.user_message
    assert waiting.image.getpixel((20, 145)) == waiting.theme.background

    replying = Canvas(width=240, height=280).chat_page(
        "Translator",
        [
            ChatMessage("user", "hello"),
            ChatMessage("assistant", "bonjour"),
        ],
        status="answering",
        streaming=True,
        actions=["Translate", "Back"],
    )

    assert replying.image.getpixel((20, 190)) == replying.theme.assistant_message


def test_status_display_capitalizes_only_the_first_character() -> None:
    assert toolkit_module._display_status("idle") == "Idle"
    assert toolkit_module._display_status("ASR ready") == "ASR ready"
    assert toolkit_module._display_status("") == ""


def test_scrolling_text_target_stays_still_for_short_text_and_reaches_tail(
) -> None:
    canvas = Canvas(width=240, height=280)
    viewport_height = 280 - 70 - 58

    assert canvas.text_scroll_target(
        "Short answer.",
        len("Short answer."),
        width=196,
        height=viewport_height,
    ) == 0

    long_answer = "\n".join(f"line {index}" for index in range(20))
    target = canvas.text_scroll_target(
        long_answer,
        len(long_answer),
        width=196,
        height=viewport_height,
    )

    assert target == 20 * 24 - viewport_height
    rendered = canvas.scrolling_text_page(
        "Chatbot",
        long_answer,
        scroll_top=target,
        status="answering",
        actions=["Talk", "Back"],
    ).render()
    assert len(rendered) == 240 * 280 * 2


def test_assistant_hangul_reply_uses_one_korean_body_font() -> None:
    canvas = Canvas(width=240, height=280)
    assistant = canvas._message_block(
        ChatMessage("assistant", "\uc548\ub155\ud558\uc138\uc694. Hello."),
        width=216,
        line_height=19,
    )
    user = canvas._message_block(
        ChatMessage("user", "\uc548\ub155\ud558\uc138\uc694"),
        width=216,
        line_height=19,
    )

    assert assistant["font"] is not canvas.body_font
    assert user["font"] is canvas.body_font
    assert toolkit_module._contains_hangul("\uc548\ub155\ud558\uc138\uc694")
    assert not toolkit_module._contains_hangul("Hello, bonjour, hola")


def test_message_list_clips_overlong_latest_message_to_tail() -> None:
    lines = [f"line {index}" for index in range(12)]
    block = {
        "message": ChatMessage("assistant", "\n".join(lines)),
        "lines": lines,
        "height": 30 + len(lines) * 19 + 10,
        "line_height": 19,
    }

    visible = toolkit_module._bottom_fit_blocks([block], height=80, gap=8)

    assert len(visible) == 1
    assert visible[0]["height"] <= 80
    assert visible[0]["lines"] == ["line 10", "line 11"]


def test_canvas_present_writes_and_commits_frame() -> None:
    async def scenario() -> None:
        fake = FakeFrame()
        result = await Canvas().error_page(
            "System Status",
            "Status unavailable",
        ).present(fake)

        assert len(fake.data) == 240 * 280 * 2
        assert fake.commits == 1
        assert result == {"next_sequence": 2}

    asyncio.run(scenario())


def test_image_to_rgb565_be_uses_big_endian_order() -> None:
    from PIL import Image

    image = Image.new("RGB", (1, 1), (255, 0, 0))

    assert image_to_rgb565_be(image) == bytes([0xF8, 0x00])
