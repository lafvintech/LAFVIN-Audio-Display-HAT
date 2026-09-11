# Changelog

All notable public-release changes are recorded here. App manifest versions
remain independent from the Runtime package version.

## Unreleased

## 0.3.0b4 - 2026-09-10

Fourth public beta focused on application experience, simulator fidelity,
device-aware AI capabilities, and more reliable streaming speech.

### Added

- A new RGB LED App provides a continuous rainbow gradient, selectable palette
  colors, and one-button navigation. Its initial App version is `0.1.0`.
- AI Chatbot adds native LLM Tool Calling for four allowlisted device actions:
  reading selected system status, reading or setting speaker volume, and
  setting the RGB light. OpenAI-compatible and Anthropic message formats are
  supported without an MCP service.
- AI Chatbot now uses six selected Twemoji PNGs for Ready, Listening,
  Thinking, Speaking, request error, and configuration error states without
  loading a complete emoji library.
- Dino Runner replaces the former rectangular One Button Jump presentation
  with original pixel dinosaur, cactus, cloud, ground, running-animation,
  score, high-score, Ready, and Game Over visuals.
- System Status now opens a two-page monitor with CPU, memory, temperature,
  storage, Runtime, model, IP, installed-App, and hostname information.
- Video Player now discovers multiple supported files from `assets/videos/`
  and provides a filename-based selection screen.
- The Web Simulator now provides explicit single-click, double-click, and
  triple-click shortcuts alongside its raw press-and-hold button.

### Changed

- AI Chatbot device writes remain Runtime-owned; RGB control now carries the
  App session and requires the foreground `led` permission. Device tools can be
  disabled with `LAFVIN_CHATBOT_TOOLS_ENABLED=0`, and the App reports version
  `0.3.1`, upgraded from `0.2.0`.
- AI Chatbot keeps streaming its first complete sentence quickly, combines
  later short sentences into bounded medium TTS chunks, and starts Runtime
  playback without waiting for long-text display layout.
- AI Chatbot removes its fixed title and divider, places status text at the
  upper left and a consistent state image at the top center, caches its image
  assets.
- The stable `dev.lafvin.jump` App is now named Dino Runner, uses a reusable
  Toolkit Canvas while retaining immediate raw-press jumping, retries on a
  Game Over single-click, uses a taller and longer jump arc, and reports App
  version `0.3.1`, upgraded from One Button Jump `0.2.0`.
- Toolkit Canvas presentation can forward an input timestamp so animated Apps
  retain Runtime frame-latency metrics without bypassing Toolkit presentation.
- System Status opens on System Monitor, switches pages on single-click, uses
  a purple storage accent and black Device Info labels, and returns Home on
  triple-click. Its App version is `0.2.1`, upgraded from `0.1.0`.
- Video Player selects the next file on single-click and starts it on
  double-click. During playback, single-click returns to selection,
  double-click is ignored, triple-click returns Home, and natural completion
  loops the selected video. Its App version is `0.2.2`, upgraded from `0.1.0`.
- The Web Simulator now renders Runtime pages and every App through one native
  240x280 RGB565 Canvas, checks animated frames at up to 30 FPS, and uses a
  smooth device-pixel-ratio-aware HiDPI backing store.

### Fixed

- Streaming speech no longer treats a transport chunk ending in an ASCII
  period as a complete sentence before numeric look-ahead arrives. IPv4
  addresses, decimals, and versions remain intact and receive explicit
  speech-only `dot` / `point` pronunciation.
- Video Player resolves the shared `assets/videos/` directory from development
  checkouts, configured project roots, and conventional deployment locations.
- The simulator Canvas content area now matches the hardware's full 240x280
  display instead of using an inset size.

## 0.3.0b3 - 2026-08-26

Third public beta with expanded Raspberry Pi compatibility and deployment
refinements.

### Added

- Raspberry Pi 4 Model B support, verified on the 64-bit Raspberry Pi OS
  260618 / 2026-06-18 Trixie image.
- Raspberry Pi 3 Model B+ support, including platform detection, GPIO mapping,
  hardware checks, installer coverage, and physical-device acceptance.
- Optional first-deployment import of a checkout `.env` into the persistent
  Runtime configuration.

### Changed

- WM8960 hardware installation and verification now use profile v4 across all
  supported Raspberry Pi models.
