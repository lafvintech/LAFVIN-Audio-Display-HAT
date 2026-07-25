# UI Toolkit Guide

The app-facing Toolkit lives in `src/lafvin_hat/ui/toolkit.py` and is imported
through `lafvin_hat.ui`. It renders directly to RGB565 Raw Frame output; the
same frame is presented by the hardware backend and the simulator.

## Design Principles

- Applications own state, interaction, and business logic.
- The Toolkit owns common drawing, text measurement, wrapping, layout helpers,
  frame encoding, and the default visual language.
- Runtime owns display access, Raw Frame ownership, and presentation. Runtime
  does not need to understand Toolkit components.
- Add a Toolkit primitive only after a real application needs a reusable
  version of it. Do not add page-specific one-off helpers.
- Prefer a normal Toolkit page for information and controls. Use custom Raw
  Frame drawing for animation-heavy or media-heavy work.

The public first-pass surface is intentionally small:

- `Theme`
- `Canvas`
- `StatusRow`
- `ChatMessage`
- `image_to_rgb565_be()` for custom image-to-frame workflows

## Default Theme

Use the default `Theme` unless an application has a clear product reason to
do otherwise. It defines the visual baseline for Toolkit applications.

| Element | Default treatment |
|---|---|
| Background | near white `(245, 245, 245)` |
| Primary text | black |
| Secondary text | dark gray |
| Divider | near black, 1 px |
| Normal action | gray fill with black text |
| Selected action | blue fill `(92, 150, 255)` with white text |
| User chat message | blue fill with white text |
| Assistant chat message | white fill with green outline |
| Error state | dark red text |

Do not hard-code a second palette inside a normal app. Extend `Theme` or add a
carefully named Toolkit primitive when the need is shared by more than one app.

## Layout Baseline

The first target is a 240x280 display. `Canvas` adapts to the frame dimensions
it is given, but normal Toolkit pages should follow this baseline:

| Area | Default position |
|---|---|
| Title | `x=22`, `y=10`, bold 22 px |
| Divider | `y=42`, 8 px side margins |
| Status text | `x=22`, `y=48`, 14 px |
| Main content | starts around `y=58` |
| Standard body text | 19 px with 24 px line height |
| Bottom action bar | around `y=236`, 28 px button height |

Use `Canvas.title()` and `Canvas.divider()` rather than reproducing those
coordinates in each application. Use `text_page()`, `chat_page()`, and
`system_status_page()` when their layout fits. Compose lower-level primitives
only when a page needs a genuinely different structure.

## Component Use

```python
canvas = Canvas(width=frame.width, height=frame.height)
canvas.text_page(
    "Settings",
    "Choose an action with one click, then confirm with two clicks.",
    status="ready",
    actions=["Apply", "Back"],
    selected=selected_action,
)
await canvas.present(frame)
```

Use `chat_page()` with `ChatMessage` values for voice conversation or streamed
text. It keeps the most recent text visible when content exceeds the screen.
Pi Zero 2 W can still show visible redraw stutter during very frequent
streaming updates; treat that as a performance issue, not a reason to create a
second UI path.

Use `button_row()` or `action_bar()` for selectable actions. The Toolkit only
draws which index is selected; it does not decide what a click or hold means.

## Typography and Text

The default UI typeface is the checkout-bundled
`assets/font/HarmonyOS Sans/HarmonyOS_Sans_SC.ttf`. It is a CJK-capable
variable font: normal body text uses its `Regular` weight, compact Toolkit
status text and chat-role labels use `Medium`, while titles and large values
use `Bold`. Selected controls remain a Theme color treatment.
Runtime-owned Home and compatibility views, Toolkit Apps, and Video Player
status/error pages use the same loader. Home App-list labels use `Medium` so
they remain readable without making all body text heavier.

Chatbot and Translator have one deliberately narrow exception: an assistant
reply containing Hangul uses the bundled `Noto Sans KR` font for its entire
message body. This avoids per-character font switching and leaves titles,
controls, status text, role labels, and non-Korean replies on HarmonyOS Sans.
It is not a general multi-script fallback system.

Toolkit state labels retain lowercase values in App logic, but display with an
uppercase initial, such as `Idle`, `Listening`, and `Answering...`.

Resolution order is:

1. an explicit constructor path or `LAFVIN_UI_FONT` / `LAFVIN_UI_FONT_BOLD`
   override;
2. the bundled HarmonyOS Sans SC font resolved from `LAFVIN_PROJECT_ROOT`,
   the editable source tree, or the current checkout;
3. system Noto CJK; then
4. DejaVu and Pillow's final default.

The default needs no system font package. Relative override paths resolve from
the checkout root, which keeps the same configuration valid for a manual
Runtime and checkout-backed `systemd` deployment. Existing environments that
explicitly point `LAFVIN_UI_FONT` at Noto continue to use that override until
the line is removed or changed.

Use `Canvas.text()` or `Canvas.text_box()` for wrapping. Use
`scroll_to_bottom=True` for a text area that must show the newest content.
Keep user-facing status messages short: 240x280 is a compact screen, and a
clear two-line state beats a paragraph of diagnostics.

## When to Use Custom Drawing

Use custom Raw Frame drawing when the Toolkit would hide useful control over
timing or pixels:

- game loops and frame pacing
- video decode and presentation
- image effects or full-screen animation
- specialized visualizations that are not shared by normal pages

Even a custom-drawn application should preserve the system conventions: use
the Runtime-owned frame session, handle `app.exit_requested`, release resources
through `app.close()`, and avoid direct access to hardware drivers.

## Evolving the Toolkit

Before adding a component, answer these questions:

1. Does a bundled application already need it?
2. Is it reusable by another likely application?
3. Does it belong in application state or logic instead?
4. Can it reuse the existing theme, text, button, or page primitives?

If the first two answers are not both yes, keep the code local to the app for
now. This keeps `toolkit.py` small, coherent, and easy to evolve.
