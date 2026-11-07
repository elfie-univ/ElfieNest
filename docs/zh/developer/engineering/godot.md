# Godot

Godot 是房屋、几何、世界坐标、移动、碰撞、角色和渲染的唯一源码来源。

## 允许放在 Godot 的内容

- 场景、节点、房间和家具资源；
- 角色模型、动画、碰撞和导航；
- Web Runtime 的渲染与空间交互；
- 与 Python Core 交换事件的适配层。

## 不应放在 Godot 的内容

- Elfie 的完整身份、记忆和人格；
- Nest 的产品账户、领养和聊天规则；
- Python 侧复制的房屋蓝图或坐标事实。

打开、运行或截图前，先核对 `project.godot` 的 Godot 版本和已有进程，再按
[Godot README](https://github.com/elfie-univ/ElfieNest/blob/main/godot_project/README.md)
与 [Web 导出说明](godot.md#web-export) 的流程操作。

## 居民状态接线

权威 Gateway 使用协议 4。环境命令单独携带 `life_phase`，不受灯光覆盖影响：
白天／黎明所有门常开，黄昏／夜间使用已有感应与防夹控制。所有精灵均可进入所有房间。

正式 Nest 会话选择 Brain 具身输入。寄身前必须取得精灵已在自己的床上躺好的权威状态；
选中实体身体后，虚拟身体留床并显示罩体。已提交的领养标识与时间驱动四楼单向到达展示，
重连不会重置到达时钟。没有传送离开，也不加入声音展示。

聚焦场景验证：`bash scripts/quality/checks/godot_host.sh
res://test/test_resident_lifecycle.gd`。真实设备寄身及最终画面验收仍需单独完成。

## Web 导出 {#web-export}

产品消费已导出的 Godot Web Runtime，不直接读取 `godot_project/` 源项目。修改 Godot
资源的开发者和 CI 构建机需要 Godot 与官方 Export Templates；普通运行用户不需要安装。

### 固定目录

| 内容 | 路径 |
| --- | --- |
| Godot 源项目 | `godot_project/` |
| Web 导出预设 | `godot_project/export_presets.cfg` |
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

### 版本要求

Godot 兼容版本只由 `godot_project/project.godot` 的 `config/features` 第一项声明。
发布时必须同时使用：

1. 与该主次版本线匹配的 Godot 编辑器或命令行程序。
2. 与该版本匹配的官方 Export Templates。

Godot 主次版本和 Templates 不一致时不得发布。构建脚本默认会拒绝这种情况。

在 Godot 编辑器中安装 Templates：

1. 打开 `Editor > Manage Export Templates`。
2. 下载或选择与项目声明版本匹配的官方 `export_templates.tpz`。
3. 安装完成后关闭对话框。

### 标准构建命令

在仓库根目录运行：

```bash
GODOT_BIN=/path/to/godot ./developer.sh build-godot-web
```

也可以显式传参：

```bash
./developer.sh build-godot-web --godot /path/to/godot
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
./developer.sh build-godot-web --check
```

### Godot 编辑器手工导出

命令行构建是团队标准流程。需要在编辑器排查导出问题时，可以：

1. 使用与项目声明版本匹配的 Godot 打开 `godot_project/project.godot`。
2. 打开 `Project > Export`。
3. 选择仓库已有的 `Web` preset。
4. 点击 `Export Project`。
5. 输出入口选择 `build/components/godot-web/elfienest.html`。

手工导出不会生成 ElfieNest 的 `build-manifest.json`，因此完成排查后仍需运行一次标准构建命令。

### 开发与发布流程

没有修改 Godot 资源时，不要重复导出。

修改 Godot 资源后的流程：

```text
修改 godot_project/ 源资源
  -> 运行 Godot 场景测试
  -> ./developer.sh build-godot-web
  -> ./developer.sh build-godot-web --check
  -> ./elfienest.sh start
  -> 浏览器验收 3D 房间
  -> 提交 Godot 源资源和构建脚本，CI 重新生成 Web Runtime
```

发布流水线也必须执行同一个构建命令，并在打包阶段将
`build/components/godot-web/` 组装到
`build/staging/<platform-arch>/resources/godot-web/`。Windows、Linux 和 macOS
使用同一套 WebAssembly 资源，不需要分别导出三个原生 Godot 应用。`build/`
属于可再生中间产物，不提交 Git。


`build/components/godot-web/` 是唯一规范导出位置。开发态 Python Core 从该目录挂载
Web Runtime；发布时构建编排器把同一份产物复制到平台 staging，Electron 消费 staging，
不在 Desktop 或 Web 源码目录维护长期副本。Runtime authority 的启停归
[服务生命周期契约](../contracts/service-lifecycle.md)。
