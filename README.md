# 动漫少女桌面宠物

Windows 桌面宠物，支持角色互动、换装、人物配音和「星屿小冒险」小游戏。

## 项目内容

- Python 程序源码
- assets：角色图片、服装、音乐及配音素材
- runtime/tcl：启动器使用的 Tcl/Tk 资源
- 中文操作说明和预览图片

## 启动说明

本项目是源码版本，不是独立 EXE 安装包。目前的 CMD 启动器使用本机 Codex Python 环境（需要 Pillow），路径为 `%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe`。

具备该环境时，双击「启动动漫宠物.cmd」；直接进入小游戏可双击「直接开始冒险.cmd」。仓库未包含本机快捷方式，请使用 CMD 启动器。

其他电脑需要自行准备兼容的 Windows Python、Tkinter 和 Pillow 环境，并调整启动器中的 Python 路径。尚未验证其他电脑上的运行兼容性。

详细操作见「动漫宠物说明.md」和「小游戏说明.md」。

## 本地数据

个人存档、窗口位置、音量和服装设置、缓存不随源码提交。「先看这里.md」保留了原文件夹说明，其中提到的快捷方式及原存档未包含在此仓库中。
