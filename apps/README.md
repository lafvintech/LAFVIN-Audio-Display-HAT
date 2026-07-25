# First-party Applications

The first-party application set contains:

- `chatbot/`: Raw Frame toolkit voice chatbot with streaming LLM text and TTS
- `translator/`: Raw Frame toolkit voice translator using the shared AI stack
- `system_status/`: Raw Frame toolkit Runtime and device status page
- `system_volume/`: Raw Frame toolkit Runtime volume control page
- `one_button_jump/`: custom Raw Frame game loop and low-latency button input
- `video_player/`: custom Raw Frame MP4/local video playback trial

V3 records the authoritative first-party identity, provisioning type, intended
Home order, and implementation type in [`catalog.yaml`](catalog.yaml). Validate
it without installing or launching applications:

```bash
python -m lafvin_hat.runtime.apps.catalog
```

V3-M5 makes the catalog the source of truth for first-party provisioning and
Home order. Third-party installed Apps remain outside this catalog.

All foreground applications under `apps/` now use `display.raw_frame` in their
manifests. Normal pages and voice apps use the app-facing toolkit in
`lafvin_hat.ui`; animation-heavy or media-heavy apps may draw Raw Frame content
directly.

See [`../docs/APP_DEVELOPMENT.md`](../docs/APP_DEVELOPMENT.md) for the supported
new-app workflow and [`../docs/UI_GUIDE.md`](../docs/UI_GUIDE.md) for Toolkit
components, layout, and theme rules.

Use `app-run` for the normal development loop:

```bash
lafvin-hat app run apps/chatbot
lafvin-hat app run apps/translator
lafvin-hat app run apps/system_status
lafvin-hat app run apps/system_volume
```

Use `--follow` when app logs matter during development:

```bash
lafvin-hat app run apps/chatbot --follow
lafvin-hat logs dev.lafvin.chatbot --follow
```

Persistent installs still use the explicit workflow:

```bash
lafvin-hat app install apps/chatbot
lafvin-hat app start dev.lafvin.chatbot
```

Milestone notes:

- M3 added the One Button Jump Raw Frame game.
- M5 added Chatbot and Translator on the shared Runtime audio and AI services.
- V2-M5 added Video Player as a standalone media app, not a Runtime-owned media service.
- V2-M5.1 and M5.2 moved System Status and Volume into bundled apps.
- V2-M5.3 kept Hardware Test Runtime-hosted for fast startup while exposing it
  as the Home system app `dev.lafvin.hardware-test`.
- V2-M6 moved System Status, Volume, Translator, and Chatbot onto the app-facing
  Raw Frame toolkit.
