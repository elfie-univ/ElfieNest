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

源码开发使用仓库内的 `./elfienest.sh`。最终用户安装平台原生应用包，不从源码
checkout 执行安装命令。原生安装器还会把包内管理 CLI 暴露为全局 `elfienest` 命令；
它复用已安装的 Desktop Controller 和生产数据目录，但不会打开 Viewer。

两套 CLI 的命令面是有意区分的：源码开发入口 `./elfienest.sh` 不注册
`desktop` 命令；安装后的管理 CLI 因为能够激活打包的 Desktop Controller，才提供
`desktop`。`serve` 仍然是源码开发模式的前台入口。

Python `3.9.25` 是产品和开发工具的共同固定运行时。除非负责人明确批准全仓升级，
不得改用系统 `python`/`python3`、其他虚拟环境或 `ELFIENEST_PYTHON` 覆盖入口；
源码 CLI、Developer Tools、测试和 CR 一律经 `uv` 与仓库 `.venv`。环境失效时只需
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
| `web` | 为已经运行的服务打开 Web 管理台 |
| `mobile` | 显示当前无线网络和移动端二维码访问信息 |
| `config` | 打开方向键配置中心 |
| `doctor` | 检查本地环境和配置 |
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

安装后的全局 CLI 刻意不提供 `serve`；它的 `start`、`restart`、`stop` 只操作唯一的
安装版 Controller 和固定产品数据根，也不接受源码 CLI 的 `--data-home`、`--port`、
`--godot-ws-port` 参数。

后台 `start` 成功后，CLI 会打印本机 Web 管理台地址。`web` 只打开已经运行的 Web
管理台；`mobile` 才会按两步显示：第一步是当前无线网络，第二步是指向局域网地址的二维码。

服务使用已配置的粮食与模型 Provider。Setup 中的公共 Ollama 是可选项，选择后固定为
唯一 endpoint；在聊天或领养验收前必须先配置可用的模型 Provider。

源码生命周期参数保持最小范围：`serve`、`start`、`restart` 支持
`--data-home`、`--port`、`--godot-ws-port`；`stop` 只支持 `--data-home`。安装版使用
Controller 自动分配端口，不提供这些源码专用参数。

在源码开发模式下，`serve`、发现服务已停止时执行的 `start`，以及明确执行的
`restart`，只在启动这一刻检查前端源码指纹；发现过期时使用固定版本的 pnpm 重新构建
Web 客户端。发现服务已被验证为正在运行时，`start` 不会重复检查或重启；`stop` 也不会
在服务运行期间监听或重建前端。正式安装模式保持不变。

## 数据与高风险命令

安装版入口只使用 `${ELFIE_HOME:-~/.elfienest}`。源码 CLI 选择任务时忽略调用方
`ELFIE_HOME`，且只有源码 `start`、`serve`、`restart`、`stop` 接受 `--data-home`；
其余源码命令使用内存中的交互会话目标、当前 worktree 下可用于该命令的
`.elfienest.local`，或重新校验后的候选选择。不存在持久化的活动数据目录命令。测试、
文档核验和实验仍须使用隔离环境/数据根，避免污染日常数据。

Owner 恢复只在本机终端提供；密码通过隐藏输入填写，不应放进命令参数、环境变量
或 shell 历史。服务密钥从环境变量或被 Git 忽略的本地配置读取，示例文档只能
使用占位符。

```bash
./elfienest.sh owner
./elfienest.sh db
./elfienest.sh db backup
```

`db reset` 会重置本地数据库，执行前必须确认 `ELFIE_HOME` 指向的精确数据目录并
保留备份。命令行不提供旧数据迁移入口；新配置与聊天只使用当前目录契约。

## Godot Web 构建

Godot 源项目唯一的兼容版本声明是 `godot_project/project.godot` 中
`config/features` 的第一项。构建机必须使用相同主次版本线的 Godot 和对应
Web Export Templates：

```bash
GODOT_BIN=/path/to/godot ./developer.sh build-godot-web
./developer.sh build-godot-web --ensure
./developer.sh build-godot-web --check
GODOT_BIN=/path/to/godot ./developer.sh build-godot-dedicated
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
导出机必须安装项目所声明兼容版本线的 Godot 与对应 Web Export Templates；若缺失，
服务会明确报告 3D 预览离线原因，聊天与管理 API 不会伪造“预览正常”。

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
  uv run --no-sync pre-commit run gitleaks --all-files
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
