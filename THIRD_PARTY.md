# 第三方组件

Windows 安装包使用下列上游组件。各组件归原作者所有，沿用上游授权。项目本身的完整源码、固件和安装脚本可在对应 [GitHub Release](https://github.com/RP27-EC/Motor-Test-Bench/releases) 的 `Source code` 下载。

| 组件 | 授权或源码 |
| --- | --- |
| PyQt5 5.15.11 | Riverbank Computing，GPLv3。[源码下载](https://pypi.org/project/PyQt5/5.15.11/#files) |
| Qt 5.15.2（PyQt5-Qt5） | Qt Company 及贡献者，LGPLv3。[对应源码](https://download.qt.io/archive/qt/5.15/5.15.2/single/) · [LGPLv3](tools/LGPL-3.0.txt) |
| PyQt5-sip 12.18.0 | Riverbank Computing，BSD-2-Clause。[源码及授权](https://pypi.org/project/PyQt5-sip/12.18.0/#files) |
| CPython 3.10.11 | Python Software Foundation。[源码及授权](https://www.python.org/downloads/release/python-31011/) |
| intelhex 2.3.0、pyelftools 0.33 | [intelhex（BSD-3-Clause）](https://pypi.org/project/intelhex/2.3.0/#files) · [pyelftools（公有领域）](https://pypi.org/project/pyelftools/0.33/#files) |
| PyInstaller 6.22.3 | GPLv2 或更新版，含打包与分发例外。[源码及授权](https://github.com/pyinstaller/pyinstaller/tree/v6.22.3) |
| probe-rs 0.31.0 | MIT 或 Apache-2.0。[源码及授权](https://crates.io/crates/probe-rs/0.31.0)。探针后端的完整依赖版本见 `probe_bridge/Cargo.lock`。 |
| STM32 HAL、CMSIS | STMicroelectronics 与 Arm。保留 `firmware/` 中的上游版权、授权和文件头，CMSIS 的 Apache-2.0 授权随安装包提供。 |
| Inno Setup 6.7.4 及简体中文翻译 | [安装工具源码](https://github.com/jrsoftware/issrc/tree/is-6_7_4) · [工具授权](tools/Inno-Setup-License.txt) · [翻译出处](https://jrsoftware.org/inno-setup/translations) |

Qt DLL 位于安装目录的 `_internal\PyQt5\Qt5\bin`，可用接口兼容的 Qt 5 构建替换。LGPLv3 原文也随安装包提供。
