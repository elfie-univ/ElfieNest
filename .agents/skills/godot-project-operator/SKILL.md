---
name: godot-project-operator
description: 安全操作仓库内的 Godot 项目，控制单实例启动、编辑器与游戏运行、引擎版本检查、场景资源验证、渲染验收和进程清理。Codex 在打开 Godot、运行或调试场景、检查最终渲染、处理导入缓存、排查 Godot 启动错误或关闭 Godot 进程时必须使用此技能。
---

# Godot 项目操作

使用受控流程操作 Godot，避免重复实例、版本升级污染和误关用户进程。执行前读取 [references/elfienest.md](references/elfienest.md) 获取本项目路径和场景信息。

## 强制规则

1. 先运行 `godot_guard.py status` 和 `git status --short`，再决定是否启动。
2. 同一时间只保留一个 Godot 图形实例。禁止使用 `open -n`，禁止为看日志、截图或重建缓存并行启动编辑器和游戏。
3. 检测到已有 Godot 进程时停止自动启动。复用已有窗口；无法确认窗口归属时先询问用户，不得批量终止进程。
4. 遵循 `project.godot` 声明的引擎主次版本。版本不一致时不得直接打开可编辑项目；只有用户明确同意后才能传入 `--allow-version-mismatch`。
5. 启动前记录工作区状态，结束后再次检查。Godot 自动修改的 `project.godot`、`*.import` 或场景文件不得直接保留或提交；先展示差异并说明来源。
6. 仅在没有图形实例时运行 headless 验证，并等待该进程完全退出。不得把临时验证进程留在后台。
7. 视觉验收优先复用当前游戏窗口，只截取 Godot 窗口或 Viewport。禁止截取整个桌面，禁止在已有实例旁再启动截图实例。
8. 用户要求保留页面时保留唯一的目标窗口；其余由本次操作创建的临时进程必须退出。结束前再次运行 `status`。

## 标准流程

### 1. 检查环境

从仓库根目录运行：

```bash
python3 .agents/skills/godot-project-operator/scripts/godot_guard.py doctor
python3 .agents/skills/godot-project-operator/scripts/godot_guard.py status
git status --short
```

若 `doctor` 报告版本不匹配，优先寻找匹配版本。不要通过打开项目让 Godot 自动升级元数据。

### 2. 选择一种运行方式

- 打开编辑器：仅在没有 Godot 进程时运行 `godot_guard.py editor`。
- 查看最终场景：已有编辑器时在该编辑器内运行主场景；没有任何 Godot 进程时运行 `godot_guard.py run`。
- 验证资源：关闭图形实例后运行 `godot_guard.py validate`。
- 查看已有窗口：聚焦现有 Godot 应用，不创建新实例；macOS 使用 `open -a Godot`，不得添加 `-n`。

`editor` 和 `run` 只负责启动一个实例。不要立即再执行另一种启动命令。

### 3. 验收与清理

1. 从现有窗口检查场景是否可见、相机是否正确、是否出现黑屏或资源缺失。
2. 读取同一实例的 Godot 输出；不要为了日志另开进程。
3. 仅关闭本次明确创建且不再需要的进程。用户要求保留的窗口不要关闭。
4. 运行：

```bash
python3 .agents/skills/godot-project-operator/scripts/godot_guard.py status
git status --short
git diff -- godot_project/project.godot 'godot_project/**/*.import'
```

5. 报告保留了哪个窗口、关闭了哪些临时进程、验证结果以及是否产生源码变更。

## 受控启动脚本

使用 [scripts/godot_guard.py](scripts/godot_guard.py) 执行重复操作：

```bash
python3 .agents/skills/godot-project-operator/scripts/godot_guard.py --help
```

通过 `GODOT_BIN` 指定 Godot 可执行文件。只有用户明确接受版本差异时才使用 `--allow-version-mismatch`。脚本拒绝在已有 Godot 进程时继续启动，这是安全行为，不要绕过。
