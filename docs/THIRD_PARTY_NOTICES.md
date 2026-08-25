# Third-Party Notices

This file records materials that are shipped in the checkout under licenses
other than, or in addition to, the root project license. Except where a
component-specific notice states otherwise, the root [`LICENSE`](../LICENSE)
applies to source code and project-created test media. Each component below
retains its own applicable terms and attribution.

## Noto Sans KR Message Font

The optional Korean message-body font is the unmodified bundled file:

- `assets/font/Noto_Sans_KR/NotoSansKR-VariableFont_wght.ttf`

It is used only for a Chatbot or Translator message or scrolling answer body
that contains Hangul. The retained
[`OFL.txt`](../assets/font/Noto_Sans_KR/OFL.txt) applies to the bundled font.
LAFVIN Audio Display HAT does not modify or redistribute it as a standalone
font package.

## LAFVIN Audio Display HAT WM8960 Profile v4 Resources

The following bundled resource is sourced from the Waveshare WM8960 Audio HAT
project:

- `hardware/lafvin_hat/wm8960/v4/lafvin-hat-wm8960-v4.zip`

Upstream project: <https://github.com/waveshareteam/WM8960-Audio-HAT>

Upstream license: GPL-3.0

LAFVIN profile: `lafvin-hat-wm8960` v4

The package is a LAFVIN-maintained derivative. The source attribution and
GPL-3.0 license remain applicable. The unmodified GPL-3.0 text is retained as
[`hardware/lafvin_hat/wm8960/v4/COPYING`](../hardware/lafvin_hat/wm8960/v4/COPYING).
The fixed bundled snapshot has SHA-256:

```text
107AA596234EDE0B2FB077657BCED2043B083051B841093D9B86A469EF771D40
```

LAFVIN's `deploy/hardware` scripts are separate local integration work. They
verify the snapshot, record ownership state, install/check/remove profile
resources conservatively, and account for the required reboot. See
[`hardware/lafvin_hat/wm8960/v4/PROFILE.md`](../hardware/lafvin_hat/wm8960/v4/PROFILE.md)
for the profile record.

The archived v1, v2, and v3 profiles remain under
`hardware/lafvin_hat/wm8960/` as historical source baselines and are not
installed by the current scripts. Each retains its own GPL-3.0 `COPYING`.

## HarmonyOS Sans SC UI Font

The default UI font is the unmodified bundled file:

- `assets/font/HarmonyOS Sans/HarmonyOS_Sans_SC.ttf`

Source: Huawei Device Co., Ltd., HarmonyOS Sans font family.

The applicable license is retained beside the font as
[`assets/font/HarmonyOS Sans/LICENSE-update.txt`](../assets/font/HarmonyOS%20Sans/LICENSE-update.txt).
It permits distribution of unmodified copies bundled with software, subject to
the license conditions and retained notices. LAFVIN Audio Display HAT does not
modify or redistribute the font as a standalone font package.

## Project-Created Test Media

The following active checkout assets were created for and are owned by the
LAFVIN Audio Display HAT project. They are licensed under the root Apache
License 2.0 and may be redistributed with the project:

| File | Role | SHA-256 |
|---|---|---|
| `assets/audio/audio_test.wav` | Runtime Hardware Test speaker sample | `786D39BAA3ABF2AEB0844DDABEB633A2308DB2E3D8FC4E92704057DDAE3E97E0` |
| `assets/videos/test.mp4` | Video Player demonstration sample | `04A1A88639F8706A6EEDF0EC61E35DCC7EF9CD3E624F611494AB1C7F0CA6F9F6` |
