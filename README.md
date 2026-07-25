# LAFVIN Audio Display HAT

**English** | [简体中文](README.zh-CN.md)

LAFVIN Audio Display HAT is a portable audio and display platform for
Raspberry Pi applications such as an AI chatbot, translator, hardware
diagnostics, media playback, and single-button games.

This repository contains the device Runtime, application SDK, hardware
support, first-party applications, UI Toolkit, and deployment tools.

## Highlights

- A single Runtime owns the display, button, RGB LED, backlight, audio,
  application lifecycle, and persistent application storage.
- The native Raspberry Pi backend supports the LAFVIN Audio Display HAT and
  includes a versioned WM8960 hardware profile.
- The Raw Frame SDK and UI Toolkit let applications render the same final
  pixels on physical hardware and in the simulator.
- Six bundled foreground applications are provided: System Status, Volume,
  Chatbot, Translator, One Button Jump, and Video Player.
- Hardware Test is hosted by the Runtime for fast startup and direct hardware
  access.
- Checkout-backed deployment provides the canonical `lafvin-hat` command,
  systemd integration, application logs, and straightforward Git updates.

The product name is **LAFVIN Audio Display HAT**. For software compatibility,
the Python package, command-line tool, service, backend, and configuration
paths continue to use the `lafvin-hat` or `lafvin_hat` identifier.

## Release and License

The current public prerelease is `0.3.0b1`.

Except where a component-specific notice states otherwise, source code and
project-created test media are licensed under the
[Apache License 2.0](LICENSE). Read [NOTICE](NOTICE),
[CHANGELOG.md](CHANGELOG.md), and
[Third-Party Notices](docs/THIRD_PARTY_NOTICES.md) before redistributing this
project or a device image.

## Before You Begin

The current hardware flow has been tested on:

- Raspberry Pi Zero 2 W
- Raspberry Pi 5
- Current 64-bit Raspberry Pi OS
- Python 3.11 or newer

Use a stable power supply. Shut down and disconnect power before installing or
removing the HAT.

Chatbot and Translator can use an OpenAI-compatible API. API usage is billed
separately from ChatGPT Plus, Pro, or other application subscriptions. An
offline Fake Provider is available when you only need to validate the local
application flow.

## Recommended Raspberry Pi Installation

The recommended first-install path is:

1. install and verify the hardware profile;
2. validate the project in development mode;
3. register the tested checkout as the persistent systemd Runtime.

### 1. Clone the Repository

Install Git when it is not already available:

```bash
sudo apt update
sudo apt install -y git
```

Clone the project:

```bash
cd ~
git clone https://github.com/lafvintech/LAFVIN-Audio-Display-HAT.git
cd ~/LAFVIN-Audio-Display-HAT
```

### 2. Install the Hardware Profile

```bash
sudo bash install_driver.sh
sudo reboot
```

`install_driver.sh` installs the Raspberry Pi system hardware baseline,
enables SPI, I2C, and I2S, installs the WM8960 profile and calibration, and
adds the required ALSA, FFmpeg, and build dependencies.

### 3. Verify the Hardware After Reboot

Reconnect to the Raspberry Pi:

```bash
cd ~/LAFVIN-Audio-Display-HAT
sudo bash install_driver.sh --check
bash tools/hardware_check.sh
```

Both checks should report:

```text
Result: 0 failure(s)
```

Resolve failures before continuing. Read any power or thermal warning instead
of ignoring it.

