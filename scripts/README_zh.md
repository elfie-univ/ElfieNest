# scripts 目录

> 中文版：本文件 · [English](README.md)

`scripts/` 保存仓库级启动、构建、质量检查和人工诊断入口。普通用户与贡献者应
优先使用根目录稳定入口；不要绕过入口脚本自行拼装一套运行环境。

## 布局与稳定性契约

根目录只暴露五个稳定运行入口：

| 稳定根路径 | 职责 |
| --- | --- |
| `bootstrap.sh` | 准备源码开发与安装包构建依赖 |
| `elfienest.py` | 为 `./elfienest.sh` 分发产品 CLI |
| `serve.py` | 启动前台服务或受管生命周期 |
| `pre_submit_gate.sh` | 显式运行本地 commit、push 或 full checkpoint |
| `release.py` | 协调严格原生发布 |

`README.md`、`README_zh.md` 和 `__init__.py` 是文档/包元数据，不是额外命令。
`python_baseline.py`、`godot_host.sh` 等单项检查统一进入 `quality/checks/`，不再作为
根目录稳定入口。

```text
scripts/
├── bootstrap.sh, elfienest.py, serve.py, pre_submit_gate.sh, release.py
├── governance/                 # 定义哪些改动和依赖是合法的
│   ├── contract_registry.py    # 版本化契约清单
│   ├── change_policy.py        # 基于不可变基础的变更分类
│   ├── boundaries/             # App、系统、结构和有效依赖边界
│   └── persistence/            # 数据库变更盘点与策略扫描
├── quality/                    # 执行质量策略选中的检查
│   ├── checks/                 # 独立 Python、Node、环境与 Godot 检查
│   ├── validation/             # 检查规划、门禁、候选证据、缓存与可复用测试包
│   └── hooks/                  # 仓库托管的 Git hook 安装与运行文件
└── internal/                   # 稳定入口背后的可替换辅助实现
    ├── bootstrap/              # Bootstrap 报告与依赖解析
    ├── build/                  # 中间构建组装
    ├── release/                # 发布规划、清单和烟雾检查
    └── diagnostics/            # 人工与交互式诊断
```

`governance/` 是策略层，描述所有权、依赖方向和契约边界；`quality/` 是执行层，运行具体
检查并组合证据；`internal/` 不表示秘密或安全隔离，只表示路径不是公开命令契约的仓库内部
辅助代码。有稳定根入口时应使用稳定入口；只有聚焦诊断或文档明确要求的 CI/开发流程才
直接调用单项检查。

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
bash scripts/quality/checks/node_toolchain.sh
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
./developer.sh build-godot-web --check
./developer.sh build-godot-dedicated --check
uv run --no-sync python scripts/quality/checks/python_baseline.py
```

运行全仓 pytest 前先做一次宿主能力预检：

```bash
uv run --no-sync python scripts/quality/checks/environment.py
```

退出码 `0` 表示允许回环端口绑定。退出码 `2` 表示当前沙箱或宿主策略拒绝
`127.0.0.1:0`；不要在当前环境启动全量测试，应在允许绑定的环境中把同一条全量命令
只运行一次。退出码 `1` 表示预检本身出现了未预期错误，需要先诊断。

## 人工诊断脚本

下列脚本会启动组件、访问本地服务或进入交互循环，不属于安装后的稳定用户命令：

| 文件 | 用途与注意事项 |
| --- | --- |
| `internal/diagnostics/chat_with_elfie.py` | 启动长时间引擎循环，与第一个已持久化的精灵在终端对话；需要先完成领养和模型运行时，手工退出后清理服务 |
| `internal/diagnostics/e2e_dashboard_check.py` | 用临时目录和随机端口启动已配置模型服务，检查登录、领养与管理面板链路；运行前必须配置模型 |
| `internal/diagnostics/verify_nest_runtime_e2e.py` | 等待一个 Godot Runtime，验证双精灵同步、广播、语义移动和取消终态 |

这些脚本可能耗时、占用端口或产生本地数据，不应作为 import 时执行的模块，也不应
在不知情的情况下指向默认生产数据。可自动化的回归应优先进入 `test/e2e/`。

`internal/diagnostics/verify_nest_runtime_e2e.py` 启动 Python 侧协议 v2 网关；另一个终端需使用脚本
输出的 WebSocket 地址和 nonce 启动 `godot_project/main.tscn`。脚本只使用内存
状态，不读取或写入生产 `ELFIE_HOME`。

## 产物边界

- 所有可再生中间产物写入根目录 `build/`；
- 最终安装包写入根目录 `dist/`；
- 生产数据写入 `ELFIE_HOME`；
- 不把生成的 Godot Web、Desktop JavaScript、Python Core、日志或缓存写回
  `scripts/` 或其他源码目录。

新增脚本时，策略进入 `governance/`，可执行检查进入 `quality/`，辅助实现进入
`internal/`。新增根目录稳定入口属于脚本布局契约变化，必须同步治理审阅、测试和
Developer 文档。