- Supported-board documentation and hardware test coverage now include Pi 3
  Model B+ and Pi 4 Model B.
- ASR, LLM, and TTS models, voices, languages, and latency modes now use
  Provider-specific environment variables, allowing every Provider's settings
  to coexist without overriding the selected service.
- Voice Translator manifest version is now `0.1.1`.
### Removed

- The shared `LAFVIN_AI_PROVIDER` and Provider-owned `LAFVIN_ASR_*`,
  `LAFVIN_LLM_*`, and `LAFVIN_TTS_*` configuration paths for models, voices,
  language, custom endpoint credentials, and Claude token limits. Version
  `0.3.0b3` requires the three capability selectors and Provider-specific
  settings documented in `.env.example`; capability timeout and retry settings
  retain their existing names.

### Fixed

- PCM WAV normalization now reads physical audio in bounded chunks instead of
  trusting oversized streaming-container lengths, preventing Fish Audio TTS
  responses from triggering excessive memory allocation.
- Korean message and scrolling-answer bodies now use the bundled Korean font
  consistently for wrapping, rendering, and speech-following scroll layout.
- Voice Translator treats questions, commands, and requested response
  languages as source text to translate instead of instructions to execute.

## 0.3.0b2 - 2026-08-21

Second public beta with expanded cloud AI services and refined bundled Apps.

### Added

- Independent ASR, LLM, and TTS Provider selection, including the first
  built-in multi-provider cloud integrations and a custom OpenAI-compatible
  LLM endpoint.
- Optional diagnostic logging for complete LLM responses and the text sent to
  TTS, without logging API keys.
- Speech-duration metadata used by the Chatbot to coordinate answer scrolling
  with audio playback.

### Changed

- Chatbot now shows the current question and answer on separate pages, streams
  the answer ahead of playback, and scrolls it in step with synthesized speech.
- Cloud ASR input is normalized to PCM S16_LE, 16000 Hz, mono WAV; cloud TTS
  output is normalized to PCM S16_LE, 24000 Hz, mono WAV.
- ASR, LLM, and TTS reuse capability-specific HTTP clients across a Provider
  lifetime and close them cleanly when the App exits.
- One Button Jump uses randomized obstacle spacing, progressive speed changes,
  and corrected score and continue-label placement.
- AI configuration examples now expose only adapted speech Providers while
  retaining a generic OpenAI-compatible endpoint for LLMs.

### Fixed

- Chatbot cancellation no longer leaves stale playback or synthesis work after
  a new recording starts.
- Runtime IPC handles clients disconnecting during a response without emitting
  an unhandled `ConnectionResetError`.
- Fish Audio WAV responses with padded container data no longer fail audio
  normalization as incomplete PCM frames.

## 0.3.0b1 - 2026-07-24

First public beta preparation for LAFVIN Audio Display HAT.

### Added

- Native hardware composition for LCD, button, backlight, RGB LED, battery,
  and network access.
- A versioned WM8960 profile with source, GPL-3.0 license record, conservative
  install/check/remove tooling, and calibrated capture defaults.
- Checkout-backed deployment, the canonical `lafvin-hat` command, first-party
  application cataloguing, application logs, and hardware diagnostics.
- Shared Raw Frame Toolkit, font policy, volume preview tone, and current
  system, AI, game, and video applications.

### Changed

- Runtime logical volume now maps to the calibrated WM8960 speaker curve.
- Runtime startup now refreshes bundled Apps for both development and
  deployment data directories.
- WM8960 profile v2 waits for mixer readiness, tolerates partial full-state
  restore failures, and verifies calibrated capture controls from readback.
- WM8960 profile v2 now packages only the active configuration resources and
  relies on the Raspberry Pi OS WM8960 modules instead of an unused DKMS stub.
- Project-owned test audio and video assets are explicitly recorded with
  checksums and Apache-2.0 redistribution terms.

### Removed

- Obsolete compatibility hardware paths, backend aliases, and legacy
  external-driver environment variables.
- Unused CLI, System Status, and audio diagnostic helpers, plus the empty image
  directory placeholder and obsolete installer demo-package prompt.

### Compatibility

- Physical Runtime uses `--backend lafvin-hat`.
- Development-only external board overrides must export `LafvinHatBoard` and
  use `--lafvin-hat-driver` or `LAFVIN_HAT_DRIVER`.
