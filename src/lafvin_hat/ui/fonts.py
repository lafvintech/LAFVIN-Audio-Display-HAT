"""Shared font resolution for LAFVIN HAT UI renderers.

The platform is checkout-deployed, so the default CJK font lives beside the
source tree instead of being an unrelated operating-system package. Explicit
per-renderer and environment overrides remain available for development or a
future board-specific font policy.
"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from PIL import ImageFont


BUNDLED_HARMONYOS_SANS_SC = (
    Path("assets")
    / "font"
    / "HarmonyOS Sans"
    / "HarmonyOS_Sans_SC.ttf"
)

BUNDLED_NOTO_SANS_KR = (
    Path("assets")
    / "font"
    / "Noto_Sans_KR"
    / "NotoSansKR-VariableFont_wght.ttf"
)


def load_ui_font(
    size: int,
    *,
    bold: bool = False,
    weight: str | None = None,
    font_path: str | Path | None = None,
    bold_font_path: str | Path | None = None,
) -> ImageFont.ImageFont:
    """Load one UI font using the shared default and fallback order."""

    for candidate in font_candidates(
        bold=bold,
        font_path=font_path,
        bold_font_path=bold_font_path,
    ):
        try:
            font = ImageFont.truetype(str(candidate), size)
        except (OSError, ValueError):
            continue
        return _select_weight(font, bold=bold, weight=weight)
    return ImageFont.load_default()


def font_candidates(
    *,
    bold: bool = False,
    font_path: str | Path | None = None,
    bold_font_path: str | Path | None = None,
) -> list[str | Path]:
    """Return UI-font candidates in the order in which they are attempted."""

    configured = _configured_font_path(
        bold=bold,
        font_path=font_path,
        bold_font_path=bold_font_path,
    )
    candidates: list[str | Path] = []
    if configured:
        candidates.extend(_relative_path_candidates(configured))
    candidates.extend(bundled_font_paths())
    candidates.extend(_system_fallback_candidates(bold=bold))
    return _deduplicate(candidates)


def bundled_font_paths() -> list[Path]:
    """Return possible checkout locations for the bundled default font."""

    return [root / BUNDLED_HARMONYOS_SANS_SC for root in _project_roots()]


def load_korean_ui_font(
    size: int,
    *,
    weight: str | None = None,
) -> ImageFont.ImageFont | None:
    """Load bundled Noto Sans KR for a Korean message body when available."""

    for candidate in bundled_korean_font_paths():
        try:
            return _load_cached_korean_font(str(candidate), size, weight)
        except (OSError, ValueError):
            continue
    return None


def bundled_korean_font_paths() -> list[Path]:
    """Return possible checkout locations for the Korean message font."""

    return [root / BUNDLED_NOTO_SANS_KR for root in _project_roots()]


def _configured_font_path(
    *,
    bold: bool,
    font_path: str | Path | None,
    bold_font_path: str | Path | None,
) -> str | Path | None:
    regular = font_path or os.getenv("LAFVIN_UI_FONT")
    if not bold:
        return regular
    return bold_font_path or os.getenv("LAFVIN_UI_FONT_BOLD") or regular


def _project_roots() -> list[Path]:
    roots: list[Path] = []
    configured_root = os.getenv("LAFVIN_PROJECT_ROOT")
    if configured_root:
        roots.append(Path(configured_root).expanduser())
    roots.append(Path(__file__).resolve().parents[3])
    roots.append(Path.cwd())

    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def _relative_path_candidates(value: str | Path) -> list[Path]:
    path = Path(value).expanduser()
    if path.is_absolute():
        return [path]
    return [*(root / path for root in _project_roots()), path]


def _system_fallback_candidates(*, bold: bool) -> list[str | Path]:
    noto_name = "NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc"
    noto_sc_name = "NotoSansSC-Bold.ttf" if bold else "NotoSansSC-Regular.ttf"
    dejavu_name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return [
        Path("/usr/share/fonts/opentype/noto") / noto_name,
        Path("/usr/share/fonts/opentype/noto") / noto_sc_name,
        Path("/usr/share/fonts/truetype/noto") / noto_name,
        Path("/usr/share/fonts/truetype/noto") / noto_sc_name,
        Path("/usr/share/fonts/truetype/dejavu") / dejavu_name,
        "arialbd.ttf" if bold else "arial.ttf",
    ]


def _deduplicate(candidates: list[str | Path]) -> list[str | Path]:
    unique: list[str | Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


@lru_cache(maxsize=32)
def _load_cached_korean_font(
    candidate: str,
    size: int,
    weight: str | None,
) -> ImageFont.ImageFont:
    """Cache the optional Korean font across streaming Canvas instances."""

    font = ImageFont.truetype(candidate, size)
    return _select_weight(font, bold=False, weight=weight)


def _select_weight(
    font: ImageFont.ImageFont,
    *,
    bold: bool,
    weight: str | None,
) -> ImageFont.ImageFont:
    """Select a named variable-font weight when the font exposes one."""

    get_names = getattr(font, "get_variation_names", None)
    set_name = getattr(font, "set_variation_by_name", None)
    if not callable(get_names) or not callable(set_name):
        return font
    try:
        available = {
            name.decode("ascii") if isinstance(name, bytes) else str(name)
            for name in get_names()
        }
    except OSError:
        return font

    preferred = (
        (weight,)
        if weight
        else (("Bold", "SemiBold") if bold else ("Regular",))
    )
    for name in preferred:
        if name not in available:
            continue
        try:
            set_name(name)
        except (OSError, ValueError):
            continue
        break
    return font
