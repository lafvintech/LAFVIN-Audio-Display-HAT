# LAFVIN Audio Display HAT 文档

这是 LAFVIN Audio Display HAT 的用户教程源文件。文档面向首次使用树莓派
和 HAT 模块的用户，主线从开箱、烧录 Raspberry Pi OS、安装模块，到部署为
开机自启动的设备。

产品源码与部署脚本位于
[`LAFVIN-Audio-Display-HAT`](https://github.com/lafvintech/LAFVIN-Audio-Display-HAT)。

当前文档以简体中文编写；确认内容后可按页面逐一翻译为英文。

## Build

From the template root:

```powershell
cd docs
.\make.bat html
```

On Linux or macOS:

```bash
cd docs
make html
```

## 文档结构

- `about_this_kit.rst`：模块介绍、规格、包装内容和兼容性。
- `Preparation/`：系统烧录、HAT 安装、首次启动与登录。
- `Tutorial/`：从克隆项目、安装驱动到部署 Runtime 的首次安装主线。
- `Appendix/`：更新、恢复、故障排查和发布检查。

产品实物图、包装图和安装方向图应放在 `docs/source/img/`。图片到位后，请在
对应步骤的下方插入图片，不要集中放在页面末尾。
