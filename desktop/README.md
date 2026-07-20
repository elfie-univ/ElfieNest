# ElfieNest Desktop

这里是跨平台 Electron 外壳。它负责 TypeScript 管理界面、首次安装引导和本地进程监督，
不承载 Python 或 Godot 的业务逻辑。

## 进程边界

- Electron 主进程：窗口、IPC、安装检查、进程启动和停止。
- Renderer：安装引导和管理页面。
- Python Core：由应用包内的打包程序启动。
- Godot Web Runtime：由 Electron 的隐藏 BrowserWindow 启动并持续运行。
- Ollama：由应用包内或安装器准备的后台 `ollama serve` 启动。

## 当前实现

`src/main.ts` 会创建一个隐藏的 Godot Web BrowserWindow，并通过
`src/supervisor/supervisor.ts` 按 Ollama → Python Core → Godot Web 的顺序启动依赖。源码开发时可用
`ELFIENEST_CORE_BIN` 和 `ELFIENEST_OLLAMA_BIN` 指向本机调试运行时；发布包从
`resources/` 读取平台专属组件。

生产安装包仍需要在构建流水线中生成 Python Core 和 Ollama 的平台产物，开发者不应把
Godot 编辑器或用户数据放入安装包。

## 固定构建路径

Desktop 的 TypeScript 编译结果只能进入根目录 `build/components/desktop/`。发布前的
平台资源只能按 target 放入根目录 `build/staging/<platform-arch>/resources/`，例如：

```text
build/staging/darwin-arm64/resources/
├── godot-web/
├── python-core/ElfieNestCore
├── ollama/ollama
└── manifest.json
```

Windows target 使用 `python-core/ElfieNestCore.exe` 和 `ollama/ollama.exe`。不要再创建
`resources/python-core/darwin/`、`resources/ollama/win32/` 这类把多平台塞进同一个
resources 根目录的旧结构。
