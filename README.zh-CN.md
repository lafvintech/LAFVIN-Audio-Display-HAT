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

当前公开预发布版本为 `0.3.0b1`。

除非组件自己的许可证另有说明，项目源代码和项目创建的测试媒体使用
[Apache License 2.0](LICENSE)。重新分发本项目或设备镜像前，请阅读
[NOTICE](NOTICE)、[CHANGELOG.md](CHANGELOG.md) 和
[第三方声明](docs/THIRD_PARTY_NOTICES.md)。

## 开始之前

当前硬件流程已经在以下环境测试：

- Raspberry Pi Zero 2 W
- Raspberry Pi 5
- 当前 64 位 Raspberry Pi OS
- Python 3.11 或更高版本

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
| `ai` | 安装 OpenAI-compatible Provider 支持 |

### 5. 配置开发模式

```bash
cp .env.example .env
nano .env
```

使用真实 OpenAI-compatible Provider：

```ini
LAFVIN_AI_PROVIDER=openai-compatible
OPENAI_API_KEY=替换为你的API_KEY
OPENAI_BASE_URL=https://api.openai.com/v1
LAFVIN_ASR_MODEL=whisper-1
LAFVIN_LLM_MODEL=gpt-4o-mini
LAFVIN_TTS_MODEL=tts-1
LAFVIN_TTS_VOICE=alloy
```

只进行离线测试：

```ini
LAFVIN_AI_PROVIDER=fake
```

本地 `.env` 已被 Git 忽略。不要在截图、日志、问题报告或提交中暴露 API Key。

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

部署过程不会复制 checkout 中的 `.env`。持久 Runtime 使用独立配置：

```bash
sudo nano /etc/lafvin-hat/runtime.env
```

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

## 应用与日志命令

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

## 切换回开发模式

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

## 更新 Checkout

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
都会保留该文件，并将访问权限限制为 root 和 Runtime 用户的主用户组。

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

## 桌面与模拟器开发

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
