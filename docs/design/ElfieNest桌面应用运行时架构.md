# ElfieNest 桌面应用运行时架构

## 目标

ElfieNest 对用户表现为一个跨平台桌面应用。用户只安装 ElfieNest，不需要
单独安装 Godot、Node.js、Python 或 Ollama。开发者和构建机才需要 Godot
编辑器、导出模板和 Node 工具链。

## 应用分层

```text
ElfieNest Desktop（Electron）
├── TypeScript 管理界面
├── 安装引导和 Owner 初始化
├── 进程监督器
├── Python Core 子进程
├── Godot Web Runtime 隐藏窗口
└── Ollama 后台服务
```

- Electron 主进程只负责生命周期、IPC、窗口和依赖状态，不承载精灵业务逻辑。
- TypeScript 页面负责安装引导、管理台和状态展示。
- Python Core 负责数据库、精灵大脑、房间状态、API 和 WebSocket。
- Godot Web Runtime 是持续存在的精灵巢世界实例，运行在 Electron 内置 Chromium
  的独立隐藏窗口中，不由用户打开的管理页面创建。
- Ollama 只作为本机 HTTP 推理服务运行，不依赖其聊天前端。

## 应用包与用户数据

应用包内放只读、可发布的程序和资源：

```text
resources/
├── godot-web/                 # html/js/wasm/pck
├── python-core/               # 各平台打包后的 Core
├── ollama/<platform>/         # 各平台 Ollama 可执行文件
└── manifest.json              # 版本、哈希、最低资源要求
```

用户数据放在 `~/.elfienest/`（Windows 使用对应用户数据目录）：

```text
~/.elfienest/
├── config.yaml
├── nest.db
├── models/                    # Ollama 模型，不放入 Electron asar
├── elfies/
├── runtime/                   # 运行时 PID、状态和临时套接字
├── logs/
├── cache/
└── backups/
```

应用代码和用户数据必须分离，升级应用不能覆盖数据库、Owner 配置或模型。

## 首次安装流程

1. Electron 检查当前平台和应用包 manifest。
2. 检查 Python Core、Godot Web Runtime 和 Ollama Runtime 的文件哈希。
3. 创建用户数据目录和权限。
4. 启动 Ollama 后台服务并检查 `127.0.0.1:11434`。
5. 按低配配置下载 `qwen3.5:0.8b`；视觉模型按需下载。
6. 启动 Python Core，等待 HTTP、管理 WebSocket 和 Godot WebSocket 就绪。
7. 创建或恢复 Owner。
8. 启动隐藏 Godot Web Runtime，等待 `runtime_ready` 握手。
9. 打开管理页面。

## 日常启动和停止

Electron 主进程按固定顺序启动：

```text
Ollama → Python Core → Godot Web Runtime → 管理页面
```

停止时按反向顺序发送优雅退出，超时才强制终止。任何一个进程异常退出，
监督器都要在管理页面显示具体组件状态，不得静默重启造成数据竞争。

## Ollama 依赖策略

不同系统的官方安装方式不同，因此不能依赖用户预先安装全局命令。ElfieNest
对外提供统一安装流程，内部按平台选择官方二进制或官方安装包，并固定版本。
运行时只调用 `ollama serve` 和本地 HTTP API；不启动 Ollama 聊天界面。

模型下载到用户数据目录，支持断点、哈希校验、取消和重新下载。安装包不默认
携带大模型，避免每次升级都重新下载几十 GB 的资源。

## 平台发布

源码和 Godot Web 产物保持一套；Electron 仍然需要分别构建：

```text
ElfieNest-macOS.dmg
ElfieNest-Windows.exe
ElfieNest-Linux.AppImage
```

用户不需要安装任何开发工具。构建流水线负责生成三平台安装包、签名和 manifest。

## 低配边界

- 默认使用 `qwen3.5:0.8b`。
- Godot 运行时持续存在，但没有观察者时不抓取摄像头帧。
- 视觉截图按需、低频、限并发。
- Electron 只保留管理窗口和一个 Godot Runtime 隐藏窗口。
- 8GB 作为最低验证目标，16GB 作为推荐目标。
