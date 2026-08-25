# LAFVIN HAT WM8960 Profile v3

## Purpose

This profile is the Raspberry Pi 4 Model B enablement revision of the LAFVIN
HAT WM8960 board support. It retains the accepted playback and capture
calibration from profile v2, adds an ownership-aware v2 upgrade path, and stops
installing the obsolete `i2s-mmap` Device Tree overlay.

The supported hardware targets are:

- Raspberry Pi Zero 2 W;
- Raspberry Pi 4 Model B; and
- Raspberry Pi 5.

## Contents

- Source directory: `lafvin-hat-wm8960-v3/`
- Installation archive: `lafvin-hat-wm8960-v3.zip`
- License: GPL-3.0; see `COPYING`
- Mixer state: `lafvin-hat-wm8960-v3/wm8960_asound.state`
- WirePlumber rule: `lafvin-hat-wm8960-v3/51-lafvin-hat-wm8960.conf`
- Kernel support: Raspberry Pi OS WM8960 modules and the
  `wm8960-soundcard` overlay; no DKMS payload

The profile is derived from the Waveshare WM8960 Audio HAT package. LAFVIN HAT
maintains its own installation, verification, calibration, upgrade, and
removal flow. See `docs/THIRD_PARTY_NOTICES.md` for provenance and support
boundaries.

## Changes From v2

- Add Raspberry Pi 4 Model B to the physically tested target list.
- Require a supported Raspberry Pi model and the installed
  `wm8960-soundcard.dtbo` before changing system files.
- Stop adding or requiring `dtoverlay=i2s-mmap`; current Raspberry Pi kernels
  no longer provide that overlay, and `wm8960-soundcard` enables its required
  I2S resources.
- During an upgrade, remove or re-comment `dtoverlay=i2s-mmap` only when the
  root-owned v2 state proves that LAFVIN previously added or uncommented it.
  Preserve an unowned pre-existing line and emit a warning.
- Carry the original ownership actions and pre-install backup directory across
  profile upgrades so a later uninstall still restores the pre-LAFVIN state.
- Record the detected Raspberry Pi model and the `i2s-mmap` migration result
  for diagnostics.

All v2 boot restoration, service ordering, WirePlumber isolation, mutable ALSA
state separation, and physical mixer readback behavior remain unchanged.

The calibrated values remain:

- `Capture Volume`: `45,45`
- `Left Input Boost Mixer LINPUT1 Volume`: `2`
- `Right Input Boost Mixer RINPUT1 Volume`: `2`
- `ADC PCM Capture Volume`: `195,195`

## Upgrade and Removal Contract

Do not uninstall v2 before installing v3. The v3 installer reads the existing
root-owned profile state, creates a new timestamped safety backup, and preserves
the original ownership record needed by `uninstall_driver.sh`.

On a fresh system, v3 installs the current profile directly. On an existing v2
system, running `sudo bash install_driver.sh` performs the in-place upgrade.
Both paths require a reboot before final validation.

The uninstaller remains version-tolerant. For v3, it does not recreate the
obsolete `i2s-mmap` entry after an ownership-aware upgrade.

## Versioning Rule

Any later change to mixer defaults, boot restoration behavior, service
ordering, upgrade ownership semantics, or kernel-facing files must create
another profile version. Existing profile directories and records remain
available as historical baselines.
