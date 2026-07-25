# Application Development Guide

This guide is the supported development path for a LAFVIN HAT foreground
application. It assumes that the Runtime is already running and owns the
device hardware.

## Choose an Application Type

Use one of these two paths before creating an application:

| Application type | Use it for | Rendering approach |
|---|---|---|
| Toolkit app | status pages, controls, forms, text, chat, and translation | `lafvin_hat.ui.Canvas` |
| Custom Raw Frame app | games, video, animation, and other frame-sensitive work | write RGB565 frame bytes directly |

All first-party foreground applications use the `display.raw_frame`
permission. A toolkit app is still a Raw Frame app: the toolkit draws an
RGB565 frame, and Runtime presents that finished frame. It does not introduce
another Runtime UI mode.

Use the Toolkit by default. Use custom drawing only when its lower-level
control is genuinely useful; `one_button_jump` and `video_player` are the reference
examples.

## Application Directory

An application directory contains a manifest and an executable entry point:

```text
apps/my_app/
  manifest.yaml
  main.py
  README.md
```

Start from the closest first-party application:

- `apps/system_status` for a periodically refreshed Toolkit page
- `apps/system_volume` for a simple button-controlled Toolkit page
- `apps/translator` for push-to-talk, audio, AI, and Toolkit rendering
- `apps/one_button_jump` for custom Raw Frame animation

Use a unique reverse-domain application ID in `manifest.yaml`. An interactive
Toolkit application normally needs `display.raw_frame` and `button`
permissions:

```yaml
schema_version: 1
id: dev.example.my-app
name: My App
version: 0.1.0
description: Short description of the app

entrypoint:
  executable: python
  args:
    - main.py
  working_directory: .

permissions:
  - display.raw_frame
  - button

ui:
  mode: raw_frame

lifecycle:
  startup_timeout_sec: 10
  exit_timeout_sec: 3
  restart: never
  max_restarts: 0
```

Add only the permissions the application actually uses. A display-only page
can omit `button`; audio applications also need `microphone` and/or `speaker`
as appropriate.

## Recommended Development Loop

Start Runtime in one terminal. Use the LAFVIN HAT backend on hardware; omit the
backend flag for the local simulator:

```bash
lafvin-hat runtime start --env-file .env --backend lafvin-hat
```

Runtime refreshes the six bundled first-party Apps before it starts listening.
On a fresh development data directory they appear on Home automatically;
manual installation remains for third-party or local test Apps.

From another terminal, run an application from its working directory:

```bash
lafvin-hat app run apps/my_app
```

`lafvin-hat app run` development-registers the directory and starts it in one
step. It is the recommended command while editing source code. Add `--follow`
when the application writes useful runtime logs:

```bash
lafvin-hat app run apps/my_app --follow
lafvin-hat logs dev.example.my-app --follow
```

The module forms remain useful only when console scripts are unavailable:

```bash
python -m lafvin_hat.runtime --env-file .env --backend lafvin-hat
python -m lafvin_hat.sdk app-run apps/my_app
```

Use the explicit install/start workflow only when testing persistent packaged
installation behavior:

```bash
lafvin-hat app install apps/my_app
lafvin-hat app start dev.example.my-app
lafvin-hat app stop dev.example.my-app
```

Development registration points at the source directory and is not restored
after a Runtime restart. Persistent installation copies the application into
Runtime-managed storage.

## Minimal Toolkit Application

This is the smallest useful Raw Frame Toolkit pattern. Runtime supplies launch
environment variables, so an application must be started through Runtime,
not by directly invoking `main.py`.

```python
from __future__ import annotations

import asyncio

from lafvin_hat.sdk import DeviceApp
from lafvin_hat.ui import Canvas


async def main() -> None:
    app = await DeviceApp.connect_from_environment()
    await app.acquire_foreground()
    frame = await app.frames.acquire()
    try:
        await (
            Canvas(width=frame.width, height=frame.height)
            .text_page(
                "My App",
                "Hello from LAFVIN HAT.",
                status="ready",
            )
            .present(frame)
        )
        async for event in app.subscribe(events=["app.exit_requested"]):
            if event["event"] == "app.exit_requested":
                break
    finally:
        await app.close()


if __name__ == "__main__":
    asyncio.run(main())
```

`app.close()` releases owned audio, the Raw Frame session, and foreground
ownership. Keep it in a `finally` block. The Runtime handles the global
triple-click return gesture and sends `app.exit_requested` before stopping an
application; do not reimplement the global return gesture in every app.

## Buttons and Actions

Foreground applications receive raw button events immediately:

- `button.raw_pressed`
- `button.raw_released`
- `app.exit_requested`

The usual convention for selection pages is single click to move selection
and double click to confirm. Voice applications reserve a hold on their Talk
or Translate action for recording. The Toolkit paints selection state; the
application owns the selected action and all interaction decisions.

Do not add page-specific gesture recognition to Runtime just to serve one
application. Keep app-local state and timing in the application, as
`system_volume`, `chatbot`, and `translator` do.

## Logs and Debugging

Use standard Python logging or `print()` for application diagnostics. Runtime
captures application output in its per-app log, and the CLI exposes it:

```bash
lafvin-hat logs dev.example.my-app --follow
lafvin-hat app list
lafvin-hat status
```

Use `lafvin-hat status` to verify foreground ownership, Raw Frame activity, frame
metrics, audio ownership, and the active backend. If an application fails
before drawing, inspect its log first; if it draws but the display is blank,
check `frame.active`, `frame.owner_app_id`, and `frame.metrics.commit_count`.

## Ownership Boundaries

Applications may request Runtime capabilities through `DeviceApp`:

- foreground UI and Raw Frame output
- button events
- recording, playback, and volume through `app.audio`
- Runtime status through `app.client.request("runtime.status")`

Applications must not access LAFVIN HAT hardware drivers, GPIO, SPI, ALSA
device files, or the Runtime frame buffer directly. Runtime remains the
hardware owner. This keeps applications portable between the Web simulator, Pi
Zero 2 W, and Pi 5.

## Before Sharing an Application

Check these items before calling an app ready:

- the manifest requests only required permissions
- `app.close()` runs on normal exit and failures
- the page remains readable at 240x280
- text wraps or scrolls when it can exceed the visible area
- the app returns cleanly after Runtime triple-click exit
- `lafvin-hat app run apps/my_app --follow` shows useful failure context
- `pytest` passes for any changed SDK, Toolkit, or app behavior

`lafvin-hat app create` is intentionally deferred. The current application shape
is stable enough to document, but a generator should wait until third-party
app creation has been exercised more broadly.
