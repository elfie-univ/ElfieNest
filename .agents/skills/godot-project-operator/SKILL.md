---
name: godot-project-operator
description: 安全检查仓库内的 Godot 项目，执行单次 headless 验证、引擎版本检查和进程状态检查。Codex 在排查 Godot 启动错误、执行 Godot 专项门禁或检查 Godot 进程时必须使用此技能。
---

# Godot 项目操作

使用受控流程操作 Godot，避免重复实例、版本升级污染和误关用户进程。执行前读取 [references/elfienest.md](references/elfienest.md) 获取本项目路径和场景信息。

## 强制规则

1. 先运行 `godot_guard.py status` 和 `git status --short`，再决定是否启动。
2. Godot 专项门禁只允许单次、同步、headless 验证。禁止使用 `open -n`、启动编辑器、启动游戏或为看日志、截图、重建缓存并行启动实例。
3. 检测到已有 Godot 进程时停止自动启动。复用已有窗口；无法确认窗口归属时先询问用户，不得批量终止进程。
4. 遵循 `project.godot` 声明的引擎主次版本。版本不一致时不得直接打开可编辑项目；只有用户明确同意后才能传入 `--allow-version-mismatch`。
5. 启动前记录工作区状态，结束后再次检查。Godot 自动修改的 `project.godot`、`*.import` 或场景文件不得直接保留或提交；先展示差异并说明来源。
6. 仅在没有 Godot 进程时运行一次 headless 验证，并等待该进程完全退出。不得后台启动、自动重试或把临时验证进程留在后台。
7. Godot 发生崩溃时立即失败并保留统一入口输出的命令、项目、版本、父进程和退出码证据；不得再次拉起。
8. 结束前再次运行 `status`，确认没有遗留的验证进程。

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

- 验证资源：确认没有 Godot 进程后运行 `godot_guard.py validate`。该命令只启动一次同步 headless 进程。

`doctor` 和 `status` 只检查环境与进程，不启动项目；`validate` 是唯一的 Godot 专项启动入口。

### 3. 验收与清理

1. 读取统一入口输出，确认 headless 进程已退出且没有崩溃或超时。
2. 运行：

```bash
python3 .agents/skills/godot-project-operator/scripts/godot_guard.py status
git status --short
git diff -- godot_project/project.godot 'godot_project/**/*.import'
```

3. 报告验证结果、崩溃证据（如有）以及是否产生源码变更。

## 受控启动脚本

使用 [scripts/godot_guard.py](scripts/godot_guard.py) 执行重复操作：

```bash
python3 .agents/skills/godot-project-operator/scripts/godot_guard.py --help
```

通过 `GODOT_BIN` 指定 Godot 可执行文件。只有用户明确接受版本差异时才使用 `--allow-version-mismatch`。脚本拒绝在已有 Godot 进程时继续验证，这是安全行为，不要绕过。
