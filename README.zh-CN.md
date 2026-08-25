# LAFVIN Audio Display HAT

[English](README.md) | **简体中文**

LAFVIN Audio Display HAT 是一套面向 Raspberry Pi 的便携式音频与显示平台，
适用于 AI Chatbot、翻译器、硬件诊断、媒体播放和单按钮游戏等应用。

本仓库包含设备 Runtime、应用 SDK、硬件支持、第一方应用、UI Toolkit 和部署工具。

## 项目特点

- 单一 Runtime 统一管理显示屏、按钮、RGB LED、背光、音频、应用生命周期和持久化应用数据；
- 原生 Raspberry Pi Backend 支持 LAFVIN Audio Display HAT，并包含版本化的 WM8960 硬件 Profile；
- Raw Frame SDK 和 UI Toolkit 让应用在实机和模拟器中使用相同的最终画面；
- 内置六个前台应用：System Status、Volume、Chatbot、Translator、One Button Jump 和 Video Player；
- Hardware Test 由 Runtime 托管，可以快速启动并直接访问硬件；
- Checkout-backed 部署提供统一的 `lafvin-hat` 命令、systemd 集成、应用日志和简单的 Git 更新流程。

产品名称为 **LAFVIN Audio Display HAT**。为了保持软件兼容，Python
包、命令行工具、服务、Backend 和配置目录仍使用 `lafvin-hat` 或
`lafvin_hat` 标识。

## 版本与许可证

当前公开预发布版本为 `0.3.0b3`。

除非组件自己的许可证另有说明，项目源代码和项目创建的测试媒体使用
[Apache License 2.0](LICENSE)。重新分发本项目或设备镜像前，请阅读
[NOTICE](NOTICE)、[CHANGELOG.md](CHANGELOG.md) 和
[第三方声明](docs/THIRD_PARTY_NOTICES.md)。

## 开始之前

当前硬件流程已经在以下环境测试：

- Raspberry Pi Zero 2 W
- Raspberry Pi 3 Model B+
- Raspberry Pi 4 Model B
- Raspberry Pi 5
- Raspberry Pi OS（64 位，镜像版本 260618 / 2026-06-18，Trixie）
- Python 3.11 或更高版本

Raspberry Pi 3 Model B+ 可以正常运行，但在视频播放和频繁界面刷新时会明显慢于
Pi 4 Model B 与 Pi 5。这属于预期的性能限制，不代表安装失败。

请使用稳定的电源。安装或拆卸 HAT 前，先关闭 Raspberry Pi 并断开电源。

Chatbot 和 Translator 可以连接 OpenAI-compatible API。API 费用与
ChatGPT Plus、Pro 或其他应用订阅相互独立。只需要验证本地应用流程时，
可以使用离线 Fake Provider。

## 推荐的 Raspberry Pi 安装流程

推荐的首次安装顺序为：

1. 安装并检查硬件 Profile；
2. 在开发模式中验收项目；
3. 将验收通过的 checkout 注册为持久 systemd Runtime。

### 1. 克隆项目

如果系统尚未安装 Git：

```bash
sudo apt update
sudo apt install -y git
```

克隆项目：

```bash
cd ~
git clone https://github.com/lafvintech/LAFVIN-Audio-Display-HAT.git
cd ~/LAFVIN-Audio-Display-HAT
```

### 2. 安装硬件 Profile

```bash
sudo bash install_driver.sh
sudo reboot
```

`install_driver.sh` 会安装 Raspberry Pi 系统硬件基础环境，启用 SPI、
I2C 和 I2S，安装 WM8960 Profile 与标定参数，并添加所需的 ALSA、
FFmpeg 和构建依赖。

### 3. 重启后检查硬件

重新连接 Raspberry Pi：

```bash
cd ~/LAFVIN-Audio-Display-HAT
sudo bash install_driver.sh --check
bash tools/hardware_check.sh
```

两个检查都应该显示：

```text
Result: 0 failure(s)
```

继续安装前应解决所有 failure。电源和温度 warning 也不应直接忽略。

