# LAFVIN HAT WM8960 Profile v2

## Purpose

This profile packages the WM8960 board support used by LAFVIN HAT. It keeps
the calibrated playback and capture defaults from profile v1 and adds
boot-time mixer restoration with physical readback for Raspberry Pi 5 and
Raspberry Pi Zero 2 W.

## Contents

- Source directory: `lafvin-hat-wm8960-v2/`
- Installation archive: `lafvin-hat-wm8960-v2.zip`
- License: GPL-3.0; see `COPYING`
- Mixer state: `lafvin-hat-wm8960-v2/wm8960_asound.state`
- WirePlumber rule: `lafvin-hat-wm8960-v2/51-lafvin-hat-wm8960.conf`
- Kernel support: Raspberry Pi OS WM8960 modules and overlay; no DKMS payload

The profile is derived from the Waveshare WM8960 Audio HAT package. LAFVIN HAT
maintains its own installation, verification, calibration, and removal flow.
See `docs/THIRD_PARTY_NOTICES.md` for provenance and support boundaries.

## Changes From v1

- Wait for the WM8960 ALSA mixer controls before restoring the profile.
- Restore the fixed profile state explicitly, then verify all four calibrated
  capture controls from physical ALSA readback.
- Treat a non-zero full-state restore as diagnostic information rather than
  final failure; explicitly apply the calibrated controls when readback still
  differs.
- Require a second stable readback after a short delay before service success.
- Keep ALSA's mutable system state separate from the fixed profile state.
- Start the profile service after the sound target and before the LAFVIN HAT
  Runtime service.
- Append helper logs so a manual restart no longer overwrites the boot record.
- Match WirePlumber's `api.alsa.card.id=wm8960soundcard` property and enable
  its software mixer. ALSA exposes `wm8960-soundcard` (with hyphens) as the
  separate card name, so the ID and name must not be interchanged. This keeps
  the desktop audio session from replacing the calibrated hardware
  `Capture Volume` with its 100% input default after boot.

The WirePlumber rule only changes volume ownership for this ALSA card. Other
sound cards remain untouched, while LAFVIN HAT continues to use direct ALSA
capture and playback. Reboot after installation so the user audio session
loads the rule.

The calibrated values remain:

- `Capture Volume`: `45,45`
- `Left Input Boost Mixer LINPUT1 Volume`: `2`
- `Right Input Boost Mixer RINPUT1 Volume`: `2`
- `ADC PCM Capture Volume`: `195,195`

## Versioning Rule

Any later change to mixer defaults, boot restoration behavior, service
ordering, or kernel-facing files must create another profile version. Existing
profile directories and records remain available as historical baselines.
