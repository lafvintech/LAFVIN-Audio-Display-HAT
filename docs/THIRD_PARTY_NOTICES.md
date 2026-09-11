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

## Twemoji Graphics

AI Chatbot uses six selected Twemoji PNG graphics. Three additional candidate
graphics remain in the same asset directory but are not loaded by the App. The
images are identified by their Unicode code-point filenames; the project does
not bundle or load the complete Twemoji image set or JavaScript library.

Upstream project: <https://github.com/jdecked/twemoji>

Graphics copyright: Copyright 2019 Twitter, Inc and other contributors.

Graphics license: Creative Commons Attribution 4.0 International (CC BY 4.0),
<https://creativecommons.org/licenses/by/4.0/>

The exact upstream revision of the user-supplied PNG files has not been
independently pinned. The checksums below identify the files shipped by this
project and do not change the upstream license.

| File | Role | SHA-256 |
|---|---|---|
| `assets/emoji/1f600.png` | Speaking state (grinning face) | `9CFC5AD34E89B6EEBDDCD5EC715C224A86C99EA5B9FAD999407DEE7E32F681B6` |
| `assets/emoji/1f602.png` | Reserved candidate (face with tears of joy) | `C252A58367211C11D839155E50DC5E98551826C64B8D2E8D6267124C054CEAE0` |
| `assets/emoji/1f634.png` | Reserved candidate (sleeping face) | `2AEEA8BADCCCEED72027D37081AC75D81CED2932C382ED89527D427585081DF7` |
| `assets/emoji/1f642.png` | Ready state (slightly smiling face) | `C7A2C052F383509AC9EC9DA7F34CCCC4C1D35040799426588C54A0D83CD9628F` |
| `assets/emoji/1f914.png` | Thinking state (thinking face) | `5116F7D07677F06785887C0AF23C189B541A306D6B792D605FFAF3ED9F0E912D` |
| `assets/emoji/1f917.png` | Listening state (hugging face) | `75051001FAED2BDDDDB6C9E67EE6B62F4F6E72395D2EFFCAA017BD4E6970B29F` |
| `assets/emoji/203c.png` | Reserved candidate (double exclamation mark) | `44ED845D25BD815242A41567ED15F043F9155C93C0C1066BDE788CFE6F70D93B` |
| `assets/emoji/2639.png` | Request error state (frowning face) | `9C06D755CFEA63FE7DBBD4E0F3B666FEDEC89B474CFC6AB0B22289D6BCDE9680` |
| `assets/emoji/26a0.png` | Configuration error state (warning sign) | `7A03A74A92CB2F04B7F3E0338F51A3C4DFC1491A8F046B722F8A951502A7740E` |

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

## Bundled Video Demonstration Media

The following files are present in the development checkout for Video Player
testing. Their source, license, and redistribution terms have not yet been
documented. They must not be included in a public release until that review is
complete. The checksums below identify the exact files under review; they do
not grant or imply redistribution rights.

| File | Role | SHA-256 |
|---|---|---|
| `assets/videos/1.mp4` | Video Player demonstration sample | `C17876FFFC670D5ED27DD5E2B19907D6072A603F6CBCDFBC5D2D15CF243B1F17` |
| `assets/videos/2.mp4` | Video Player demonstration sample | `2201DA191583602A35A9D26FA3A6F49BDA8E6CE1E42D1FCCA670FD5B31DE459E` |
| `assets/videos/3.mp4` | Video Player demonstration sample | `3DEB1B9B2F0EFD683CC875A052222E744AE41D0C11A4A5FFED9F183C67796E0B` |
