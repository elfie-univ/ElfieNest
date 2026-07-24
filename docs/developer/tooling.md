# 命令与开发工具

本页记录当前代码提供的稳定 CLI、构建命令和隔离调试入口。命令行为以
`./elfienest.sh --help`、`scripts/elfienest.py` 和对应测试为准。

## 准备锁定环境

ElfieNest 固定使用 CPython 3.9.25，依赖以 `uv.lock` 为准：

```bash
./install.sh --env-only
./elfienest.sh version
```

贡献者还需要开发依赖：

```bash
uv sync --locked --extra dev
```

`./install.sh` 不使用 `sudo`，完整安装时会创建当前用户可用的 `elfienest` 与
`uninstall-elfienest` 命令。源码开发也可以始终使用仓库内的
`./elfienest.sh`。

## CLI 入口

直接运行 `./elfienest.sh` 会进入交互模式；脚本化调用应提供明确子命令：

| 命令 | 当前用途 |
| --- | --- |
| `serve` | 开发/诊断模式前台运行服务并显示日志 |
| `start` | 后台启动服务，已运行时不重复启动 |
| `status` | 查看登记服务与端口状态 |
| `stop` | 停止当前项目登记的服务 |
| `restart` | 停止并重新启动当前服务 |
| `web` | 确保服务可用并打开 Web 管理台 |
| `config` | 打开方向键配置中心 |
| `setup` | 运行首次设置向导 |
| `doctor` | 检查本地环境和配置 |
| `owner` | 在本机终端打开 Owner 账户菜单 |
| `db` | 查看数据库信息，或执行 `backup`、`reset` |
| `migrate` | 显式迁移旧配置和数据 |
| `version` | 显示版本 |
| `build-godot-web` | 构建或检查浏览器 3D Runtime |
| `developer` | 进入隔离的 Developer Tools |

前台与后台服务支持经代码确认的参数：

```bash
./elfienest.sh serve --fallback
./elfienest.sh serve --port 8001 --ws-port 8767 --godot-ws-port 8768
./elfienest.sh start --fallback --no-seed-elfie
```

`--fallback` 使用内置模拟运行时，不连接 Ollama。`serve --force` 只尝试终止由
当前项目登记、且确认属于该服务的冲突进程；它不是任意端口清理工具。

## 数据与高风险命令

默认产品数据位于 `${ELFIE_HOME:-~/.elfienest}`。测试、文档核验和实验必须
设置临时 `ELFIE_HOME`，避免污染日常数据。

Owner 恢复只在本机终端提供；密码通过隐藏输入填写，不应放进命令参数、环境变量
或 shell 历史。服务密钥从环境变量或被 Git 忽略的本地配置读取，示例文档只能
使用占位符。

```bash
./elfienest.sh owner
./elfienest.sh db
./elfienest.sh db backup
```

`db reset` 会重置本地数据库，执行前必须确认 `ELFIE_HOME` 指向的精确数据目录并
保留备份。`migrate` 会改变旧配置或数据，只应在确认迁移来源后运行。

## Godot Web 构建

Godot 源项目当前声明 4.7。构建机必须使用同版本 Godot 和 Web Export Templates：

```bash
GODOT_BIN=/path/to/godot4.7 ./developer.sh build-godot-web
./developer.sh build-godot-web --check
```

正式输出位于 `build/components/godot-web/`，不会提交 Git。具体环境、产物和
打包流程见独立 Godot 源工程内的 `godot_project/WEB_EXPORT.md`。

## Developer Tools

开发实验统一从 `./developer.sh` 进入，不会启动普通用户产品入口：

```bash
./developer.sh --help
./developer.sh elfie-lab --data-dir /tmp/elfienest-elfie-lab
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab
./developer.sh runtime-lab --config-dir /tmp/elfienest-runtime-lab show
```

- Elfie Lab 默认监听 `127.0.0.1:8877`；
- Nest Lab 默认监听 `127.0.0.1:8890`；
- Runtime Lab 是命令行工具，没有监听端口。

端口只是本地默认值，不是生产保证。`runtime-lab test` 和 `runtime-lab chat`
会真实请求模型服务；运行前确认 Provider、模型、网络与费用。详细边界见
`devtools/README.md`。

## 质量检查与测试

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_baseline.py
PRE_COMMIT_HOME=/tmp/elfienest-precommit \
  uv run --no-sync pre-commit run --all-files
```

文档站本地构建：

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

Desktop 使用 Node.js 20 与独立锁文件：

```bash
cd desktop
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
npx --yes pnpm@10.12.1 test
```

`build/` 只放中间产物，`dist/` 只放最终安装包。不要把生成结果写回源码目录。
