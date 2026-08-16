# scripts 目录

> 中文版：本文件 · [English](README.md)

`scripts/` 保存仓库级启动、构建、质量检查和人工诊断入口。普通用户与贡献者应
优先使用根目录稳定入口；不要绕过入口脚本自行拼装一套运行环境。

## 稳定入口背后的脚本

| 文件 | 分类 | 说明 |
| --- | --- | --- |
| `bootstrap.sh` | 依赖编排 | 统一准备源码开发/构建依赖（Python、Node、前端、Godot Web、Electron） |
| `elfienest.py` | CLI 分发 | 被 `./elfienest.sh` 调用，分发配置、服务生命周期、Owner、数据库、迁移等命令 |
| `serve.py` | 前台服务 | 启动 FastAPI、引擎和 WebSocket；由 `serve` 或后台生命周期命令调用 |
| `build_godot_web.py` | 构建 | 导出并校验 Godot Web Runtime，正式输出到 `build/components/godot-web/` |
| `release.py` | 发布构建 | 组装 staging 资源并调用 electron-builder |
| `check_quality_baseline.py` | 质量门 | 比较 Ruff、Ruff format、MyPy 当前诊断与受控历史基线 |
| `check_quality_environment.py` | 质量预检 | 在昂贵的全量门禁前检查全仓测试所需的宿主能力 |
| `check_task_closure.py` | 完成门禁 | 校验任务完成矩阵、改动归属、证据和列出的 Conformance 收口 |
| `check_node_toolchain.sh` | 质量门 | 校验根目录 Node.js/pnpm 锚点与所有独立 Node 项目的清单 |
| `architecture/app_layer_scan.py` | 架构门禁 | 对 App 层精确旧债做棘轮约束，基线删除后切换为 deny-all |
| `architecture/system_layer_scan.py` | 架构门禁 | 对 Elfie/Nest 系统边界精确旧债做棘轮约束，基线删除后切换为 deny-all |
| `architecture/check_governance_change.py` | 架构门禁 | 分离治理与生产变更，并要求契约中英文同步、升级版本且配套 ADR |
| `architecture/contract_registry.py` | 架构注册表 | 关联契约、中英文镜像、ADR、Agent 规约、Scanner、测试、台账与基线 |
| `__init__.py` | 包标记 | 允许架构测试导入脚本中的可测试函数，不是命令入口 |

### bootstrap.sh 用法

`bootstrap.sh` 是统一的依赖编排器，支持两种模式：

- `dev`：贡献者模式，包含 Python dev + 前端 + Godot 编辑器/Web 导出 + Electron dev deps
- `build`：源码/安装包构建模式，包含当前原生 target 的发行工具链

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
