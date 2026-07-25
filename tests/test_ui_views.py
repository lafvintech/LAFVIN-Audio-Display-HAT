import pytest

from lafvin_hat.runtime.ui import UIModelError, apply_patch, validate_view


@pytest.mark.parametrize(
    "view",
    [
        {"kind": "text", "text": "Hello", "status": "idle"},
        {
            "kind": "text",
            "text": "Hold to talk",
            "status": "idle",
            "actions": [
                {"id": "talk", "label": "Talk"},
                {"id": "back", "label": "Back"},
            ],
            "selected": 0,
        },
        {
            "kind": "chat",
            "messages": [
                {"role": "user", "text": "Hello"},
                {"role": "assistant", "text": "Hi"},
            ],
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
            "kind": "image",
            "source": {"type": "file", "path": "image.png"},
            "fit": "contain",
        },
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
            "actions": ["OK", "Cancel"],
        },
    ],
)
def test_validate_supported_views(view: dict) -> None:
    assert validate_view(view) == view


def test_patch_view_preserves_schema() -> None:
    current = {
        "kind": "chat",
        "messages": [{"role": "assistant", "text": "Hel"}],
        "streaming": True,
    }

    patched = apply_patch(
        current,
        [
            {
                "op": "append_text",
                "path": "/messages/0/text",
                "value": "lo",
            },
            {
                "op": "append_item",
                "path": "/messages",
                "value": {"role": "user", "text": "Hi"},
            },
            {"op": "replace", "path": "/streaming", "value": False},
        ],
    )

    assert patched["messages"][0]["text"] == "Hello"
    assert patched["messages"][1]["role"] == "user"
    assert patched["streaming"] is False
    assert current["messages"][0]["text"] == "Hel"


def test_invalid_view_and_patch_are_rejected() -> None:
    with pytest.raises(UIModelError):
        validate_view(
            {
                "kind": "list",
                "items": [{"id": "one", "label": "One"}],
                "selected": 2,
            }
        )
    with pytest.raises(UIModelError):
        validate_view(
            {
                "kind": "unknown",
                "title": "Volume",
            }
        )
    with pytest.raises(UIModelError):
        validate_view(
            {
                "kind": "system_page",
                "title": "Volume",
                "components": [
                    {
                        "type": "button_row",
                        "actions": [
                            {"id": "volume.up", "label": "+10%"},
                        ],
                    },
                ],
                "selected": 1,
            }
        )
    with pytest.raises(UIModelError):
        validate_view(
            {
                "kind": "text",
                "text": "Bad action selection",
                "actions": [{"id": "talk", "label": "Talk"}],
                "selected": 1,
            }
        )
    with pytest.raises(UIModelError):
        validate_view(
            {
                "kind": "chat",
                "messages": [{"role": "assistant", "text": "Hi"}],
                "actions": [{"id": "talk", "label": "Talk"}],
            }
        )

    with pytest.raises(UIModelError):
        apply_patch(
            {"kind": "text", "text": "Hello"},
            [{"op": "replace", "path": "/kind", "value": "chat"}],
        )