### 4. Create the Development Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,hardware,ai]"
pytest
```

The optional dependency groups provide:

| Extra | Purpose |
| --- | --- |
| `dev` | Automated tests with `pytest` |
| `hardware` | `spidev` and `gpiod` |
| `ai` | OpenAI-compatible provider support |

### 5. Configure Development Mode

```bash
cp .env.example .env
nano .env
```

For a real OpenAI-compatible provider:

```ini
LAFVIN_AI_PROVIDER=openai-compatible
OPENAI_API_KEY=replace-with-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
LAFVIN_ASR_MODEL=whisper-1
LAFVIN_LLM_MODEL=gpt-4o-mini
LAFVIN_TTS_MODEL=tts-1
LAFVIN_TTS_VOICE=alloy
```

For an explicit offline test:

```ini
LAFVIN_AI_PROVIDER=fake
```

The local `.env` file is ignored by Git. Do not expose API keys in screenshots,
logs, bug reports, or commits.

### 6. Run the Interactive Hardware Test

The test directly accesses the display, GPIO, and audio devices. Stop a
deployed Runtime before starting it:

```bash
sudo systemctl stop lafvin-hat 2>/dev/null || true
python3 tools/hardware_test.py
```

The test asks you to confirm each observed hardware result.

### 7. Start the Development Runtime

```bash
lafvin-hat runtime start --env-file .env --backend lafvin-hat
```

Every command-line Runtime start atomically refreshes the six bundled
first-party applications into the selected Runtime data directory. Third-party
applications are not changed.

In another terminal:

```bash
cd ~/LAFVIN-Audio-Display-HAT
source .venv/bin/activate
lafvin-hat info
lafvin-hat app list
```

Test the Home screen, button gestures, and applications. Press `Ctrl+C` in the
first terminal to stop the development Runtime cleanly.

Do not run the development Runtime and `lafvin-hat.service` at the same time.
They would compete for the display, GPIO, audio devices, and Runtime socket.

### 8. Deploy the Accepted Checkout

After the development Runtime has stopped:

```bash
cd ~/LAFVIN-Audio-Display-HAT
sudo bash deploy/install_raspberry_pi.sh
```

The deployment installer:

- uses the current Git checkout and its editable `.venv`;
- installs the global `lafvin-hat` management command;
- creates and enables `lafvin-hat.service`;
- stores application data in `/var/lib/lafvin-hat`;
- stores Runtime logs in `/var/log/lafvin-hat`;
- preserves existing configuration, data, third-party applications, and the
  hardware profile.

Deployment deliberately does not copy the checkout `.env`. Configure the
persistent Runtime separately:

```bash
sudo nano /etc/lafvin-hat/runtime.env
```

Then start and inspect the service:

```bash
sudo systemctl start lafvin-hat
sudo systemctl status lafvin-hat --no-pager
sudo journalctl -u lafvin-hat -n 100 --no-pager
```

After deployment, the management command works without activating `.venv`:

```bash
lafvin-hat info
lafvin-hat app list
lafvin-hat logs dev.lafvin.chatbot --follow
```

## Installed Services

A complete installation has two project-related systemd units:

| Unit | Role | Normal state |
| --- | --- | --- |
| `lafvin-hat.service` | Long-running device Runtime | `active (running)` |
| `wm8960-soundcard.service` | One-shot WM8960 setup and calibration | `active (exited)` |

The foreground applications are Runtime-managed child processes, not separate
systemd services.

Inspect the units with:

```bash
systemctl list-unit-files | grep -E 'lafvin-hat|wm8960'
systemctl status lafvin-hat --no-pager
systemctl status wm8960-soundcard --no-pager
```

## Application and Log Commands

```bash
lafvin-hat info
lafvin-hat app list
lafvin-hat app start dev.lafvin.chatbot
lafvin-hat app stop dev.lafvin.chatbot
lafvin-hat logs dev.lafvin.chatbot
lafvin-hat logs dev.lafvin.chatbot --follow
```

During application development, register and launch a working-tree application
with:

```bash
lafvin-hat app run apps/system_status
lafvin-hat app run apps/system_volume
lafvin-hat app run apps/chatbot --follow
lafvin-hat app run apps/translator --follow
lafvin-hat app run apps/one_button_jump
lafvin-hat app run apps/video_player
```

`lafvin-hat` is the canonical command. `lafvin`, `lafvin-sdk`, and the
corresponding `python -m lafvin_hat...` forms remain compatibility entrypoints
for existing scripts.

## Switch Back to Development Mode

Stop the deployed Runtime first:

```bash
sudo systemctl stop lafvin-hat
```

Start the development Runtime:

```bash
cd ~/LAFVIN-Audio-Display-HAT
source .venv/bin/activate
lafvin-hat runtime start --env-file .env --backend lafvin-hat
```

After testing, press `Ctrl+C` and restore the deployed service:

```bash
sudo systemctl start lafvin-hat
```

## Update the Checkout

For ordinary Runtime and bundled-application source updates:

```bash
cd ~/LAFVIN-Audio-Display-HAT
git pull
sudo systemctl restart lafvin-hat
```

When Python dependencies or deployment assets changed:

```bash
cd ~/LAFVIN-Audio-Display-HAT
git pull
sudo bash deploy/install_raspberry_pi.sh
sudo systemctl restart lafvin-hat
```

When the hardware profile changed:

```bash
cd ~/LAFVIN-Audio-Display-HAT
sudo systemctl stop lafvin-hat
sudo bash install_driver.sh --yes
sudo reboot
```

After reboot:

```bash
cd ~/LAFVIN-Audio-Display-HAT
sudo bash install_driver.sh --check
```

## Deployment Ownership and Recovery

Run the deployment installer with `sudo` from the normal user that owns the
checkout. When invoking it directly as root, identify that user explicitly:

```bash
sudo bash deploy/install_raspberry_pi.sh --user pi
```

Deployment records absolute paths to the checkout and its virtual
environment. After moving or renaming the checkout, rerun the installer and
restart the Runtime:

```bash
sudo bash deploy/install_raspberry_pi.sh
sudo systemctl restart lafvin-hat
```

Persistent Runtime configuration is stored in
`/etc/lafvin-hat/runtime.env`, is preserved by repeated deployment and
undeployment, and is restricted to root and the Runtime user's primary group.

If WM8960 calibration verification fails after boot, collect the observed
capture value and service logs before restarting anything:

```bash
amixer -c wm8960soundcard cget 'name=Capture Volume' | grep values
sudo systemctl status wm8960-soundcard --no-pager
sudo journalctl -b -u wm8960-soundcard --no-pager
sudo tail -n 100 /var/log/wm8960-soundcard.log
sudo bash install_driver.sh --check
```

## Remove the Deployment

Preview and remove only the Runtime integration:

```bash
cd ~/LAFVIN-Audio-Display-HAT
sudo bash deploy/uninstall_raspberry_pi.sh --dry-run
sudo bash deploy/uninstall_raspberry_pi.sh --yes
```

This removes the Runtime service, managed global CLI link, and deployment
metadata. It preserves the checkout, `.venv`, Runtime configuration,
application data, logs, and hardware profile.

To remove the recorded WM8960 profile as well:

```bash
sudo bash uninstall_driver.sh --dry-run
sudo bash uninstall_driver.sh --yes
sudo reboot
```

The hardware uninstaller preserves packages, fonts, shared SPI/I2C
configuration, the checkout, and Runtime data.

If you need to reinstall, run the following command in the project directory:

```bash
sudo bash install_driver.sh
sudo reboot
sudo bash deploy/install_raspberry_pi.sh
sudo systemctl start lafvin-hat
```

## Desktop and Simulator Development

On Windows without the physical HAT, use PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
lafvin-hat runtime start
```

