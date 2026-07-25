# LAFVIN HAT WM8960 Profile v1

This directory owns the versioned WM8960 hardware profile used by LAFVIN HAT.
`lafvin-hat-wm8960-v1/` is the editable profile source. The install artifact
is `lafvin-hat-wm8960-v1.zip`.
Its packaged driver license is GPL-3.0. The unmodified license text is
distributed beside this profile as [`COPYING`](COPYING). Do not distribute the
ZIP by itself; distribute it with this source directory, `PROFILE.md`, and
`COPYING` so recipients have the corresponding source and license record.

## Fixed Mixer State

The archive includes the final `wm8960_asound.state` restored at boot by the
existing `wm8960-soundcard.service`. The M6.2 capture calibration is therefore
part of the static profile, not a second systemd service.

| Control | Value |
|---|---:|
| `Capture Volume` | `45/63` on both channels |
| Left/Right `INPUT1` boost | `2/3` |
| `ADC PCM Capture Volume` | `195/255` on both channels |
| `ALC Function` | `Off` |
| `Noise Gate Switch` | `off` |

The installer verifies the archive checksum before it installs the profile.
`sudo bash install_driver.sh --check` reads the physical ALSA controls after
boot. `sudo bash uninstall_driver.sh` restores recorded backups when available.

## Profile Maintenance

Treat this directory as the source of truth for the installed WM8960 profile.
Update the unpacked source first, rebuild the ZIP with POSIX `/` entry paths,
then update its checksum in the installer and tests. Any mixer, service, or
kernel-resource change must create a new profile version instead of replacing
this archive in place. The source and license record for the packaged driver
are maintained in the project notices.
