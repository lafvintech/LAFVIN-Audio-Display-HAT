# LAFVIN HAT WM8960 Profile v4

## Purpose

This profile is the Raspberry Pi 3 Model B+ enablement revision of the LAFVIN
HAT WM8960 board support. It retains the accepted playback and capture
calibration, boot behavior, WirePlumber isolation, and ownership-aware upgrade
semantics from profile v3.

The supported hardware targets are:

- Raspberry Pi Zero 2 W;
- Raspberry Pi 3 Model B+;
- Raspberry Pi 4 Model B; and
- Raspberry Pi 5.

## Contents

- Source directory: `lafvin-hat-wm8960-v4/`
- Installation archive: `lafvin-hat-wm8960-v4.zip`
- License: GPL-3.0; see `COPYING`
- Mixer state: `lafvin-hat-wm8960-v4/wm8960_asound.state`
- WirePlumber rule: `lafvin-hat-wm8960-v4/51-lafvin-hat-wm8960.conf`
- Kernel support: Raspberry Pi OS WM8960 modules and the
  `wm8960-soundcard` overlay; no DKMS payload

The profile is derived from the Waveshare WM8960 Audio HAT package. LAFVIN HAT
maintains its own installation, verification, calibration, upgrade, and
removal flow. See `docs/THIRD_PARTY_NOTICES.md` for provenance and support
boundaries.

## Changes From v3

- Add Raspberry Pi 3 Model B+ to the explicitly accepted hardware list.
- Keep Raspberry Pi 3 Model B, Raspberry Pi 3 Model A+, Compute Module 3, and
  other untested derivatives outside the support boundary.
- Preserve the v3 mixer payload and all installation, boot restoration,
  service ordering, WirePlumber, and ownership behavior unchanged.
- Record profile version 4 and the exact Raspberry Pi model for diagnostics.

The calibrated values remain:

- `Capture Volume`: `45,45`
- `Left Input Boost Mixer LINPUT1 Volume`: `2`
- `Right Input Boost Mixer RINPUT1 Volume`: `2`
- `ADC PCM Capture Volume`: `195,195`

## Upgrade and Removal Contract

Do not uninstall v3 before installing v4. The v4 installer reads the existing
root-owned profile and first-install ownership state, creates a new timestamped
safety backup, and preserves the original backup and ownership actions needed
by `uninstall_driver.sh`.

On a fresh system, v4 installs the current profile directly. On an existing
v1, v2, or v3 system, running `sudo bash install_driver.sh` performs the
in-place upgrade. A reboot is required before final validation.

The uninstaller remains version-tolerant and restores only files and boot
entries proven to be owned by the LAFVIN profile.

## Versioning Rule

Any later change to the supported hardware list, mixer defaults, boot
restoration behavior, service ordering, upgrade ownership semantics, or
kernel-facing files must create another profile version. Existing profile
directories and records remain available as historical baselines.