On WSL2 or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
lafvin-hat runtime start
```

Open the simulator control panel at:

```text
http://127.0.0.1:17880
```

Default endpoints:

- Linux/WSL: Unix socket under
  `$XDG_RUNTIME_DIR/lafvin-hat/runtime.sock`
- Windows: TCP at `127.0.0.1:8765`

Override the endpoint when needed:

```bash
lafvin-hat runtime start --endpoint tcp://127.0.0.1:8765
```

Inject simulator-only button events from another terminal:

```bash
lafvin-hat sim button pressed
lafvin-hat sim button released
```

## Application Rendering

- System Status, Volume, Chatbot, and Translator use the app-facing Raw Frame
  Toolkit in `lafvin_hat.ui`.
- One Button Jump and Video Player draw custom Raw Frame content directly.
- Runtime Home, shell, and hosted Hardware Test remain Runtime-owned.
- The legacy declarative UI service remains for compatibility and Runtime
  internals, but first-party foreground applications use Raw Frame manifests.

Place the Video Player file at `assets/videos/test.mp4`.

For application manifests, Toolkit use, Raw Frame lifecycle, logs, and
ownership boundaries, read
[`docs/APP_DEVELOPMENT.md`](docs/APP_DEVELOPMENT.md). Visual rules are
documented in [`docs/UI_GUIDE.md`](docs/UI_GUIDE.md).

## Documentation

- [Documentation map](docs/README.md)
- [Application development](docs/APP_DEVELOPMENT.md)
- [UI Toolkit guide](docs/UI_GUIDE.md)
- [Simulator guide](docs/SIMULATOR.md)
- [简体中文说明](README.zh-CN.md)
- [Third-party notices](docs/THIRD_PARTY_NOTICES.md)

## Third-Party Components

LAFVIN Audio Display HAT bundles the unmodified HarmonyOS Sans font for its
device UI. Its copyright notice and license are retained at
[`assets/font/HarmonyOS Sans/LICENSE-update.txt`](<assets/font/HarmonyOS Sans/LICENSE-update.txt>).

The repository also contains adapted or separately licensed components. Read
[Third-Party Notices](docs/THIRD_PARTY_NOTICES.md) before redistributing a
device image or checkout.

## Repository Layout

```text
src/lafvin_hat/
  hardware/      Bundled hardware adaptation modules
  runtime/       Device Runtime, app lifecycle, UI, events, and backends
  sdk/           Application SDK
  schemas/       Packaged protocol and manifest schemas
apps/            First-party applications
assets/          Project-level videos, images, audio, and font resources
tests/           Unit and integration tests
docs/            Application, UI, simulator, release, and licensing guides
deploy/          systemd, environment, and Raspberry Pi deployment assets
```
