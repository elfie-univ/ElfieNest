# Desktop 运行时资源

发布构建前，构建流水线必须把三类平台产物放到对应目录。这里不放 Godot 编辑器、
Node.js 或用户数据库：

```text
build/staging/<platform-arch>/resources/
├── godot-web/
│   ├── elfienest.html
│   ├── elfienest.js
│   ├── elfienest.wasm
│   └── elfienest.pck
├── web/
│   ├── manifest.json
│   ├── login.html
│   ├── chat.html
│   ├── manage.html
│   └── assets/
├── python-core/ElfieNestCore
├── ollama/ollama
└── manifest.json
```

这是“单 target staging root”。每次只放当前目标平台需要的资源，不在同一个
`resources/` 下嵌套 `darwin/`、`win32/`、`linux/` 多平台目录。Windows 目标目录中的
两个可执行文件名分别是 `python-core/ElfieNestCore.exe` 和 `ollama/ollama.exe`。`web/`
必须是前端 Vite 构建产物的完整副本；Electron 启动 Core 时将其作为
`ELFIENEST_WEB_BUILD_DIR` 传入，Core 不会回退到旧静态控制台。

`manifest.json` 应记录版本和哈希。模型不随安装包提交，首次启动时由 Ollama 下载到
用户数据目录的 `models/`，这样升级应用不会重复携带大文件。

使用 `scripts/assemble_desktop_resources.py` 组装时，它会先校验已下载 Ollama archive
的固定 SHA-256，再复制 Vite、Godot Web、target-native Python Core 和 Ollama，最后
原子写入 `manifest.json`。资源缺失、archive 被篡改或路径不是文件时命令会失败，
不会生成不完整的安装清单。Electron 在已打包模式还会再次验证清单，之后才生成
任何受管子进程。最终安装包只能输出到根 `dist/`。

当前 Desktop 资源清单代码支持的 target：

- `darwin-arm64`
- `darwin-x64`
- `win32-x64`
- `linux-x64`
