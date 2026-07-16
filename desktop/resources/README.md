# Desktop 运行时资源

发布构建前，构建流水线必须把三类平台产物放到对应目录。这里不放 Godot 编辑器、
Node.js 或用户数据库：

```text
resources/
├── godot-web/
│   ├── elfienest.html
│   ├── elfienest.js
│   ├── elfienest.wasm
│   └── elfienest.pck
├── python-core/
│   ├── darwin/ElfieNestCore
│   ├── win32/ElfieNestCore.exe
│   └── linux/ElfieNestCore
├── ollama/
│   ├── darwin/ollama
│   ├── win32/ollama.exe
│   └── linux/ollama
└── manifest.json
```

`manifest.json` 应记录版本和哈希。模型不随安装包提交，首次启动时由 Ollama 下载到
用户数据目录的 `models/`，这样升级应用不会重复携带大文件。