### 4. 创建开发环境

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,hardware,ai]"
pytest
```

各个可选依赖组的用途：

| Extra | 用途 |
| --- | --- |
| `dev` | 使用 `pytest` 运行自动化测试 |
| `hardware` | 安装 `spidev` 和 `gpiod` |
| `ai` | 安装云端 ASR、LLM 和 TTS Provider 支持 |

### 5. 配置开发模式

```bash
cp .env.example .env
nano .env
```

三种能力需要独立选择。下面是全部使用 OpenAI 的配置：

```ini
LAFVIN_ASR_PROVIDER=openai
LAFVIN_LLM_PROVIDER=openai
LAFVIN_TTS_PROVIDER=openai
OPENAI_API_KEY=替换为你的API_KEY
LAFVIN_ASR_MODEL=whisper-1
LAFVIN_LLM_MODEL=gpt-4o-mini
LAFVIN_TTS_MODEL=tts-1
LAFVIN_TTS_VOICE=alloy
```

内置 Provider 的能力与 API Key 如下：

| Provider | ASR | LLM | TTS | API Key 变量 |
| --- | ---: | ---: | ---: | --- |
| `openai` | 是 | 是 | 是 | `OPENAI_API_KEY` |
| `deepseek` | 否 | 是 | 否 | `DEEPSEEK_API_KEY` |
| `kimi` | 否 | 是 | 否 | `MOONSHOT_API_KEY` |
| `claude` | 否 | 是 | 否 | `ANTHROPIC_API_KEY` |
| `minimax` | 否 | 否 | 是 | `MINIMAX_API_KEY` |
| `fish` | 是 | 否 | 是 | `FISH_AUDIO_API_KEY` |
| `openai-compatible` | 否 | 是 | 否 | `LAFVIN_LLM_API_KEY` |

如需连接其他兼容 OpenAI Chat Completions 协议的 LLM，选择
`openai-compatible`，并设置 `LAFVIN_LLM_BASE_URL`、`LAFVIN_LLM_API_KEY`
和 `LAFVIN_LLM_MODEL`。项目有意不开放自定义 ASR/TTS 端点，因为不同服务的
音频协议和格式不能假定互相兼容。

只把 ASR 替换为 Fish Audio：

```ini
LAFVIN_ASR_PROVIDER=fish
FISH_AUDIO_API_KEY=替换为你的FISH_AUDIO_API_KEY
LAFVIN_ASR_MODEL=transcribe-1
# 可选；不设置时由 Fish Audio 自动检测语言。
# LAFVIN_ASR_LANGUAGE=zh
```

Fish Audio Transcribe-1 目前是付费 Beta API，消耗 Fish Audio API Credit，
与平台 Credit 分开管理；使用前请查看最新的
[官方价格](https://docs.fish.audio/developer-guide/models-pricing/pricing-and-rate-limits)。
不在命令行中显示 Key 即可查询 API 余额：

```bash
set -a
source .env
set +a
curl -sS \
  -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
  "https://api.fish.audio/wallet/self/api-credit?check_free_credit=true"
