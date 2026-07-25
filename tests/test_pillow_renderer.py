from pathlib import Path

import pytest
from PIL import Image

from lafvin_hat.runtime.ui import PillowRenderer
from lafvin_hat.ui import DEFAULT_THEME


@pytest.mark.parametrize(
    "view",
    [
        None,
        {"kind": "text", "title": "Text", "text": "Hello"},
        {
            "kind": "text",
            "title": "Voice",
            "text": "Hold to talk",
            "actions": [
                {"id": "talk", "label": "Talk"},
                {"id": "back", "label": "Back"},
            ],
            "selected": 0,
        },
        {
            "kind": "chat",
            "messages": [{"role": "assistant", "text": "Hello"}],
            "actions": [
                {"id": "talk", "label": "Talk"},
                {"id": "back", "label": "Back"},
            ],
            "selected": 1,
        },
        {
            "kind": "list",
            "items": [{"id": "one", "label": "One"}],
            "selected": 0,
        },
        {"kind": "progress", "message": "Loading", "value": 0.5},
        {
            "kind": "system_page",
            "title": "Volume",
            "components": [
                {"type": "spacer", "size": "small"},
                {"type": "value", "text": "70%"},
                {
                    "type": "button_row",
                    "actions": [
                        {"id": "volume.down", "label": "-10%"},
                        {"id": "volume.up", "label": "+10%"},
                    ],
                },
            ],
            "selected": 1,
        },
        {
            "kind": "dialog",
            "title": "Confirm",
            "message": "Continue?",
            "actions": ["OK"],
        },
    ],
)
def test_renderer_produces_rgb565_frame(view: dict | None) -> None:
    frame = PillowRenderer().render(view)

    assert frame.image.size == (240, 280)
    assert frame.image.mode == "RGB"
    assert len(frame.rgb565) == 240 * 280 * 2


def test_renderer_loads_image_from_app_directory(tmp_path: Path) -> None:
    Image.new("RGB", (32, 32), "red").save(tmp_path / "image.png")
    view = {
        "kind": "image",
        "source": {"type": "file", "path": "image.png"},
        "fit": "cover",
    }

    frame = PillowRenderer().render(view, asset_root=tmp_path)

    assert frame.image.getpixel((120, 150))[0] > 200


def test_home_list_uses_a_centered_depth_hierarchy() -> None:
    frame = PillowRenderer().render(
        {
            "kind": "list",
            "title": "LAFVIN HAT",
            "items": [
                {"id": "hardware", "label": "Hardware Test", "meta": "installed"},
                {"id": "status", "label": "System Status", "meta": "installed"},
                {"id": "volume", "label": "Volume", "meta": "installed"},
                {"id": "chatbot", "label": "AI Chatbot", "meta": "installed"},
                {"id": "translator", "label": "Translator", "meta": "installed"},
                {"id": "jump", "label": "One Button Jump", "meta": "installed"},
            ],
            "selected": 0,
        }
    )

    assert frame.image.getpixel((0, 0)) == DEFAULT_THEME.background
    assert frame.image.getpixel((20, 152)) == DEFAULT_THEME.button_selected
    assert frame.image.getpixel((28, 108)) == (225, 225, 225)
    assert frame.image.getpixel((36, 70)) == (237, 237, 237)
    assert frame.image.getpixel((20, 70)) == DEFAULT_THEME.background


def test_home_list_wraps_without_duplicate_rows() -> None:
    items = [
        {"id": str(index), "label": f"App {index}"}
        for index in range(3)
    ]

    visible = PillowRenderer._home_visible_items(items, selected=0)

    assert [offset for offset, _item in visible] == [-1, 0, 1]
    assert [item["id"] for _offset, item in visible] == ["2", "0", "1"]


def test_chat_bubble_height_contains_all_text_lines() -> None:
    renderer = PillowRenderer()
    lines = renderer._wrap(
        "The audio session works. Streaming text and queued speech work too.",
        renderer.body_font,
        renderer.width - 36,
    )

    box_height = max(40, len(lines) * 18 + 28)
    last_line_bottom = 22 + (len(lines) - 1) * 18 + 18

    assert last_line_bottom <= box_height


@pytest.mark.parametrize(
    "text",
    [
        "这是用于验证中文文本不会超出聊天气泡右侧边界的测试内容。",
        "日本語の文章が画面の右側を越えずに正しく折り返されます。",
        "한국어 문장이 화면 오른쪽 경계를 넘지 않고 줄바꿈됩니다.",
        "Donaudampfschifffahrtsgesellschaftskapitän",
        "English français español text remains inside the bubble.",
    ],
)
def test_multilingual_chat_lines_fit_pixel_width(text: str) -> None:
    renderer = PillowRenderer()
    max_width = renderer.width - 36

    lines = renderer._wrap(text, renderer.body_font, max_width)

    assert "".join(lines)
    assert all(
        renderer._text_width(line, renderer.body_font) <= max_width
        for line in lines
    )


def test_chat_layout_keeps_latest_message_visible() -> None:
    renderer = PillowRenderer()
    messages = [
        {"role": "user", "text": f"old message {index}"}
        for index in range(8)
    ]
    messages.append(
        {
            "role": "assistant",
            "text": "latest " + "response " * 80,
        }
    )

    visible = renderer._visible_chat_messages(
        messages,
        available_height=210,
    )

    assert visible[-1][0]["text"].startswith("latest")
    assert visible[-1][1][-1].endswith("response")
