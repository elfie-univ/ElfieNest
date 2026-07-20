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
├── python-core/ElfieNestCore
├── ollama/ollama
└── manifest.json
```

`manifest.json` 应记录版本和哈希。模型不随安装包提交，首次启动时由 Ollama 下载到
用户数据目录的 `models/`，这样升级应用不会重复携带大文件。

资源准备完成后，在 `desktop/` 目录设置 `ELFIENEST_TARGET=<platform-arch>`，执行
`pnpm build-resource-manifest` 生成并校验 `manifest.json`。资源缺失或路径不是文件
时命令会失败，不会生成不完整的安装清单。最终安装包只能输出到根 `dist/`。