```

返回 JSON 中的 `credit` 是当前 API Credit，也可能包含
`has_free_credit`。余额不足时可在
[Fish Audio 开发者计费页](https://fish.audio/app/developers/billing/)充值。

只把 TTS 替换为 MiniMax：

```ini
LAFVIN_TTS_PROVIDER=minimax
MINIMAX_API_KEY=替换为你的MINIMAX_API_KEY
LAFVIN_TTS_MODEL=speech-2.8-turbo
LAFVIN_TTS_VOICE=male-qn-qingse
```

只把 TTS 替换为 Fish Audio：

```ini
LAFVIN_TTS_PROVIDER=fish
FISH_AUDIO_API_KEY=替换为你的FISH_AUDIO_API_KEY
LAFVIN_TTS_MODEL=s2.1-pro
# 可选：删除原来的 OpenAI 音色，或把它改成 Fish Audio reference ID。
# 不填写 reference ID 时，由 Fish Audio 使用默认音色。
# LAFVIN_TTS_VOICE=你的Fish音色ReferenceID
```

内置服务地址默认已经生效。`MINIMAX_TTS_BASE_URL`、`FISH_AUDIO_BASE_URL`
等 Provider 专用地址仅供高级部署覆盖使用。这些服务属于第三方 API，可能需要
单独充值，和面向消费者的订阅不是一回事。

只进行离线测试：

```ini
LAFVIN_ASR_PROVIDER=fake
LAFVIN_LLM_PROVIDER=fake
LAFVIN_TTS_PROVIDER=fake
```

本地 `.env` 已被 Git 忽略。不要在截图、日志、问题报告或提交中暴露 API Key。

排查 LLM 回复和 TTS 棒读问题时，可以临时开启内容追踪：

```ini
LAFVIN_AI_LOG_CONTENT=1
```

开启后，日志会记录 LLM 原始回复和每个切片最终提交给 TTS 的清理后文本。TTS API
返回的是音频而不是“实际朗读文字”，因此请求文本是定位问题的依据。该日志可能包含
私人对话内容，默认关闭，完成排查后应删除或改回 `0`。

### 6. 运行交互式硬件测试

测试会直接访问显示、GPIO 和音频设备。运行前先停止已经部署的 Runtime：

```bash
sudo systemctl stop lafvin-hat 2>/dev/null || true
python3 tools/hardware_test.py
```

测试会要求用户逐项确认观察到的硬件结果。

### 7. 启动开发 Runtime

```bash
lafvin-hat runtime start --env-file .env --backend lafvin-hat
```

每次通过命令行启动 Runtime 时，都会将六个 bundled 第一方应用原子刷新到
当前 Runtime 数据目录，不会修改第三方应用。

另开一个终端：

```bash
cd ~/LAFVIN-Audio-Display-HAT
source .venv/bin/activate
lafvin-hat info
lafvin-hat app list
```

测试 Home、按钮手势和应用功能。完成后在第一个终端按 `Ctrl+C`，正常停止开发 Runtime。

不要同时运行开发 Runtime 和 `lafvin-hat.service`，否则两个进程会争用
显示、GPIO、音频设备和 Runtime Socket。

### 8. 部署已经验收的 Checkout

停止开发 Runtime 后执行：

```bash
cd ~/LAFVIN-Audio-Display-HAT
sudo bash deploy/install_raspberry_pi.sh
```

部署脚本会：

- 使用当前 Git checkout 和可编辑的 `.venv`；
- 安装全局 `lafvin-hat` 管理命令；
- 创建并启用 `lafvin-hat.service`；
- 将应用数据保存在 `/var/lib/lafvin-hat`；
- 将 Runtime 日志保存在 `/var/log/lafvin-hat`；
- 保留已有配置、数据、第三方应用和硬件 Profile。

首次部署时，如果 checkout 中存在 `.env`，而持久 Runtime 配置尚不存在，安装器会
询问是否将其快照复制到 `/etc/lafvin-hat/runtime.env`。提示会明确该文件可能包含
API Key 或代理凭据。选择 `Yes` 后，安装器会先验证格式，再以受限权限复制；不会
移动或删除开发环境的 `.env`。选择 `No`、使用非交互终端或项目中没有 `.env` 时，
安装器仍会安装默认模板。

重复部署会直接保留已有持久配置，不会反复询问。

<details>
<summary><strong>替换或编辑持久 Runtime 配置</strong></summary>

以后确实需要用开发配置替换时，显式执行：

```bash
sudo bash deploy/install_raspberry_pi.sh --import-project-env
```

显式导入会先验证 `.env`，并把原来的 `runtime.env` 备份到
`/var/backups/lafvin-hat/` 后再替换。也可以直接编辑持久 Runtime 配置：

```bash
sudo nano /etc/lafvin-hat/runtime.env
```

</details>

如果云端 Provider 在开发终端中正常、部署后却一直等待，请检查该终端是否导出了
`HTTP_PROXY`、`HTTPS_PROXY` 或 `ALL_PROXY`。systemd 服务不会继承交互式终端的
代理变量。直连正常时保持 `runtime.env` 中的代理示例为注释；必须使用代理时，替换
示例地址并启用适用的代理行，同时保留
`NO_PROXY=127.0.0.1,localhost,::1`，然后重启服务。Runtime 不会在请求失败后自动
切换网络线路。

然后启动并检查服务：

```bash
sudo systemctl start lafvin-hat
sudo systemctl status lafvin-hat --no-pager
sudo journalctl -u lafvin-hat -n 100 --no-pager
```

部署后无需激活 `.venv` 即可使用管理命令：

```bash
lafvin-hat info
lafvin-hat app list
lafvin-hat logs dev.lafvin.chatbot --follow
```

## 已安装的服务

完整安装后会出现两个项目相关的 systemd 单元：

| 单元 | 作用 | 正常状态 |
| --- | --- | --- |
| `lafvin-hat.service` | 持续运行的设备 Runtime | `active (running)` |
| `wm8960-soundcard.service` | 一次性应用 WM8960 配置与标定 | `active (exited)` |

前台应用是 Runtime 管理的子进程，不会注册独立的 systemd 服务。

查看服务：

```bash
systemctl list-unit-files | grep -E 'lafvin-hat|wm8960'
systemctl status lafvin-hat --no-pager
systemctl status wm8960-soundcard --no-pager
```

<details>
<summary><strong>应用与日志命令</strong></summary>

```bash
lafvin-hat info
lafvin-hat app list
lafvin-hat app start dev.lafvin.chatbot
lafvin-hat app stop dev.lafvin.chatbot
lafvin-hat logs dev.lafvin.chatbot
lafvin-hat logs dev.lafvin.chatbot --follow
```

开发应用时，可以直接注册并启动工作区中的应用：

```bash
lafvin-hat app run apps/system_status
lafvin-hat app run apps/system_volume
lafvin-hat app run apps/chatbot --follow
lafvin-hat app run apps/translator --follow
lafvin-hat app run apps/one_button_jump
lafvin-hat app run apps/video_player
```

`lafvin-hat` 是推荐命令。`lafvin`、`lafvin-sdk` 和相应的
`python -m lafvin_hat...` 形式作为兼容入口保留。

</details>

<details>
<summary><strong>切换回开发模式</strong></summary>

先停止部署 Runtime：

```bash
sudo systemctl stop lafvin-hat
```

启动开发 Runtime：

```bash
cd ~/LAFVIN-Audio-Display-HAT
source .venv/bin/activate
lafvin-hat runtime start --env-file .env --backend lafvin-hat
```

测试完成后按 `Ctrl+C`，再恢复部署服务：

```bash
sudo systemctl start lafvin-hat
```

</details>

<details>
<summary><strong>更新已部署的项目</strong></summary>

普通 Runtime 和 bundled App 源代码更新：

```bash
cd ~/LAFVIN-Audio-Display-HAT
git pull
sudo systemctl restart lafvin-hat
```

Python 依赖或部署资源发生变化：

```bash
cd ~/LAFVIN-Audio-Display-HAT
git pull
sudo bash deploy/install_raspberry_pi.sh
sudo systemctl restart lafvin-hat
```

硬件 Profile 发生变化：

```bash
cd ~/LAFVIN-Audio-Display-HAT
sudo systemctl stop lafvin-hat
sudo bash install_driver.sh --yes
sudo reboot
```

重启后检查：

```bash
cd ~/LAFVIN-Audio-Display-HAT
sudo bash install_driver.sh --check
```

</details>

## 部署所有权与恢复

请使用拥有 checkout 的普通用户通过 `sudo` 运行部署脚本。如果直接在 root
环境中执行，需要明确指定普通用户：

```bash
sudo bash deploy/install_raspberry_pi.sh --user pi
```

部署过程会记录 checkout 和虚拟环境的绝对路径。移动或重命名 checkout
后，需要重新运行部署脚本并重启 Runtime：

```bash
sudo bash deploy/install_raspberry_pi.sh
sudo systemctl restart lafvin-hat
```

持久 Runtime 配置保存在 `/etc/lafvin-hat/runtime.env`。重复部署或解除部署
都会保留该文件，并将访问权限限制为 root 和 Runtime 用户的主用户组。安装器不会
将它链接到 checkout 的 `.env`，也不会删除开发配置；只有确实需要从开发配置替换
持久副本时才使用 `--import-project-env`。

如果启动后的 WM8960 标定检查失败，请先记录实际捕获值和服务日志，不要先
重启服务：

```bash
amixer -c wm8960soundcard cget 'name=Capture Volume' | grep values
sudo systemctl status wm8960-soundcard --no-pager
sudo journalctl -b -u wm8960-soundcard --no-pager
sudo tail -n 100 /var/log/wm8960-soundcard.log
sudo bash install_driver.sh --check
```

## 解除部署

预览并仅删除 Runtime 集成：

```bash
cd ~/LAFVIN-Audio-Display-HAT
sudo bash deploy/uninstall_raspberry_pi.sh --dry-run
sudo bash deploy/uninstall_raspberry_pi.sh --yes
```

该操作删除 Runtime 服务、项目管理的全局 CLI 链接和部署元数据，但会保留
checkout、`.venv`、Runtime 配置、应用数据、日志和硬件 Profile。

继续删除项目记录拥有的 WM8960 Profile：

```bash
sudo bash uninstall_driver.sh --dry-run
sudo bash uninstall_driver.sh --yes
sudo reboot
```

硬件卸载脚本会保留软件包、字体、共享 SPI/I2C 配置、checkout 和 Runtime
数据。

如果需要重新安装,在项目目录执行下面的命令:

```bash
sudo bash install_driver.sh
sudo reboot
sudo bash deploy/install_raspberry_pi.sh
sudo systemctl start lafvin-hat
```

<details>
<summary><strong>桌面与模拟器开发</strong></summary>

在 WSL2 或 Linux 上：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
lafvin-hat runtime start
```

