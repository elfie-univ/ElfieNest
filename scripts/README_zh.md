# scripts 目录

> 中文版：本文件 · [English](README.md)

`scripts/` 保存仓库级启动、构建、质量检查和人工诊断入口。普通用户与贡献者应
优先使用根目录稳定入口；不要绕过入口脚本自行拼装一套运行环境。

## 布局与稳定性契约

根目录只保留被启动器、CI、发布自动化或生产 Bootstrap 引用的稳定命令或 import 路径。
内部整理不得移动下列路径：

| 稳定根路径 | 分类 | 所有者/调用方 |
| --- | --- | --- |
| `bootstrap.sh` | Bootstrap 入口 | 源码开发与构建依赖编排 |
| `elfienest.py` | CLI 分发 | 只由 `./elfienest.sh` 和打包启动器调用 |
| `serve.py` | Runtime 入口 | 前台服务和受管生命周期启动 |
| `pre_submit_gate.sh` | 质量入口 | 显式本地 commit/push/full 诊断 checkpoint |
| `check_node_toolchain.sh` | 质量入口 | Node.js 与 pnpm 清单一致性 |
| `check_quality_baseline.py` | 质量入口 | Ruff、format 与 MyPy 基线 |
| `check_quality_environment.py` | 质量入口 | 广覆盖测试的宿主能力预检 |
| `check_release_version.py` | 发布质量入口 | 仓库与包版本一致性 |
| `godot_host_validate.sh` | Godot 质量入口 | 受控宿主 Godot 验证 |
| `godot_species_validation.py` | Runtime/构建模块 | 注入 App 与构建流程的共享物种验证 |
| `release.py` | 发布入口 | 严格原生发布协调 |

`architecture/` 负责架构 Scanner、不可变基础分类、验证规划/复用、契约注册表和仓库
Git hook 安装器；其中的 `AGENTS.md` 定义机器治理规则。

其余根文件属于内部实现，不是稳定用户命令。迁移时不增加兼容壳，而是在同一改动中更新
所有调用方：

| 内部文件 | 分类 |
| --- | --- |
| `internal/bootstrap/report.sh`、`internal/bootstrap/runtime_dependencies.sh` | Bootstrap 辅助 |
| `assemble_desktop_resources.py`、`build_devtools_web.py`、`build_godot_dedicated.py`、`build_godot_web.py`、`package_python_core.py` | 构建辅助 |
| `release_install_smoke.py`、`release_manifest.py`、`release_pipeline.py`、`release_planning.py` | 发布辅助 |
| `chat_with_elfie.py`、`e2e_dashboard_check.py`、`verify_nest_runtime_e2e.py` | 人工诊断 |
| `__init__.py` | 包标记，不是命令 |

新增内部辅助实现进入 `scripts/internal/<category>/`；稳定根路径保持精简明确，不继续堆积
无关实现。

### bootstrap.sh 用法

`bootstrap.sh` 是统一的依赖编排器，支持两种模式：

- `dev`：贡献者模式，包含 Python dev + 前端 + 已导出的 Godot Web Runtime + Electron dev deps
- `build`：源码/安装包构建模式，包含当前原生 target 的发行工具链

Godot 编辑器不是普通启动依赖。只有缺少已导出的 Web Runtime 时，Bootstrap 才会解析
编辑器；它会复用与 `godot_project/project.godot` 所声明主次版本线匹配的任意本机
可执行文件，并且只有明确输入 `y` 后才下载官方构建。

```bash
# 检查依赖状态
./scripts/bootstrap.sh check --tier=dev

# 补齐缺失依赖
./scripts/bootstrap.sh ensure --tier=dev

# 输出 JSON 格式报告（供 CI 使用）
./scripts/bootstrap.sh report --tier=build

# 校验 Node.js/pnpm 声明
bash scripts/check_node_toolchain.sh
```

### release.py 用法

`release.py` 用于打包发布，组装 staging 资源并调用 electron-builder：

```bash
# 在本地构建当前原生 target，不上传或发布
.venv/bin/python scripts/release.py --target darwin-x64

# 请求四 target 协调；不可用 runner 保持 incomplete
.venv/bin/python scripts/release.py
```

要生成完整的多平台安装包，请运行 `.github/workflows/release.yml`：
`workflow_dispatch` 会把四个校验后的安装包保存为 Actions artifacts；推送匹配的
`v<version>` tag 还会把它们发布为 GitHub Release。

正常使用示例：

```bash
./elfienest.sh --help
./elfienest.sh serve
./elfienest.sh build-godot-web --check
./developer.sh build-godot-dedicated --check
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_baseline.py
```

运行全仓 pytest 前先做一次宿主能力预检：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_environment.py
```

退出码 `0` 表示允许回环端口绑定。退出码 `2` 表示当前沙箱或宿主策略拒绝
`127.0.0.1:0`；不要在当前环境启动全量测试，应在允许绑定的环境中把同一条全量命令
只运行一次。退出码 `1` 表示预检本身出现了未预期错误，需要先诊断。

## 人工诊断脚本

下列脚本会启动组件、访问本地服务或进入交互循环，不属于安装后的稳定用户命令：

| 文件 | 用途与注意事项 |
| --- | --- |
| `chat_with_elfie.py` | 启动长时间引擎循环，与第一个已持久化的精灵在终端对话；需要先完成领养和模型运行时，手工退出后清理服务 |
| `e2e_dashboard_check.py` | 用临时目录和随机端口启动已配置模型服务，检查登录、领养与管理面板链路；运行前必须配置模型 |
| `verify_nest_runtime_e2e.py` | 等待一个 Godot Runtime，验证双精灵同步、广播、语义移动和取消终态 |

这些脚本可能耗时、占用端口或产生本地数据，不应作为 import 时执行的模块，也不应
在不知情的情况下指向默认生产数据。可自动化的回归应优先进入 `test/e2e/`。

`verify_nest_runtime_e2e.py` 启动 Python 侧协议 v2 网关；另一个终端需使用脚本
输出的 WebSocket 地址和 nonce 启动 `godot_project/main.tscn`。脚本只使用内存
状态，不读取或写入生产 `ELFIE_HOME`。

## 产物边界

- 所有可再生中间产物写入根目录 `build/`；
- 最终安装包写入根目录 `dist/`；
- 生产数据写入 `ELFIE_HOME`；
- 不把生成的 Godot Web、Desktop JavaScript、Python Core、日志或缓存写回
  `scripts/` 或其他源码目录。

新增脚本时应明确它是稳定入口、构建/质量门还是人工诊断，并同步相应测试与
Developer 文档。
