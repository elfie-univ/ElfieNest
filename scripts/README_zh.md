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
| `elfienest_install_helpers.sh` | Shell 库 | 供 `install.sh` 校验用户级安装目录和 PATH，不能独立执行 |
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
```

### release.py 用法

`release.py` 用于打包发布，组装 staging 资源并调用 electron-builder：

```bash
# 在本地构建当前原生 target，不上传或发布
.venv/bin/python scripts/release.py --target darwin-x64

# 请求四 target 协调；不可用 runner 保持 incomplete
.venv/bin/python scripts/release.py
```

正常使用示例：

```bash
./elfienest.sh --help
./elfienest.sh serve --fallback
./elfienest.sh build-godot-web --check
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_baseline.py
```

## 人工诊断脚本

下列脚本会启动组件、访问本地服务或进入交互循环，不属于安装后的稳定用户命令：

| 文件 | 用途与注意事项 |
| --- | --- |
| `chat_with_elfie.py` | 启动长时间引擎循环并在终端对话；需要模型运行时，手工退出后清理服务 |
| `e2e_dashboard_check.py` | 用临时目录和随机端口启动 fallback 服务，检查登录、领养与管理面板链路 |
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
