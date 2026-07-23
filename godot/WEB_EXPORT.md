# Godot Web Runtime 构建与发布

## 目标

ElfieNest 正常运行时由 Electron Desktop 监督 Python/FastAPI 服务，并在隐藏的
Chromium BrowserWindow 中加载已经导出的 Godot Web Runtime；不读取 `godot/`
源项目，也不要求运行用户安装 Godot。

Godot 编辑器和 Export Templates 只属于构建环境：

- 修改 `godot/` 场景、脚本、模型或材质的开发者需要安装。
- CI 发布构建机需要安装。
- 只运行 `./elfienest.sh start` 的用户不需要安装。

## 固定目录

| 内容 | 路径 |
| --- | --- |
| Godot 源项目 | `godot/` |
| Web 导出预设 | `godot/export_presets.cfg` |
| 正式 Web Runtime | `build/components/godot-web/` |
| Web 入口 | `build/components/godot-web/elfienest.html` |
| 构建清单 | `build/components/godot-web/build-manifest.json` |

正式目录至少包含：

```text
elfienest.html
elfienest.js
elfienest.wasm
elfienest.pck
build-manifest.json
```

Godot 可能额外生成 AudioWorklet 等 JavaScript 文件，这些文件也必须随包交付。

## 版本要求

`godot/project.godot` 当前声明 Godot 4.7。发布时必须同时使用：

1. Godot 4.7 编辑器或命令行程序。
2. Godot 4.7 官方 Export Templates。

Godot 主次版本和 Templates 不一致时不得发布。构建脚本默认会拒绝这种情况。

在 Godot 编辑器中安装 Templates：

1. 打开 `Editor > Manage Export Templates`。
2. 下载或选择 Godot 4.7 官方 `export_templates.tpz`。
3. 安装完成后关闭对话框。

## 标准构建命令

在仓库根目录运行：

```bash
GODOT_BIN=/path/to/godot4.7 ./elfienest.sh build-godot-web
```

也可以显式传参：

```bash
./elfienest.sh build-godot-web --godot /path/to/godot4.7
```

构建器会执行以下步骤：

1. 检查项目版本与 Godot 版本。
2. 使用 `Web` preset 执行 release 导出。
3. 先输出到同级临时目录。
4. 检查 `html/js/wasm/pck` 是否完整。
5. 计算每个文件的 SHA-256 并生成 manifest。
6. 成功后原子替换正式目录；失败时保留上一个可运行版本。

只检查现有产物：

```bash
./elfienest.sh build-godot-web --check
```

## Godot 编辑器手工导出

命令行构建是团队标准流程。需要在编辑器排查导出问题时，可以：

1. 使用 Godot 4.7 打开 `godot/project.godot`。
2. 打开 `Project > Export`。
3. 选择仓库已有的 `Web` preset。
4. 点击 `Export Project`。
5. 输出入口选择 `build/components/godot-web/elfienest.html`。

手工导出不会生成 ElfieNest 的 `build-manifest.json`，因此完成排查后仍需运行一次标准构建命令。

## 开发与发布流程

没有修改 Godot 资源时，不要重复导出。

修改 Godot 资源后的流程：

```text
修改 godot/ 源资源
  -> 运行 Godot 场景测试
  -> ./elfienest.sh build-godot-web
  -> ./elfienest.sh build-godot-web --check
  -> ./elfienest.sh start
  -> 浏览器验收 3D 房间
  -> 提交 Godot 源资源和构建脚本，CI 重新生成 Web Runtime
```

发布流水线也必须执行同一个构建命令，并在打包阶段将
`build/components/godot-web/` 组装到
`build/staging/<platform-arch>/resources/godot-web/`。Windows、Linux 和 macOS
使用同一套 WebAssembly 资源，不需要分别导出三个原生 Godot 应用。`build/`
属于可再生中间产物，不提交 Git。

## 正常运行

```bash
./elfienest.sh start
```

打包后的 Desktop 会启动 ElfieNest Core、Ollama，并在 Electron 隐藏的
BrowserWindow 中加载 Godot Web Runtime。Godot Runtime 是持续存在的精灵巢世界
实例，负责房间、碰撞、角色移动和状态上报；Web 页面只是观察和控制客户端，
不负责创建精灵巢。Python Core 不再自行启动 Godot。

普通用户不需要安装 Godot。Godot 编辑器和 Export Templates 只属于
`./developer.sh build-godot-web` 的开发/构建环境；导出的 WebAssembly 资源由
Electron/Chromium 承载。

`build/components/godot-web/` 是唯一规范导出位置。开发态 Python Core 从该目录
挂载 Godot Runtime；发布时构建编排器把同一份产物复制到平台 staging，Electron
只消费 staging，不在 `desktop/` 或 Web 源码目录维护长期副本。
