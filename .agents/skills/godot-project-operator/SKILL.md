---
name: godot-project-operator
description: 安全检查仓库内的 Godot 项目，执行单次 headless 验证、引擎版本检查和进程状态检查。Codex 在排查 Godot 启动错误、执行 Godot 专项门禁或检查 Godot 进程时必须使用此技能。
---

# Godot 项目操作

使用受控流程操作 Godot，避免重复实例、版本升级污染和误关用户进程。执行前读取 [references/elfienest.md](references/elfienest.md) 获取本项目路径和场景信息。

## 执行环境

本技能不能自行提升权限。Codex 的默认命令在沙箱中运行；真实 Godot 只能在用户授权的
本机主机环境运行。在 Codex 中，这对应执行器的
`sandbox_permissions=require_escalated` 授权模式。沙箱只允许做静态检查和无启动的诊断；
如果 `status` 无法读取进程表，必须停止并通过执行器请求一次主机授权，不得继续调用
`validate`。

授权后的本机验证使用仓库入口 `scripts/quality/checks/godot_host.sh`。Codex 应以主机授权方式
调用它；用户不需要手工复制命令到 Terminal。若执行器无法提供授权执行，再把同一个入口
交给用户在普通 Terminal 中运行。

## 强制规则

1. 先运行 `godot_guard.py status` 和 `git status --short`，再决定是否启动；如果当前环境
   无法执行 `status`，不得启动任何 Godot 子进程。
2. Godot 专项门禁只允许单次、同步、headless 验证。禁止使用 `open -n`、启动编辑器、启动游戏或为看日志、截图、重建缓存并行启动实例。
3. 检测到当前项目或归属不明的 Godot 进程时停止自动启动。已确认属于其他项目的进程不阻塞当前项目；无法确认窗口归属时先询问用户，不得批量终止进程。
4. 遵循 `project.godot` 声明的引擎主次版本。版本不一致时不得直接打开可编辑项目；只有用户明确同意后才能传入 `--allow-version-mismatch`。
5. 启动前记录工作区状态，结束后再次检查。Godot 自动修改的 `project.godot`、`*.import` 或场景文件不得直接保留或提交；先展示差异并说明来源。
6. 仅在没有当前项目或归属不明的 Godot 进程时运行一次 headless 验证，并等待该进程完全退出。其他项目的进程不阻塞验证；不得后台启动、自动重试或把临时验证进程留在后台。
7. Godot 发生崩溃时立即失败并保留统一入口输出的命令、项目、版本、父进程和退出码证据；不得再次拉起。
8. 结束前再次运行 `status`，确认没有遗留的验证进程。

## 标准流程

### 1. 检查环境

从仓库根目录运行：

```bash
python3 .agents/skills/godot-project-operator/scripts/godot_guard.py status
git status --short
```

这里不把 `doctor` 放在真实验证前面：当前 `doctor` 会通过 `Godot --version` 启动额外
进程。真实验证直接从一次 headless 运行的输出中读取版本；`doctor` 只作为主机环境中的
独立诊断命令，不得与 `validate` 组合成一次验证流程。

### 2. 选择一种运行方式

- 验证资源：确认没有 Godot 进程后运行 `godot_guard.py validate`。该命令只启动一次同步 headless 进程。
  - 当前项目或归属不明的 Godot 进程存在时拒绝启动；已确认属于其他项目的进程不阻塞验证。

在 Codex 中执行真实验证时，使用主机授权调用：

```bash
bash scripts/quality/checks/godot_host.sh \
  res://scripts/test/test_scene_resource_contract.gd
```

该入口先检查主机进程表，再调用一次 `validate`；沙箱中检查失败时不会启动 Godot。

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

通过 `GODOT_BIN` 指定 Godot 可执行文件。只有用户明确接受版本差异时才使用 `--allow-version-mismatch`。脚本拒绝在当前项目或归属不明的 Godot 进程存在时继续验证；已确认属于其他项目的实例不会阻塞当前项目。
