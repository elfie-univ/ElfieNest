# ElfieNest Developer Tools

`devtools/` 是与普通用户产品隔离的模块实验台。它们不会作为用户导航或生产
服务入口，也不应依赖普通用户页面才能工作。

## 统一入口

先准备仓库锁定的 Python 环境，再查看可用工具：

```bash
./install.sh --env-only
./developer.sh --help
```

当前有三个入口：

| 工具 | 真实入口 | 本地默认 | 用途 |
| --- | --- | --- | --- |
| Elfie Lab | `./developer.sh elfie-lab` | `127.0.0.1:8877` | 单精灵档案、感知、决策和回合调试 |
| Runtime Lab | `./developer.sh runtime-lab <command>` | 命令行，无监听端口 | Provider、模型配置和连接实验 |
| Nest Lab | `./developer.sh nest-lab` | HTTP `127.0.0.1:8890`、Godot WS `127.0.0.1:8891` | 固定房间、临时角色与 Godot Runtime 实验 |

这些端口只是源码中的本地默认值，不是生产协议保证。需要并行运行或避免冲突时，
用 `--port` 显式覆盖；Nest Lab 的 WebSocket 默认随 HTTP 端口加一，也可用
`--godot-ws-port` 单独指定。

## 数据隔离

统一入口默认把 Web 实验台数据放在 `${ELFIE_DEV_HOME:-~/.elfienest-dev}` 下的独立子目录。
为一次实验提供显式临时目录更容易清理：

```bash
./developer.sh elfie-lab --data-dir /tmp/elfienest-elfie-lab --port 8877
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab --port 8890 --godot-ws-port 8891
./developer.sh runtime-lab --config-dir /tmp/elfienest-runtime-lab show
```

Elfie Lab 也会为会话维护独立 Runtime 配置；Runtime Lab 的密钥写入开发配置
目录中权限受限的 `.env`，状态命令不会显示密钥内容。不得把任何实验数据、密钥
或本机配置复制到 Git 跟踪文件。

## 各工具命令

Elfie Lab 和 Nest Lab 是本地 FastAPI 服务，会一直运行到进程退出：

```bash
./developer.sh elfie-lab --host 127.0.0.1 --port 8877
./developer.sh nest-lab --host 127.0.0.1 --port 8890 --godot-ws-port 8891
```

Runtime Lab 提供四个子命令：

```bash
./developer.sh runtime-lab show
./developer.sh runtime-lab configure
./developer.sh runtime-lab test
./developer.sh runtime-lab chat
```

`configure` 可以通过隐藏输入保存开发 API Key；不要把密钥放进命令参数、文档或
shell 历史。`test` 和 `chat` 会真实访问所选模型服务，运行前确认目标与费用。

Elfie Lab 和 Nest Lab 启动后都会自动打开网页，并自动复用或更新同一份
`build/components/godot-web/` 导出物：缺失或 Godot 源码变化时才重新导出，未变化时
不会重复编译。macOS 会自动发现标准 Godot 安装位置；只有自动发现失败或多版本并存时，
才需要通过 `--godot` 或 `GODOT_BIN` 指定构建工具。浏览器每次启动使用新的本地运行 URL，
避免旧工作区页面缓存遮住新版界面。床位、临时狐狸/小狗、随机游走、暂停、继续和重置
都只作用于这一次 Lab 进程的内存状态。

## 边界

- 不修改或复用 `app/interfaces/web/static/` 的普通用户页面；
- 不把工具挂到生产启动入口或普通用户导航；
- 不用生产数据库、Owner 会话或默认用户数据做实验；
- 不把 `ElfieNestEngine`、Godot 或产品鉴权变成单模块调试的必要依赖；
- 对工具行为的测试放在 `test/devtools/` 的镜像路径。