打开模拟器控制页面：

```text
http://127.0.0.1:17880
```

默认 Endpoint：

- Linux/WSL：`$XDG_RUNTIME_DIR/lafvin-hat/runtime.sock` 下的 Unix Socket；
- Windows：`127.0.0.1:8765` TCP。

需要时可以覆盖 Endpoint：

```bash
lafvin-hat runtime start --endpoint tcp://127.0.0.1:8765
```

从另一个终端注入仅限模拟器的按钮事件：

```bash
lafvin-hat sim button pressed
lafvin-hat sim button released
```

</details>

## 应用渲染方式

- System Status、Volume、Chatbot 和 Translator 使用 `lafvin_hat.ui`
  中面向应用的 Raw Frame Toolkit；
- One Button Jump 和 Video Player 直接绘制自定义 Raw Frame；
- Runtime Home、Shell 和托管的 Hardware Test 由 Runtime 管理；
- 旧的声明式 UI 服务仅为兼容和 Runtime 内部功能保留，第一方前台应用使用
  Raw Frame manifest。

Video Player 的视频文件固定放在 `assets/videos/test.mp4`。

应用 manifest、Toolkit、Raw Frame 生命周期、日志和所有权边界请阅读
[`docs/APP_DEVELOPMENT.md`](docs/APP_DEVELOPMENT.md)，视觉规范请阅读
[`docs/UI_GUIDE.md`](docs/UI_GUIDE.md)。

