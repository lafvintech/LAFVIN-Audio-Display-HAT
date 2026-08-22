# Changelog

All notable public-release changes are recorded here. App manifest versions
remain independent from the Runtime package version.

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
