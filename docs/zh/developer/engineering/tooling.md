# 命令与开发工具

本页记录当前代码提供的稳定 CLI、构建命令和隔离调试入口。命令行为以
`./elfienest.sh --help`、`scripts/elfienest.py` 和对应测试为准。

## 准备锁定环境

ElfieNest 固定使用 CPython 3.9.25，依赖以 `uv.lock` 为准：

```bash
./elfienest.sh
./elfienest.sh version
```

贡献者还需要开发依赖：

```bash
uv sync --locked --extra dev
```

`./install.sh` 不使用 `sudo`，完整安装时会创建当前用户可用的 `elfienest` 与
`uninstall-elfienest` 命令。源码开发也可以始终使用仓库内的
`./elfienest.sh`。

Python `3.9.25` 是产品和开发工具的共同固定运行时。除非负责人明确批准全仓升级，
不得改用系统 `python`/`python3`、其他虚拟环境或 `ELFIENEST_PYTHON` 覆盖入口；
安装、CLI、Developer Tools、测试和 CR 一律经 `uv` 与仓库 `.venv`。环境失效时只需
运行 `./elfienest.sh version`；首次开发运行会自动检查并补齐受控依赖。

### Node.js 与 pnpm 工具链

私有根目录 `package.json` 只锚定 Node.js 20+ 与 pnpm 10.12.1，不持有业务依赖。
Web 前端、桌面宿主、文档站和 Developer Tools 仍各自保留独立的清单与锁文件。
可用下面的命令检查这些工具链声明是否保持一致：

```bash
bash scripts/check_node_toolchain.sh
```

## 预览文档站

运行 VitePress 开发服务器，并自动在浏览器打开本地文档站：

```bash
./developer.sh docs
```

服务器会监听 `docs/` 的变更，并在 Markdown 或站点配置修改后自动刷新页面。使用
`Ctrl-C` 停止。需要改端口时，把 VitePress 参数放在命令后面，例如
`./developer.sh docs --port 4317`。

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
| `data-home inspect` | 只读诊断当前数据根，不修改数据 |
| `data-home recover` | 备份旧版/损坏数据根并创建新环境 |
| `data-home activate --data-home PATH` | 选择另一个新的或可用的数据根供下次启动使用 |
| `owner` | 在本机终端打开 Owner 账户菜单 |
| `db` | 查看数据库信息，或执行 `backup`、`reset` |
| `version` | 显示版本 |
| `build-godot-web` | 构建、增量确保或检查浏览器 3D Runtime |
| `build-godot-dedicated` | 构建或检查无显示的 Linux x64 权威 Runtime |
| `developer` | 进入隔离的 Developer Tools |

前台与后台服务支持经代码确认的参数：

```bash
./elfienest.sh serve
./elfienest.sh serve --port 8001 --godot-ws-port 8768
./elfienest.sh start
```

服务使用已配置的粮食与模型 Provider。Setup 中的公共 Ollama 是可选项，选择后固定为
唯一 endpoint；在聊天或领养验收前必须先配置可用的模型 Provider。`serve --force` 只尝试终止由
当前项目登记、且确认属于该服务的冲突进程；它不是任意端口清理工具。

在源码开发模式下，`serve`、发现服务已停止时执行的 `start`，以及明确执行的
`restart`，只在启动这一刻检查前端源码指纹；发现过期时使用固定版本的 pnpm 重新构建
Web 客户端。发现服务已被验证为正在运行时，`start` 不会重复检查或重启；`stop` 也不会
在服务运行期间监听或重建前端。正式安装模式保持不变。

## 数据与高风险命令

正式安装的产品数据默认位于 `~/.elfienest`；源码与 worktree 运行默认使用
`<当前worktree>/.elfienest.local`。两种模式都按 `--data-home PATH`、
`ELFIE_HOME`、模式默认值的顺序解析。测试、文档核验和实验必须设置临时
`ELFIE_HOME`，避免污染日常数据。

Owner 恢复只在本机终端提供；密码通过隐藏输入填写，不应放进命令参数、环境变量
或 shell 历史。服务密钥从环境变量或被 Git 忽略的本地配置读取，示例文档只能
使用占位符。

```bash
./elfienest.sh owner
./elfienest.sh db
./elfienest.sh db backup
./elfienest.sh data-home inspect --json
```

`data-home recover` 会先把旧版或损坏的数据根保留到带时间戳的旁侧备份目录，再创建符合当前契约的新数据根。它不会删除旧数据，也不会自动迁移旧数据。

`db reset` 会重置本地数据库，执行前必须确认 `ELFIE_HOME` 指向的精确数据目录并
保留备份。命令行不提供旧数据迁移入口；新配置与聊天只使用当前目录契约。

## Godot Web 构建

Godot 源项目当前声明 4.7。构建机必须使用同版本 Godot 和 Web Export Templates：

```bash
GODOT_BIN=/path/to/godot4.7 ./developer.sh build-godot-web
./developer.sh build-godot-web --ensure
./developer.sh build-godot-web --check
GODOT_BIN=/path/to/godot4.7 ./developer.sh build-godot-dedicated
./developer.sh build-godot-dedicated --check
```

正式输出位于 `build/components/godot-web/`，不会提交 Git。具体环境、产物和
打包流程见独立 Godot 源工程内的 `godot_project/WEB_EXPORT.md`。
Dedicated 权威导出是
`build/components/godot-linux-dedicated/ElfieNestRuntime` 下的 Linux x64 可执行文件，
不包含 Web payload，同样不会提交 Git。

源码树中的 `./elfienest.sh serve` 与 `./developer.sh` 默认使用 development 生命周期：
启动前会比较 Godot 源树指纹，缺失或过期时自动执行 `--ensure`；没有变更时不会重复导出。
`ELFIENEST_RUNTIME_MODE=release` 只执行 `--check`，缺少已验证 runtime 会拒绝启动。
导出机必须安装 Godot 4.7 与对应 Web Export Templates；若缺失，服务会明确报告 3D 预览
离线原因，聊天与管理 API 不会伪造“预览正常”。

## Developer Tools

开发实验统一从 `./developer.sh` 进入，不会启动普通用户产品入口：

```bash
./developer.sh --help
./developer.sh elfie-lab --data-dir /tmp/elfienest-elfie-lab
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab
```

- Elfie Lab 默认监听 `127.0.0.1:8877`；
- Nest Lab 默认监听 `127.0.0.1:8890`。

端口只是本地默认值，不是生产保证。在 Elfie Lab 的实验配置面板中配置模型；保存不会
验证连接，第一次真实回合才会发起模型请求。详细边界见 `devtools/README.md`。

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
cd app/interfaces/desktop
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
npx --yes pnpm@10.12.1 test
```

`build/` 只放中间产物，`dist/` 只放最终安装包。不要把生成结果写回源码目录。