## 文档

- [文档索引](docs/README.md)
- [应用开发](docs/APP_DEVELOPMENT.md)
- [UI Toolkit 指南](docs/UI_GUIDE.md)
- [模拟器指南](docs/SIMULATOR.md)
- [English README](README.md)
- [第三方声明](docs/THIRD_PARTY_NOTICES.md)

## 第三方组件

LAFVIN Audio Display HAT 为设备 UI 捆绑了未经修改的 HarmonyOS Sans
字体，其版权声明和许可证保留在
[`assets/font/HarmonyOS Sans/LICENSE-update.txt`](<assets/font/HarmonyOS Sans/LICENSE-update.txt>)。

仓库还包含经过适配或使用独立许可证的组件。重新分发设备镜像或 checkout
前，请阅读[第三方声明](docs/THIRD_PARTY_NOTICES.md)。

## 仓库结构

```text
src/lafvin_hat/
  hardware/      捆绑的硬件适配模块
  runtime/       设备 Runtime、应用生命周期、UI、事件和 Backend
  sdk/           应用 SDK
  schemas/       打包的协议和 manifest schema
apps/            第一方应用
assets/          项目视频、图片、音频和字体资源
tests/           单元测试和集成测试
docs/            应用、UI、模拟器、发布和许可证文档
deploy/          systemd、环境配置和 Raspberry Pi 部署资源
```
