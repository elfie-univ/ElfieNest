# 开发流程

本页给出从准备环境到完成本地验证的标准开发路径。具体 CLI、Godot 和 Desktop
命令放在[命令与开发工具](./tooling.md)，协作政策以
[贡献指南](https://github.com/elfie-univ/ElfieNest/blob/main/CONTRIBUTING.md)为准。

## 准备锁定环境

项目固定使用 CPython `3.9.25`，依赖以 `uv.lock` 为准：

```bash
./install.sh --env-only
uv sync --locked --extra dev
uv lock --check
```

不要另写一套 `pip install` 流程，也不要修改锁文件来绕过本地环境问题。安装器
只支持用户级安装，不要使用 `root` 或 `sudo`。

除非负责人明确批准一次全仓升级，CPython `3.9.25` 是不可变契约：不得因为本机
默认解释器、单个依赖或局部功能修改版本文件、锁文件、CI 或启动脚本。所有 Agent、
开发者和自动化只能使用 `uv` 与仓库 `.venv/bin/python3`；不要调用系统
`python`/`python3`、其他虚拟环境或 `ELFIENEST_PYTHON` 覆盖。环境不正确时运行
`./install.sh --env-only`，再使用 `uv run --no-sync` 执行已锁定的命令。

## 选择测试层级

测试目录镜像源码边界。先运行离改动最近的测试，再扩大验证范围：

```bash
# 示例：只修改认知协调器
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/elfie/brain/test_coordinator.py

# 所有跨模块或目录边界改动都要运行
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/

# 需要完整回归时
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/
```

`test/architecture/` 防止旧顶层包、非法反向依赖、根级测试文件和工程配置回退。
更完整的目录与 marker 说明见
[测试 README](https://github.com/elfie-univ/ElfieNest/blob/main/test/README.md)。

## 运行质量门

当前仓库有一批被哈希记录的历史 Ruff 与 MyPy 诊断。统一质量门允许历史集合继续
存在，但会阻止任何新增诊断：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_baseline.py

PRE_COMMIT_HOME=/tmp/elfienest-precommit \
  uv run --no-sync pre-commit run --all-files
```

pre-commit 与 CI 还会运行 Gitleaks。不要用 `--no-verify` 绕过密钥检查，也不要为
新问题更新质量基线；应直接修复本次引入的诊断。

## 调试单个模块

三个实验台都与普通用户产品隔离：

```bash
./developer.sh elfie-lab \
  --data-dir /tmp/elfienest-elfie-lab --port 9001

./developer.sh nest-lab \
  --data-dir /tmp/elfienest-nest-lab --port 9002

./developer.sh runtime-lab \
  --config-dir /tmp/elfienest-runtime-lab show
```

- Elfie Lab 检查单精灵档案、感知、决策与回合；
- Nest Lab 启动隔离 Nest、独立的 Godot v2 网关和可选的浏览器房间预览；它不启动
  `ElfieNestEngine`，也不读取生产数据；
- Runtime Lab 检查 Provider、模型配置和连接，不监听端口。

默认端口只是本地开发值。不要把实验台接入普通用户导航，也不要让它们使用默认
生产数据。正式 App 使用 `8000` / `8765` / `8766`，Elfie Lab 使用 `9001`，Nest Lab
使用 `9002` / `9003`。默认启动同一 Lab 会安全重启当前工作区的旧实例；显式端口用于并行
实验，不会终止既有实例。详细边界见
[Devtools README](https://github.com/elfie-univ/ElfieNest/blob/main/devtools/README.md)。

## 产品 Web 与局域网模式

Core 提供四个同源页面：本机首启的 `/setup`，以及 `/login`、`/chat` 与 `/manage`。
首次 Owner 只能经本机或 Electron 回环服务创建；完成后，同网段设备直接进入登录页。
普通用户固定进入聊天页，`/manage` 在服务端重定向到 `/chat`。Owner 默认进入管理页，
并可将自己的默认页改为聊天页。

聊天页通过同源 `/api/v1/ws/chat` 使用与 REST 相同的会话认证。用户消息会获得实时确认；
运行时产生的精灵回复先写入聊天历史，再桥接给该精灵所属用户的同源聊天连接，因此刷新后
历史与实时消息保持一致。

`/manage` 是唯一的 Owner 管理页，按状态监控、业务管理、模型订阅和系统配置分组，包含
用户、全局精灵只读筛选、精灵巢床位、模型订阅与验证、粮食策略、工具权限和系统设置。
运行事件摘要归入状态监控，模型列表归入模型订阅；Godot 实时预览从精灵巢摄像头进入，
不再分别提供运行日志、模型目录或 Godot 配置入口。聊天、领养和个人精灵私有
资料只属于 `/chat`；管理页没有用户—精灵归属分配入口。

前端源码位于 `app/interfaces/web/frontend/`，构建产物只能写入根目录 `build/web/`：

```bash
cd app/interfaces/web/frontend
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm build
```

开发启动默认只监听 loopback；需要给同网段设备提供登录页时，显式使用 `--lan`。
LAN 不会放宽账户、角色、CSRF、Host/Origin 或设备凭证检查。安装后的 CLI 可用
`--loopback` 关闭家庭 LAN 服务。设备只使用 `/api/v1/ws/devices` 的 Bearer 凭证，
浏览器用户始终使用会话 Cookie。

`/api/v1/ws/devices` 不接受自由格式 JSON：每个文本帧最大 64 KiB，并且只能是
`heartbeat`、`sensor_event`、`receipt` 或 `command_poll`。其中传感器事件和动作回执
直接复用 `elfie.body.contracts` 的类型契约；Core 通过 `DeviceGatewayTransport` 将动作
排入已连接设备的下一次 `command_poll`。设备凭证只在登记或轮换时显示一次，不能写入
浏览器日志、测试夹具或版本库。

当前阶段的产品验收聚焦 `/setup`、`/login`、`/chat`、`/manage`、Electron 登录入口和移动浏览器。
设备—具身 lease—能力声明的 Owner 配置、设备节流策略以及真实安装包 staging/双客户端
自动化仍保留二期；产品旧单页控制台已经退役。

## 提交前检查

准备交付一组改动前，至少确认：

1. 改动直接对应的测试通过；
2. `test/architecture/` 通过；
3. 统一质量门和 pre-commit 通过；
4. 改动文档时，VitePress 能完整构建；
5. 没有真实密钥、本机绝对路径、缓存或构建产物；
6. README、架构文档与测试在新增目录或跨边界依赖后保持同步。

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

PR 的范围、测试证据和审阅要求见
[贡献指南](https://github.com/elfie-univ/ElfieNest/blob/main/CONTRIBUTING.md)与
[PR 模板](https://github.com/elfie-univ/ElfieNest/blob/main/.github/pull_request_template.md)。

## 常见问题

### uv 或 Ruff 缓存不可写

把缓存放入临时目录，不要删除仓库或用户数据：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/
```

### 测试读取了日常数据

立即停止测试，并给它设置独立的 `ELFIE_HOME` 或 pytest `tmp_path`。测试、文档
验收和实验台都不应默认读取 `~/.elfienest/`。

### Godot 打不开或版本不一致

先不要打开可编辑项目。阅读
[Godot README](https://github.com/elfie-univ/ElfieNest/blob/main/godot_project/README.md)，
核对现有 Godot 进程、项目声明版本和 Export Templates，再按公开操作门执行。

### 质量门报告历史问题

先区分 `existing`、`resolved` 和 `new`。只有 `new` 会阻断本次改动；不要通过
写入新基线把它隐藏起来。
