"""Declarative UI: theme, view helpers, validation, patch, and rendering."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from lafvin_hat.ui import DEFAULT_THEME
from lafvin_hat.ui.fonts import load_ui_font
from lafvin_hat.schemas import load_ui_view_schema

# ── Theme ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Theme:
    bg: str
    surface: str
    text_primary: str
    text_muted: str
    accent: str
    accent_secondary: str
    emphasis_normal: str
    emphasis_primary: str
    emphasis_warning: str
    emphasis_danger: str
    msg_user_fill: str
    msg_user_outline: str
    msg_assistant_fill: str
    msg_assistant_outline: str
    msg_text: str
    list_active_fill: str
    list_inactive_fill: str
    list_active_text: str
    list_inactive_text: str
    list_meta_text: str
    progress_track: str
    progress_fill: str
    action_selected_fill: str
    action_fill: str
    action_text: str
    dialog_fill: str
    dialog_text: str
    image_error_outline: str
    image_error_text: str


@dataclass(frozen=True, slots=True)
class SystemTheme:
    bg: str
    text: str
    header_line: str
    button_fill: str
    button_selected_fill: str
    button_text: str
    divider: str


@dataclass(frozen=True, slots=True)
class HomeTheme:
    bg: str
    text: str
    divider: str
    row_near_fill: str
    row_far_fill: str
    row_selected_fill: str
    row_near_text: str
    row_far_text: str
    row_selected_text: str


def _rgb_hex(color: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


DARK = Theme(
    bg="#080c14",
    surface="#151e2c",
    text_primary="#f4f7fb",
    text_muted="#8190a8",
    accent="#3182f6",
    accent_secondary="#3ecf8e",
    emphasis_normal="#e6ebf2",
    emphasis_primary="#70a8ff",
    emphasis_warning="#f4c95d",
    emphasis_danger="#ff7979",
    msg_user_fill="#16365c",
    msg_user_outline="#3182f6",
    msg_assistant_fill="#192b24",
    msg_assistant_outline="#3ecf8e",
    msg_text="#f2f5f8",
    list_active_fill="#203f69",
    list_inactive_fill="#121a28",
    list_active_text="#ffffff",
    list_inactive_text="#a9b4c6",
    list_meta_text="#7f91aa",
    progress_track="#263247",
    progress_fill="#3182f6",
    action_selected_fill="#3182f6",
    action_fill="#263247",
    action_text="#f4f7fb",
    dialog_fill="#151e2c",
    dialog_text="#e6ebf2",
    image_error_outline="#d05555",
    image_error_text="#ff8f8f",
)

LIGHT = SystemTheme(
    bg="#f7f7f5",
    text="#05070a",
    header_line="#05070a",
    button_fill="#d6d7da",
    button_selected_fill="#c7c9cf",
    button_text="#05070a",
    divider="#c8c8c8",
)

HOME_LIGHT = HomeTheme(
    bg=_rgb_hex(DEFAULT_THEME.background),
    text=_rgb_hex(DEFAULT_THEME.text),
    divider=_rgb_hex(DEFAULT_THEME.line),
    row_near_fill="#e1e1e1",
    row_far_fill="#ededed",
    row_selected_fill=_rgb_hex(DEFAULT_THEME.button_selected),
    row_near_text="#202020",
    row_far_text="#888888",
    row_selected_text=_rgb_hex(DEFAULT_THEME.button_selected_text),
)

TITLE_SIZE = 20
BODY_SIZE = 16
SMALL_SIZE = 12
PADDING = 14
LINE_HEIGHT = 21
CHAT_LINE_HEIGHT = 18
CHAT_BOX_PAD = 28
CHAT_BOX_MIN = 40
CHAT_GAP = 8
LIST_VISIBLE = 5
HOME_ROW_Y = {-2: 54, -1: 91, 0: 132, 1: 179, 2: 220}
HOME_ROW_WIDTH = {0: 208, 1: 192, 2: 176}
HOME_ROW_HEIGHT = {0: 40, 1: 34, 2: 30}
HOME_ROW_RADIUS = {0: 12, 1: 10, 2: 9}
ACTION_BUTTON_WIDTH = 78
ACTION_BUTTON_HEIGHT = 28
ACTION_GAP = 14
ACTION_BOTTOM_MARGIN = 36
ACTION_BAR_HEIGHT = 42
SYSTEM_HEADER_Y = 50
SYSTEM_CONTENT_Y = 66
SYSTEM_BUTTON_WIDTH = 76
SYSTEM_BUTTON_HEIGHT = 26
SYSTEM_BUTTON_GAP = 14
SYSTEM_BUTTON_RADIUS = 14
DIALOG_MARGIN = 14
DIALOG_TOP = 35
DIALOG_RADIUS = 14
DIALOG_BORDER = 2
PROGRESS_BAR_HEIGHT = 14


# ── View Helpers ────────────────────────────────────────────────────


@dataclass(slots=True)
class Action:
    id: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label}


@dataclass(slots=True)
class Spacer:
    size: str = "medium"

    def to_dict(self) -> dict[str, str]:
        return {"type": "spacer", "size": self.size}


@dataclass(slots=True)
class Divider:
    def to_dict(self) -> dict[str, str]:
        return {"type": "divider"}


@dataclass(slots=True)
class Value:
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"type": "value", "text": self.text}


@dataclass(slots=True)
class TextComponent:
    text: str
    style: str = "body"

    def to_dict(self) -> dict[str, str]:
        return {"type": "text", "text": self.text, "style": self.style}


@dataclass(slots=True)
class ButtonRow:
    actions: list[Action] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "button_row",
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass(slots=True)
class SystemPage:
    title: str
    components: list[Spacer | Divider | Value | TextComponent | ButtonRow]
    selected: int = 0

    def to_view(self) -> dict[str, Any]:
        return {
            "kind": "system_page",
            "title": self.title,
            "components": [c.to_dict() for c in self.components],
            "selected": self.selected,
        }


# ── Validation + Patch ──────────────────────────────────────────────


class UIModelError(ValueError):
    pass


def validate_view(view: Any) -> dict[str, Any]:
    if not isinstance(view, dict):
        raise UIModelError("View must be an object")
    candidate = copy.deepcopy(view)
    try:
        jsonschema.validate(candidate, load_ui_view_schema())
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path)
        prefix = f"{location}: " if location else ""
        raise UIModelError(f"{prefix}{exc.message}") from exc

    if candidate["kind"] == "list":
        items = candidate["items"]
        if items and candidate["selected"] >= len(items):
            raise UIModelError("selected must reference an existing list item")
        if not items and candidate["selected"] != 0:
            raise UIModelError("selected must be 0 when the list is empty")
    if candidate["kind"] in {"text", "chat"}:
        _validate_actions(candidate)
    if candidate["kind"] == "system_page":
        action_count = _system_page_action_count(candidate["components"])
        if action_count == 0 and candidate["selected"] != 0:
            raise UIModelError(
                "selected must be 0 when the system page has no actions"
            )
        if action_count > 0 and candidate["selected"] >= action_count:
            raise UIModelError(
                "selected must reference an existing system page action"
            )
    return candidate


def apply_patch(
    current_view: dict[str, Any],
    operations: Any,
) -> dict[str, Any]:
    if not isinstance(operations, list) or not operations:
        raise UIModelError("operations must be a non-empty array")

    result = copy.deepcopy(current_view)
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise UIModelError(f"operations.{index} must be an object")
        op = operation.get("op")
        path = operation.get("path")
        if op not in {"replace", "append_text", "append_item", "remove"}:
            raise UIModelError(f"operations.{index}.op is not supported")
        if not isinstance(path, str) or not path.startswith("/"):
            raise UIModelError(f"operations.{index}.path must be a JSON pointer")
        tokens = _parse_pointer(path)
        if not tokens or tokens[0] == "kind":
            raise UIModelError("The view kind cannot be patched")

        if op == "replace":
            if "value" not in operation:
                raise UIModelError(f"operations.{index}.value is required")
            parent, key = _resolve_parent(result, tokens)
            _replace(parent, key, copy.deepcopy(operation["value"]))
        elif op == "append_text":
            value = operation.get("value")
            if not isinstance(value, str):
                raise UIModelError(f"operations.{index}.value must be a string")
            parent, key = _resolve_parent(result, tokens)
            existing = _get(parent, key)
            if not isinstance(existing, str):
                raise UIModelError("append_text target must be a string")
            _replace(parent, key, existing + value)
        elif op == "append_item":
            value = operation.get("value")
            target = _resolve_value(result, tokens)
            if not isinstance(target, list):
                raise UIModelError("append_item target must be an array")
            target.append(copy.deepcopy(value))
        else:
            parent, key = _resolve_parent(result, tokens)
            _remove(parent, key)

    return validate_view(result)


def _parse_pointer(path: str) -> list[str]:
    if path == "/":
        return [""]
    return [
        token.replace("~1", "/").replace("~0", "~")
        for token in path.lstrip("/").split("/")
    ]


def _resolve_value(root: Any, tokens: list[str]) -> Any:
    value = root
    for token in tokens:
        value = _get(value, token)
    return value


def _resolve_parent(root: Any, tokens: list[str]) -> tuple[Any, str]:
    if not tokens:
        raise UIModelError("Patch path cannot target the document root")
    parent = _resolve_value(root, tokens[:-1]) if len(tokens) > 1 else root
    return parent, tokens[-1]


def _get(parent: Any, key: str) -> Any:
    if isinstance(parent, dict):
        if key not in parent:
            raise UIModelError(f"Patch path does not exist: {key}")
        return parent[key]
    if isinstance(parent, list):
        index = _list_index(parent, key)
        return parent[index]
    raise UIModelError("Patch path traverses a scalar value")


def _replace(parent: Any, key: str, value: Any) -> None:
    if isinstance(parent, dict):
        if key not in parent:
            raise UIModelError(f"Patch path does not exist: {key}")
        parent[key] = value
        return
    if isinstance(parent, list):
        parent[_list_index(parent, key)] = value
        return
    raise UIModelError("Patch target is not replaceable")


def _remove(parent: Any, key: str) -> None:
    if isinstance(parent, dict):
        if key not in parent:
            raise UIModelError(f"Patch path does not exist: {key}")
        del parent[key]
        return
    if isinstance(parent, list):
        del parent[_list_index(parent, key)]
        return
    raise UIModelError("Patch target is not removable")


def _list_index(values: list[Any], key: str) -> int:
    try:
        index = int(key)
    except ValueError as exc:
        raise UIModelError(f"Array index is invalid: {key}") from exc
    if index < 0 or index >= len(values):
        raise UIModelError(f"Array index is out of range: {index}")
    return index


def _system_page_action_count(components: list[dict[str, Any]]) -> int:
    total = 0
    for component in components:
        if component["type"] == "button_row":
            total += len(component["actions"])
    return total


def _validate_actions(candidate: dict[str, Any]) -> None:
    actions = candidate.get("actions")
    selected = candidate.get("selected")
    if actions is None:
        if selected is not None:
            raise UIModelError("selected requires actions")
        return
    if selected is None:
        raise UIModelError("actions require selected")
    if selected >= len(actions):
        raise UIModelError("selected must reference an existing action")


# ── Rendering ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RenderedFrame:
    width: int
    height: int
    rgb565: bytes
    image: Image.Image


class PillowRenderer:
    def __init__(
        self,
        width: int = 240,
        height: int = 280,
        *,
        font_path: str | Path | None = None,
        bold_font_path: str | Path | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.title_font = load_ui_font(
            TITLE_SIZE,
            bold=True,
            font_path=font_path,
            bold_font_path=bold_font_path,
        )
        self.body_font = load_ui_font(
            BODY_SIZE,
            font_path=font_path,
            bold_font_path=bold_font_path,
        )
        self.menu_font = load_ui_font(
            BODY_SIZE,
            weight="Medium",
            font_path=font_path,
            bold_font_path=bold_font_path,
        )
        self.home_near_font = load_ui_font(
            15,
            weight="Medium",
            font_path=font_path,
            bold_font_path=bold_font_path,
        )
        self.home_far_font = load_ui_font(
            14,
            weight="Medium",
            font_path=font_path,
            bold_font_path=bold_font_path,
        )
        self.small_font = load_ui_font(
            SMALL_SIZE,
            font_path=font_path,
            bold_font_path=bold_font_path,
        )

    def render(
        self,
        view: dict[str, Any] | None,
        *,
        asset_root: Path | None = None,
    ) -> RenderedFrame:
        image = Image.new("RGB", (self.width, self.height), DARK.bg)
        if view is None:
            self._render_empty(image)
        else:
            method = getattr(self, f"_render_{view['kind']}")
            method(image, view, asset_root)
        return RenderedFrame(
            width=self.width,
            height=self.height,
            rgb565=self._to_rgb565(image),
            image=image,
        )

    # ── View renderers ──────────────────────────────────────────

    def _render_empty(self, image: Image.Image) -> None:
        draw = ImageDraw.Draw(image)
        draw.text(
            (PADDING + 2, 18),
            "LAFVIN HAT",
            font=self.title_font,
            fill=DARK.text_primary,
        )
        draw.text(
            (PADDING + 2, 52),
            "No app in foreground",
            font=self.body_font,
            fill=DARK.text_muted,
        )

    def _render_text(
        self,
        image: Image.Image,
        view: dict[str, Any],
        _asset_root: Path | None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        y = self._header(draw, view)
        color = self._emphasis_color(view.get("emphasis", "normal"))
        bottom_reserved = self._action_bar_reserved(view)
        self._draw_wrapped(
            draw,
            view["text"],
            PADDING,
            y,
            self.body_font,
            color,
            self.width - PADDING * 2,
            max_height=self.height - y - 8 - bottom_reserved,
        )
        self._render_action_bar(draw, view)

    def _render_chat(
        self,
        image: Image.Image,
        view: dict[str, Any],
        _asset_root: Path | None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        y = self._header(draw, view)
        bottom_reserved = self._action_bar_reserved(view)
        for message, lines in self._visible_chat_messages(
            view["messages"],
            available_height=self.height - y - CHAT_GAP - bottom_reserved,
        ):
            role = message["role"]
            if role == "user":
                fill, outline = DARK.msg_user_fill, DARK.msg_user_outline
            else:
                fill, outline = DARK.msg_assistant_fill, DARK.msg_assistant_outline
            box_height = max(CHAT_BOX_MIN, len(lines) * CHAT_LINE_HEIGHT + CHAT_BOX_PAD)
            draw.rounded_rectangle(
                (10, y, self.width - 10, y + box_height),
                radius=9,
                fill=fill,
                outline=outline,
            )
            draw.text(
                (18, y + 6),
                "You" if role == "user" else "Assistant",
                font=self.small_font,
                fill=outline,
            )
            for line_index, line in enumerate(lines):
                draw.text(
                    (18, y + 22 + line_index * CHAT_LINE_HEIGHT),
                    line,
                    font=self.body_font,
                    fill=DARK.msg_text,
                )
            y += box_height + CHAT_GAP

        self._render_action_bar(draw, view)

    def _render_list(
        self,
        image: Image.Image,
        view: dict[str, Any],
        _asset_root: Path | None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, self.width, self.height), fill=HOME_LIGHT.bg)
        draw.text((22, 10), view.get("title", "LAFVIN HAT"), font=self.title_font, fill=HOME_LIGHT.text)
        draw.line(
            (8, 42, self.width - 8, 42),
            fill=HOME_LIGHT.divider,
            width=1,
        )
        items = view["items"]
        selected = view["selected"]
        for offset, item in self._home_visible_items(items, selected):
            distance = abs(offset)
            width = HOME_ROW_WIDTH[distance]
            height = HOME_ROW_HEIGHT[distance]
            x = (self.width - width) // 2
            y = HOME_ROW_Y[offset]
            if distance == 0:
                fill = HOME_LIGHT.row_selected_fill
                text_fill = HOME_LIGHT.row_selected_text
                font = self.menu_font
            elif distance == 1:
                fill = HOME_LIGHT.row_near_fill
                text_fill = HOME_LIGHT.row_near_text
                font = self.home_near_font
            else:
                fill = HOME_LIGHT.row_far_fill
                text_fill = HOME_LIGHT.row_far_text
                font = self.home_far_font
            draw.rounded_rectangle(
                (x, y, x + width, y + height),
                radius=HOME_ROW_RADIUS[distance],
                fill=fill,
            )
            label = str(item["label"])
            label_x = x + 12
            label_y = self._centered_text_y(draw, label, font, y, height)
            draw.text(
                (label_x, label_y),
                label,
                font=font,
                fill=text_fill,
            )
            meta = str(item.get("meta", ""))
            if distance == 0 and meta and meta.lower() not in {
                "installed",
                "stopped",
            }:
                meta = meta[:12]
                meta_box = draw.textbbox((0, 0), meta, font=self.small_font)
                meta_width = meta_box[2] - meta_box[0]
                meta_x = x + width - 12 - meta_width
                label_box = draw.textbbox((0, 0), label, font=font)
                label_width = label_box[2] - label_box[0]
                if meta_x >= label_x + label_width + 8:
                    meta_y = self._centered_text_y(
                        draw,
                        meta,
                        self.small_font,
                        y,
                        height,
                    )
                    draw.text(
                        (meta_x, meta_y),
                        meta,
                        font=self.small_font,
                        fill=HOME_LIGHT.row_selected_text,
                    )

    @staticmethod
    def _home_visible_items(
        items: list[dict[str, Any]],
        selected: int,
    ) -> list[tuple[int, dict[str, Any]]]:
        if not items:
            return []
        selected %= len(items)
        visible: list[tuple[int, dict[str, Any]]] = []
        used_indices: set[int] = set()
        for offset in (0, -1, 1, -2, 2):
            index = (selected + offset) % len(items)
            if index in used_indices:
                continue
            visible.append((offset, items[index]))
            used_indices.add(index)
            if len(visible) == min(LIST_VISIBLE, len(items)):
                break
        return sorted(visible, key=lambda row: row[0])

    @staticmethod
    def _centered_text_y(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.ImageFont,
        top: int,
        height: int,
    ) -> int:
        box = draw.textbbox((0, 0), text, font=font)
        text_height = box[3] - box[1]
        return top + (height - text_height) // 2 - box[1]

    def _render_progress(
        self,
        image: Image.Image,
        view: dict[str, Any],
        _asset_root: Path | None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        y = self._header(draw, view)
        self._draw_wrapped(
            draw,
            view["message"],
            PADDING + 2,
            y + 22,
            self.body_font,
            "#dce4ef",
            self.width - (PADDING + 2) * 2,
        )
        bar_y = self.height - 60
        bar_left = PADDING + 2
        bar_right = self.width - PADDING - 2
        draw.rounded_rectangle(
            (bar_left, bar_y, bar_right, bar_y + PROGRESS_BAR_HEIGHT),
            7,
            fill=DARK.progress_track,
        )
        value = view["value"]
        if value is None:
            offset = 20
            draw.rounded_rectangle(
                (offset, bar_y, offset + 60, bar_y + PROGRESS_BAR_HEIGHT),
                7,
                fill=DARK.progress_fill,
            )
        else:
            width = int((bar_right - bar_left) * float(value))
            if width:
                draw.rounded_rectangle(
                    (bar_left, bar_y, bar_left + width, bar_y + PROGRESS_BAR_HEIGHT),
                    7,
                    fill=DARK.progress_fill,
                )

    def _render_image(
        self,
        image: Image.Image,
        view: dict[str, Any],
        asset_root: Path | None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        y = self._header(draw, view)
        try:
            source = self._resolve_asset(asset_root, view["source"]["path"])
            with Image.open(source) as opened:
                content = opened.convert("RGB")
                size = (self.width - 20, self.height - y - 10)
                if view["fit"] == "cover":
                    content = ImageOps.fit(
                        content, size, method=Image.Resampling.LANCZOS
                    )
                else:
                    content.thumbnail(size, Image.Resampling.LANCZOS)
                x = (self.width - content.width) // 2
                image.paste(content, (x, y))
        except (OSError, ValueError):
            draw.rounded_rectangle(
                (12, y, self.width - 12, self.height - 12),
                10,
                outline=DARK.image_error_outline,
            )
            draw.text(
                (24, y + 24),
                "Image unavailable",
                font=self.body_font,
                fill=DARK.image_error_text,
            )

    def _render_system_page(
        self,
        image: Image.Image,
        view: dict[str, Any],
        _asset_root: Path | None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, self.width, self.height), fill=LIGHT.bg)
        draw.text((22, 10), view["title"], font=self.title_font, fill=LIGHT.text)
        draw.line(
            (0, SYSTEM_HEADER_Y, self.width, SYSTEM_HEADER_Y),
            fill=LIGHT.header_line,
            width=2,
        )

        y = SYSTEM_CONTENT_Y
        action_index = 0
        selected = view["selected"]
        for component in view["components"]:
            component_type = component["type"]
            if component_type == "spacer":
                y += {"small": 12, "medium": 24, "large": 42}[component["size"]]
            elif component_type == "divider":
                draw.line(
                    (22, y, self.width - 22, y),
                    fill=LIGHT.divider,
                    width=1,
                )
                y += 12
            elif component_type == "value":
                self._system_centered_text(draw, component["text"], y, self.title_font)
                y += 36
            elif component_type == "text":
                style = component.get("style", "body")
                font = self.small_font if style == "small" else self.title_font
                line_height = 16 if style == "small" else 24
                lines = self._wrap(component["text"], font, self.width - 44)
                for line in lines:
                    draw.text((22, y), line, font=font, fill=LIGHT.text)
                    y += line_height
                y += 4
            elif component_type == "button_row":
                actions = component["actions"]
                total_width = (
                    len(actions) * SYSTEM_BUTTON_WIDTH
                    + (len(actions) - 1) * SYSTEM_BUTTON_GAP
                )
                x = (self.width - total_width) / 2
                for action in actions:
                    self._system_button(
                        draw,
                        (int(x), y, int(x + SYSTEM_BUTTON_WIDTH), y + SYSTEM_BUTTON_HEIGHT),
                        action["label"],
                        selected=action_index == selected,
                    )
                    x += SYSTEM_BUTTON_WIDTH + SYSTEM_BUTTON_GAP
                    action_index += 1
                y += SYSTEM_BUTTON_HEIGHT + 8

    def _render_dialog(
        self,
        image: Image.Image,
        view: dict[str, Any],
        _asset_root: Path | None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        color = self._emphasis_color(view.get("emphasis", "normal"))
        draw.rounded_rectangle(
            (
                DIALOG_MARGIN,
                DIALOG_TOP,
                self.width - DIALOG_MARGIN,
                self.height - DIALOG_TOP,
            ),
            DIALOG_RADIUS,
            fill=DARK.dialog_fill,
            outline=color,
            width=DIALOG_BORDER,
        )
        draw.text((28, 56), view["title"], font=self.title_font, fill=color)
        self._draw_wrapped(
            draw,
            view["message"],
            28,
            92,
            self.body_font,
            DARK.dialog_text,
            self.width - 56,
        )
        if len(view["actions"]) == 1:
            action = view["actions"][0]
            button = (
                self.width // 2 - 48,
                self.height - 64,
                self.width // 2 + 48,
                self.height - 36,
            )
            draw.rounded_rectangle(
                button, radius=SYSTEM_BUTTON_RADIUS, fill=LIGHT.button_selected_fill
            )
            left, top, right, bottom = draw.textbbox(
                (0, 0), action, font=self.body_font
            )
            draw.text(
                (
                    (button[0] + button[2] - (right - left)) / 2,
                    (button[1] + button[3] - (bottom - top)) / 2 - 1,
                ),
                action,
                font=self.body_font,
                fill=LIGHT.button_text,
            )
            return
        actions = "  ".join(view["actions"])
        draw.text(
            (28, self.height - 65),
            actions,
            font=self.small_font,
            fill=DARK.text_muted,
        )

    # ── Shared drawing helpers ──────────────────────────────────

    def _header(self, draw: ImageDraw.ImageDraw, view: dict[str, Any]) -> int:
        title = view.get("title") or view["kind"].replace("_", " ").title()
        draw.text((PADDING, 12), title, font=self.title_font, fill=DARK.text_primary)
        status = view.get("status")
        if status:
            draw.text(
                (PADDING, 38), status, font=self.small_font, fill=DARK.accent
            )
            return 62
        return 48

    def _draw_wrapped(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        x: int,
        y: int,
        font: ImageFont.ImageFont,
        fill: str,
        max_width: int,
        *,
        max_height: int | None = None,
    ) -> None:
        lines = self._wrap(text, font, max_width)
        if max_height is not None:
            lines = lines[: max(0, max_height // LINE_HEIGHT)]
        for index, line in enumerate(lines):
            draw.text((x, y + index * LINE_HEIGHT), line, font=font, fill=fill)

    def _action_bar_reserved(self, view: dict[str, Any]) -> int:
        return ACTION_BAR_HEIGHT if view.get("actions") else 0

    def _render_action_bar(
        self,
        draw: ImageDraw.ImageDraw,
        view: dict[str, Any],
    ) -> None:
        actions = view.get("actions")
        if not actions:
            return
        selected = view.get("selected", 0)
        total_width = (
            len(actions) * ACTION_BUTTON_WIDTH
            + (len(actions) - 1) * ACTION_GAP
        )
        x = (self.width - total_width) / 2
        y = self.height - ACTION_BOTTOM_MARGIN
        for index, action in enumerate(actions):
            fill = (
                DARK.action_selected_fill
                if index == selected
                else DARK.action_fill
            )
            draw.rounded_rectangle(
                (int(x), y, int(x + ACTION_BUTTON_WIDTH), y + ACTION_BUTTON_HEIGHT),
                radius=SYSTEM_BUTTON_RADIUS,
                fill=fill,
            )
            left, top, right, bottom = draw.textbbox(
                (0, 0), action["label"], font=self.body_font
            )
            draw.text(
                (
                    x + (ACTION_BUTTON_WIDTH - (right - left)) / 2,
                    y + (ACTION_BUTTON_HEIGHT - (bottom - top)) / 2 - 1,
                ),
                action["label"],
                font=self.body_font,
                fill=DARK.action_text,
            )
            x += ACTION_BUTTON_WIDTH + ACTION_GAP

    def _system_centered_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        y: int,
        font: ImageFont.ImageFont,
    ) -> None:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        draw.text(
            (
                (self.width - (right - left)) / 2,
                y + (36 - (bottom - top)) / 2,
            ),
            text,
            font=font,
            fill=LIGHT.text,
        )

    def _system_button(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        label: str,
        *,
        selected: bool = False,
    ) -> None:
        draw.rounded_rectangle(
            box,
            radius=SYSTEM_BUTTON_RADIUS,
            fill=LIGHT.button_selected_fill if selected else LIGHT.button_fill,
        )
        left, top, right, bottom = draw.textbbox(
            (0, 0), label, font=self.body_font
        )
        draw.text(
            (
                (box[0] + box[2] - (right - left)) / 2,
                (box[1] + box[3] - (bottom - top)) / 2 - 1,
            ),
            label,
            font=self.body_font,
            fill=LIGHT.button_text,
        )

    def _visible_chat_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        available_height: int,
    ) -> list[tuple[dict[str, Any], list[str]]]:
        visible: list[tuple[dict[str, Any], list[str]]] = []
        remaining = available_height
        for message in reversed(messages):
            lines = self._wrap(
                message["text"],
                self.body_font,
                self.width - 36,
            )
            max_lines = max(1, (remaining - CHAT_BOX_PAD) // CHAT_LINE_HEIGHT)
            if max_lines <= 0:
                break
            if len(lines) > max_lines:
                lines = lines[-max_lines:]
            box_height = max(CHAT_BOX_MIN, len(lines) * CHAT_LINE_HEIGHT + CHAT_BOX_PAD)
            if box_height > remaining:
                break
            visible.append((message, lines))
            remaining -= box_height + CHAT_GAP
        visible.reverse()
        return visible

    # ── Text utilities ──────────────────────────────────────────

    def _wrap(
        self,
        text: str,
        font: ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        if max_width <= 0:
            raise ValueError("max_width must be positive")
        lines: list[str] = []
        for paragraph in text.splitlines() or [""]:
            lines.extend(
                self._wrap_paragraph(paragraph, font, max_width) or [""]
            )
        return lines

    def _wrap_paragraph(
        self,
        paragraph: str,
        font: ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        remaining = paragraph
        lines: list[str] = []
        while remaining:
            split_at = 0
            last_break = 0
            for index, char in enumerate(remaining, start=1):
                if char.isspace() or char in "-/":
                    last_break = index
                if self._text_width(remaining[:index], font) > max_width:
                    split_at = last_break or max(1, index - 1)
                    break
            if split_at == 0:
                lines.append(remaining.rstrip())
                break
            line = remaining[:split_at].rstrip()
            if line:
                lines.append(line)
            remaining = remaining[split_at:].lstrip()
        return lines

    def _text_width(
        self,
        text: str,
        font: ImageFont.ImageFont,
    ) -> float:
        getlength = getattr(font, "getlength", None)
        if callable(getlength):
            return float(getlength(text))
        left, _top, right, _bottom = font.getbbox(text)
        return float(right - left)

    # ── Asset utilities ────────────────────────────────────────

    def _resolve_asset(self, asset_root: Path | None, value: str) -> Path:
        if asset_root is None:
            raise ValueError("Image view requires an asset root")
        candidate = (asset_root / value).resolve()
        root = asset_root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("Image path escapes the app directory")
        return candidate

    def _emphasis_color(self, emphasis: str) -> str:
        return {
            "normal": DARK.emphasis_normal,
            "primary": DARK.emphasis_primary,
            "warning": DARK.emphasis_warning,
            "danger": DARK.emphasis_danger,
        }[emphasis]

    def _to_rgb565(self, image: Image.Image) -> bytes:
        array = np.asarray(image.convert("RGB"), dtype=np.uint16)
        red = array[:, :, 0]
        green = array[:, :, 1]
        blue = array[:, :, 2]
        rgb565 = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        return rgb565.astype(">u2").tobytes()
