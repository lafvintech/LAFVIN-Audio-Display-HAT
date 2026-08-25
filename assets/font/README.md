# LAFVIN HAT Font Assets

This directory contains checkout-owned UI font assets. They are not operating
system packages and are not installed by the WM8960 driver scripts.

## Current Policy

| Asset | Runtime use | Keep |
| --- | --- | --- |
| `HarmonyOS Sans/HarmonyOS_Sans_SC.ttf` | Default UI font for Home, Runtime views, Toolkit Apps, and ordinary message bodies | Font file and `LICENSE-update.txt` |
| `Noto_Sans_KR/NotoSansKR-VariableFont_wght.ttf` | Entire Chatbot or Translator message/answer body when it contains Hangul | Font file and `OFL.txt` |

HarmonyOS Sans SC supplies the normal `Regular`, `Medium`, and `Bold` weights
through its variable-font interface. Noto Sans KR is a deliberately narrow
Korean-message exception: it does not replace the default UI typeface or act
as a general per-character fallback system.

No other HarmonyOS family variants are shipped. Condensed, italic, Traditional
Chinese, and Arabic files are excluded because the current loader never
selects them; a future language addition must follow the process below.

The Toolkit selects one font for a Korean message or scrolling answer, then
measures, wraps, calculates scrolling, and draws the whole body with that same
font. This avoids visible font switching in mixed Korean and Latin output.

## Distribution Rules

- Keep the license beside every bundled font.
- Keep only the variable Noto Sans KR font. The `static/` weight copies are
  not used by LAFVIN HAT.
- Do not add experimental or unused font families to release checkouts.
- Record each third-party font in
  [`docs/THIRD_PARTY_NOTICES.md`](../../docs/THIRD_PARTY_NOTICES.md).

## Adding Another Language

Add a font only after a product language is explicitly supported. The change
must include: character-coverage verification, a real-device visual test,
correct line measurement and wrapping, the retained license, and an update to
the UI guide. Avoid calling a font "global" merely because it covers Latin
text.
