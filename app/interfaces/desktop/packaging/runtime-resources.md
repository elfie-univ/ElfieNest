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
│   ├── index.html
│   └── assets/
├── config/
│   ├── app/
│   ├── brain/
│   ├── models/
│   ├── nest/
│   ├── species/
│   └── tools/
├── python-core/ElfieNestCore
├── management-cli/ElfieNestCli
└── manifest.json
```

这是“单 target staging root”。每次只放当前目标平台需要的资源，不在同一个
`resources/` 下嵌套 `darwin/`、`win32/`、`linux/` 多平台目录。Windows 目标目录中的
可执行文件名分别是 `python-core/ElfieNestCore.exe` 和
`management-cli/ElfieNestCli.exe`。`web/`
必须是前端 Vite 构建产物的完整副本；Electron 启动 Core 时将其作为
`ELFIENEST_WEB_BUILD_DIR` 传入，Core 不会回退到旧静态控制台。

`manifest.json` 使用 schema 2，记录应用版本、40 位源码 Git revision、目标平台和每个
资源文件的哈希。Desktop 启动时会输出该 revision，便于确认安装版的真实源码来源。
Ollama 及其模型不随安装包提交；它们属于用户选择
安装并由初始化向导绑定的系统级服务，因此升级应用不会重复携带大文件或私有模型目录。

使用 `scripts/internal/build/assemble_desktop_resources.py` 组装时，它会复制 Vite、Godot Web、
target-native Python Core 和管理 CLI，最后原子写入 `manifest.json`。资源缺失或路径
不是文件时命令会失败，不会生成不完整的安装清单。Electron 在已打包模式还会再次验证
清单；Ollama 仅作为可选的已绑定公共服务做健康检查，Desktop 不下载或启动它。最终
安装包只能输出到根 `dist/`。

当前 Desktop 资源清单代码支持的 target：

- `darwin-arm64`
- `darwin-x64`
- `win32-x64`
- `linux-x64`
