from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .fonts import load_korean_ui_font, load_ui_font


DEFAULT_WIDTH = 240
DEFAULT_HEIGHT = 280


@dataclass(frozen=True, slots=True)
class Theme:
    background: tuple[int, int, int] = (245, 245, 245)
    text: tuple[int, int, int] = (0, 0, 0)
    muted: tuple[int, int, int] = (74, 74, 74)
    line: tuple[int, int, int] = (20, 20, 20)
    accent: tuple[int, int, int] = (50, 50, 50)
    danger: tuple[int, int, int] = (180, 40, 40)
    button: tuple[int, int, int] = (200, 200, 200)
    button_selected: tuple[int, int, int] = (92, 150, 255)
    button_text: tuple[int, int, int] = (0, 0, 0)
    button_selected_text: tuple[int, int, int] = (255, 255, 255)
    user_message: tuple[int, int, int] = (78, 136, 240)
    user_message_text: tuple[int, int, int] = (255, 255, 255)
    assistant_message: tuple[int, int, int] = (255, 255, 255)
    assistant_message_outline: tuple[int, int, int] = (68, 210, 142)


DEFAULT_THEME = Theme()


@dataclass(frozen=True, slots=True)
class StatusRow:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    text: str


class Canvas:
    """Small app-facing Raw Frame drawing helper."""

    def __init__(
        self,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        theme: Theme = DEFAULT_THEME,
        font_path: str | Path | None = None,
        bold_font_path: str | Path | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.theme = theme
        self.title_font = load_ui_font(
            22,
            bold=True,
            font_path=font_path,
            bold_font_path=bold_font_path,
        )
        self.large_font = load_ui_font(
            32,
            bold=True,
            font_path=font_path,
            bold_font_path=bold_font_path,
        )
        self.body_font = load_ui_font(
            19,
            bold=False,
            font_path=font_path,
            bold_font_path=bold_font_path,
        )
        self.small_font = load_ui_font(
            14,
            weight="Medium",
            font_path=font_path,
            bold_font_path=bold_font_path,
        )
        self._korean_body_font: ImageFont.ImageFont | None = None
        self.image = Image.new("RGB", (width, height), theme.background)
        self.draw = ImageDraw.Draw(self.image)

    def clear(self) -> "Canvas":
        self.draw.rectangle(
            (0, 0, self.width, self.height),
            fill=self.theme.background,
        )
        return self

    def title(self, text: str, *, x: int = 22, y: int = 10) -> "Canvas":
        self.draw.text((x, y), text, fill=self.theme.text, font=self.title_font)
        return self

    def divider(self, *, y: int = 42, margin: int = 8) -> "Canvas":
        self.draw.line(
            (margin, y, self.width - margin, y),
            fill=self.theme.line,
            width=1,
        )
        return self

    def text(
        self,
        text: str,
        *,
        x: int = 22,
        y: int = 60,
        width: int | None = None,
        line_height: int = 24,
        fill: tuple[int, int, int] | None = None,
        font: ImageFont.ImageFont | None = None,
    ) -> int:
        active_font = font or self.body_font
        active_fill = fill or self.theme.text
        max_width = width or self.width - x - 16
        current_y = y
        for line in self.wrap(text, active_font, max_width):
            self.draw.text(
                (x, current_y),
                line,
                fill=active_fill,
                font=active_font,
            )
            current_y += line_height
        return current_y

    def center_text(
        self,
        text: str,
        *,
        y: int,
        width: int | None = None,
        x: int = 0,
        fill: tuple[int, int, int] | None = None,
        font: ImageFont.ImageFont | None = None,
        size: str = "body",
    ) -> "Canvas":
        active_font = font or self._font_for_size(size)
        active_fill = fill or self.theme.text
        active_width = width or self.width
        left, top, right, bottom = self.draw.textbbox(
            (0, 0),
            text,
            font=active_font,
        )
        text_width = right - left
        text_height = bottom - top
        text_x = x + max(0, active_width - text_width) // 2
        self.draw.text(
            (text_x, y - text_height // 2),
            text,
            fill=active_fill,
            font=active_font,
        )
        return self

    def button(
        self,
        label: str,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
        selected: bool = False,
        radius: int = 12,
    ) -> "Canvas":
        fill = self.theme.button_selected if selected else self.theme.button
        text_fill = (
            self.theme.button_selected_text
            if selected
            else self.theme.button_text
        )
        self.draw.rounded_rectangle(
            (x, y, x + width, y + height),
            radius=radius,
            fill=fill,
        )
        self._center_text_in_box(
            label,
            x=x,
            y=y,
            width=width,
            height=height,
            fill=text_fill,
            font=self.body_font,
        )
        return self

    def button_row(
        self,
        labels: Sequence[str],
        *,
        selected: int | None = None,
        y: int,
        button_width: int = 74,
        button_height: int = 26,
        gap: int = 22,
    ) -> "Canvas":
        if not labels:
            return self
        total_width = len(labels) * button_width + (len(labels) - 1) * gap
        x = max(0, (self.width - total_width) // 2)
        for index, label in enumerate(labels):
            self.button(
                label,
                x=x + index * (button_width + gap),
                y=y,
                width=button_width,
                height=button_height,
                selected=selected == index,
            )
        return self

    def action_bar(
        self,
        labels: Sequence[str],
        *,
        selected: int | None = None,
        y: int | None = None,
        button_width: int = 82,
        button_height: int = 28,
        gap: int = 18,
    ) -> "Canvas":
        return self.button_row(
            labels,
            selected=selected,
            y=y if y is not None else self.height - 44,
            button_width=button_width,
            button_height=button_height,
            gap=gap,
        )

    def text_page(
        self,
        title: str,
        text: str,
        *,
        status: str | None = None,
        actions: Sequence[str] | None = None,
        selected: int | None = None,
        emphasis: str = "primary",
    ) -> "Canvas":
        self.clear().title(title).divider()
        current_y = 58
        if status:
            status_text = _display_status(status)
            self.draw.text(
                (22, 48),
                status_text,
                fill=self._emphasis_fill(emphasis, muted_default=True),
                font=self.small_font,
            )
            current_y = 70
        content_height = self.height - current_y - (58 if actions else 14)
        self.text_box(
            text,
            x=22,
            y=current_y,
            width=self.width - 44,
            height=content_height,
            fill=self._emphasis_fill(emphasis),
        )
        if actions:
            self.action_bar(actions, selected=selected)
        return self

    def scrolling_text_page(
        self,
        title: str,
        text: str,
        *,
        scroll_top: float = 0,
        status: str | None = None,
        actions: Sequence[str] | None = None,
        selected: int | None = None,
        emphasis: str = "primary",
    ) -> "Canvas":
        self.clear().title(title).divider()
        current_y = 58
        if status:
            self.draw.text(
                (22, 48),
                _display_status(status),
                fill=self._emphasis_fill(emphasis, muted_default=True),
                font=self.small_font,
            )
            current_y = 70
        content_height = self.height - current_y - (58 if actions else 14)
        self.text_box(
            text,
            x=22,
            y=current_y,
            width=self.width - 44,
            height=content_height,
            fill=self._emphasis_fill(emphasis),
            scroll_top=scroll_top,
        )
        if actions:
            self.action_bar(actions, selected=selected)
        return self

    def text_box(
        self,
        text: str,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
        line_height: int = 24,
        fill: tuple[int, int, int] | None = None,
        font: ImageFont.ImageFont | None = None,
        scroll_to_bottom: bool = False,
        scroll_top: float = 0,
    ) -> "Canvas":
        active_font = font or self.body_font
        active_fill = fill or self.theme.text
        lines = self.wrap(text, active_font, width)
        max_lines = max(1, height // line_height)
        if scroll_to_bottom:
            visible_lines = lines[-max_lines:]
            offset_y = 0
        else:
            normalized_scroll = max(0, int(scroll_top))
            first_line = min(len(lines), normalized_scroll // line_height)
            offset_y = -(normalized_scroll % line_height)
            visible_lines = lines[
                first_line:first_line + max_lines + (1 if offset_y else 0)
            ]

        viewport = Image.new("RGB", (width, height), self.theme.background)
        viewport_draw = ImageDraw.Draw(viewport)
        current_y = offset_y
        for line in visible_lines:
            if current_y >= height:
                break
            viewport_draw.text(
                (0, current_y),
                line,
                fill=active_fill,
                font=active_font,
            )
            current_y += line_height
        self.image.paste(viewport, (x, y))
        return self

    def text_scroll_target(
        self,
        text: str,
        char_end: int,
        *,
        width: int,
        height: int,
        line_height: int = 24,
        focus_ratio: float = 0.65,
        font: ImageFont.ImageFont | None = None,
    ) -> float:
        if char_end <= 0 or height <= 0:
            return 0.0
        active_font = font or self.body_font
        value = str(text)
        lines = self.wrap(value, active_font, width)
        prefix = value[:min(len(value), char_end)]
        prefix_lines = self.wrap(prefix, active_font, width)
        target_line = max(0, len(prefix_lines) - 1)
        content_height = len(lines) * line_height
        max_scroll = max(0, content_height - height)
        desired = target_line * line_height - int(height * focus_ratio)
        return float(min(max_scroll, max(0, desired)))

    def message_list(
        self,
        messages: Sequence[ChatMessage | Mapping[str, object] | object],
        *,
        x: int = 12,
        y: int = 58,
        width: int | None = None,
        height: int | None = None,
        line_height: int = 19,
        gap: int = 8,
        scroll_to_bottom: bool = True,
        align_bottom: bool = True,
    ) -> "Canvas":
        active_width = width or self.width - x * 2
        active_height = height or self.height - y - 54
        blocks = [
            self._message_block(
                _coerce_message(message),
                width=active_width,
                line_height=line_height,
            )
            for message in messages
        ]
        if scroll_to_bottom:
            blocks = _bottom_fit_blocks(blocks, active_height, gap)

        total_height = sum(block["height"] for block in blocks)
        if blocks:
            total_height += gap * (len(blocks) - 1)
        current_y = y
        if align_bottom:
            current_y += max(0, active_height - total_height)
        for block in blocks:
            if current_y >= y + active_height:
                break
            self._draw_message_block(
                block,
                x=x,
                y=current_y,
                width=active_width,
                line_height=line_height,
                bottom=y + active_height,
            )
            current_y += block["height"] + gap
        return self

    def chat_page(
        self,
        title: str,
        messages: Sequence[ChatMessage | Mapping[str, object] | object],
        *,
        status: str | None = None,
        streaming: bool = False,
        actions: Sequence[str] | None = None,
        selected: int | None = None,
    ) -> "Canvas":
        self.clear().title(title).divider()
        message_y = 58
        if status:
            status_text = _display_status(status)
            if streaming:
                status_text = f"{status_text}..."
            self.draw.text(
                (22, 48),
                status_text,
                fill=self.theme.muted,
                font=self.small_font,
            )
            message_y = 66
        bottom_margin = 58 if actions else 12
        visible_messages = list(messages)
        awaiting_assistant_text = (
            streaming
            and bool(visible_messages)
            and _is_empty_assistant_placeholder(visible_messages[-1])
        )
        if awaiting_assistant_text:
            visible_messages.pop()
        self.message_list(
            visible_messages,
            y=message_y,
            height=self.height - message_y - bottom_margin,
            align_bottom=not awaiting_assistant_text,
        )
        if actions:
            self.action_bar(actions, selected=selected)
        return self

    def status_rows(
        self,
        rows: Sequence[StatusRow],
        *,
        x: int = 22,
        y: int = 64,
        line_height: int = 25,
    ) -> "Canvas":
        current_y = y
        for row in rows:
            self.draw.text(
                (x, current_y),
                f"{row.label}:{row.value}",
                fill=self.theme.text,
                font=self.body_font,
            )
            current_y += line_height
        return self

    def system_status_page(
        self,
        rows: Sequence[StatusRow],
        *,
        title: str = "System Status",
    ) -> "Canvas":
        return (
            self.clear()
            .title(title)
            .divider()
            .status_rows(rows)
        )

    def error_page(
        self,
        title: str,
        message: str,
    ) -> "Canvas":
        self.clear().title(title).divider()
        self.text(message, y=64, fill=self.theme.accent)
        return self

    def render(self) -> bytes:
        return image_to_rgb565_be(self.image)

    async def present(self, frame: Any) -> dict[str, Any]:
        frame.write(self.render())
        return await frame.commit()

    def wrap(
        self,
        text: str,
        font: ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        lines: list[str] = []
        for paragraph in str(text).splitlines() or [""]:
            lines.extend(_wrap_paragraph(paragraph, font, max_width) or [""])
        return lines

    def _font_for_size(self, size: str) -> ImageFont.ImageFont:
        if size == "large":
            return self.large_font
        if size == "title":
            return self.title_font
        if size == "small":
            return self.small_font
        return self.body_font

    def _emphasis_fill(
        self,
        emphasis: str,
        *,
        muted_default: bool = False,
    ) -> tuple[int, int, int]:
        if emphasis == "danger":
            return self.theme.danger
        if emphasis == "muted":
            return self.theme.muted
        if muted_default:
            return self.theme.muted
        return self.theme.text

    def _message_block(
        self,
        message: ChatMessage,
        *,
        width: int,
        line_height: int,
    ) -> dict[str, object]:
        body_font = self._body_font_for_message(message)
        lines = self.wrap(message.text, body_font, width - 20)
        height = 30 + max(1, len(lines)) * line_height + 10
        return {
            "message": message,
            "font": body_font,
            "lines": lines or [""],
            "height": height,
            "line_height": line_height,
        }

    def _draw_message_block(
        self,
        block: Mapping[str, object],
        *,
        x: int,
        y: int,
        width: int,
        line_height: int,
        bottom: int,
    ) -> None:
        message = block["message"]
        assert isinstance(message, ChatMessage)
        body_font = block.get("font", self.body_font)
        if not hasattr(body_font, "getbbox"):
            body_font = self.body_font
        lines = block["lines"]
        assert isinstance(lines, list)
        height = int(block["height"])
        role = message.role.lower()
        is_user = role == "user"
        fill = self.theme.user_message if is_user else self.theme.assistant_message
        text_fill = self.theme.user_message_text if is_user else self.theme.text
        outline = fill if is_user else self.theme.assistant_message_outline
        self.draw.rounded_rectangle(
            (x, y, x + width, y + height),
            radius=10,
            fill=fill,
            outline=outline,
            width=1,
        )
        self.draw.text(
            (x + 10, y + 7),
            message.role.title(),
            fill=text_fill,
            font=self.small_font,
        )
        current_y = y + 28
        for line in lines:
            if current_y + line_height > bottom:
                break
            self.draw.text(
                (x + 10, current_y),
                str(line),
                fill=text_fill,
                font=body_font,
            )
            current_y += line_height

    def _body_font_for_message(self, message: ChatMessage) -> ImageFont.ImageFont:
        """Use one font for an assistant reply instead of per-character fallback."""

        if message.role.lower() != "assistant" or not _contains_hangul(message.text):
            return self.body_font
        if self._korean_body_font is None:
            self._korean_body_font = load_korean_ui_font(19) or self.body_font
        return self._korean_body_font

    def _center_text_in_box(
        self,
        text: str,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
        fill: tuple[int, int, int],
        font: ImageFont.ImageFont,
    ) -> None:
        left, top, right, bottom = self.draw.textbbox((0, 0), text, font=font)
        text_width = right - left
        text_height = bottom - top
        text_x = x + max(0, width - text_width) // 2
        text_y = y + max(0, height - text_height) // 2 - top
        self.draw.text((text_x, text_y), text, fill=fill, font=font)


def image_to_rgb565_be(image: Image.Image) -> bytes:
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint16)
    red = rgb[:, :, 0]
    green = rgb[:, :, 1]
    blue = rgb[:, :, 2]
    rgb565 = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
    return rgb565.astype(">u2").tobytes()


def _coerce_message(message: ChatMessage | Mapping[str, object] | object) -> ChatMessage:
    if isinstance(message, ChatMessage):
        return message
    if isinstance(message, Mapping):
        role = str(message.get("role", "assistant"))
        text = str(message.get("text", message.get("content", "")))
        return ChatMessage(role, text)
    role = str(getattr(message, "role", "assistant"))
    text = str(getattr(message, "text", getattr(message, "content", "")))
    return ChatMessage(role, text)


def _is_empty_assistant_placeholder(
    message: ChatMessage | Mapping[str, object] | object,
) -> bool:
    coerced = _coerce_message(message)
    return coerced.role.lower() == "assistant" and not coerced.text.strip()


def _display_status(status: str) -> str:
    """Use display casing without changing the App's internal state value."""

    return status[:1].upper() + status[1:]


def _contains_hangul(text: str) -> bool:
    """Return whether text contains a modern Hangul syllable or Jamo."""

    return any(
        "\u1100" <= char <= "\u11ff"
        or "\u3130" <= char <= "\u318f"
        or "\ua960" <= char <= "\ua97f"
        or "\uac00" <= char <= "\ud7a3"
        or "\ud7b0" <= char <= "\ud7ff"
        for char in text
    )


def _bottom_fit_blocks(
    blocks: list[dict[str, object]],
    height: int,
    gap: int,
) -> list[dict[str, object]]:
    visible: list[dict[str, object]] = []
    total = 0
    for block in reversed(blocks):
        block_height = int(block["height"])
        if not visible and block_height > height:
            return [_clip_message_block_to_bottom(block, height)]
        next_total = block_height if not visible else total + gap + block_height
        if visible and next_total > height:
            break
        visible.insert(0, block)
        total = next_total
    return visible


def _clip_message_block_to_bottom(
    block: dict[str, object],
    height: int,
) -> dict[str, object]:
    lines = block["lines"]
    assert isinstance(lines, list)
    line_height = int(block.get("line_height", 19))
    max_lines = max(1, (height - 40) // line_height)
    visible_lines = lines[-max_lines:]
    clipped_height = min(
        height,
        30 + len(visible_lines) * line_height + 10,
    )
    return {
        **block,
        "lines": visible_lines,
        "height": clipped_height,
    }


def _wrap_paragraph(
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    remaining = text
    lines: list[str] = []
    while remaining:
        if _text_width(remaining, font) <= max_width:
            lines.append(remaining)
            break
        split_at = 1
        for index in range(1, len(remaining) + 1):
            if _text_width(remaining[:index], font) > max_width:
                break
            split_at = index
        space_at = remaining.rfind(" ", 0, split_at)
        if space_at > 0:
            split_at = space_at
        lines.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return lines


def _text_width(text: str, font: ImageFont.ImageFont) -> float:
    getlength = getattr(font, "getlength", None)
    if callable(getlength):
        return float(getlength(text))
    left, _top, right, _bottom = font.getbbox(text)
    return float(right - left)
