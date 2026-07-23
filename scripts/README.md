# scripts 目录

`scripts/` 保存仓库级启动、构建、质量检查和人工诊断入口。普通用户与贡献者应
优先使用根目录稳定入口；不要绕过入口脚本自行拼装一套运行环境。

## 稳定入口背后的脚本

| 文件 | 分类 | 说明 |
| --- | --- | --- |
| `elfienest.py` | CLI 分发 | 被 `./elfienest.sh` 调用，分发配置、服务生命周期、Owner、数据库、迁移等命令 |
| `serve.py` | 前台服务 | 启动 FastAPI、引擎和 WebSocket；由 `serve` 或后台生命周期命令调用 |
| `build_godot_web.py` | 构建 | 导出并校验 Godot Web Runtime，正式输出到 `build/components/godot-web/` |
| `check_quality_baseline.py` | 质量门 | 比较 Ruff、Ruff format、MyPy 当前诊断与受控历史基线 |
| `elfienest_install_helpers.sh` | Shell 库 | 供 `install.sh` 校验用户级安装目录和 PATH，不能独立执行 |
| `__init__.py` | 包标记 | 允许架构测试导入脚本中的可测试函数，不是命令入口 |

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
| `e2e_service_check.py` | 在固定本地 WebSocket 端口运行完整通信诊断；先确认端口空闲并使用隔离数据目录 |

这些脚本可能耗时、占用端口或产生本地数据，不应作为 import 时执行的模块，也不应
在不知情的情况下指向默认生产数据。可自动化的回归应优先进入 `test/e2e/`。

## 产物边界

- 所有可再生中间产物写入根目录 `build/`；
- 最终安装包写入根目录 `dist/`；
- 生产数据写入 `ELFIE_HOME`；
- 不把生成的 Godot Web、Desktop JavaScript、Python Core、日志或缓存写回
  `scripts/` 或其他源码目录。

新增脚本时应明确它是稳定入口、构建/质量门还是人工诊断，并同步相应测试与
Developer 文档。
