# ElfieNest Developer Tools

> 中文版：本文件 · [English](README.md)

`devtools/` 是与普通用户产品隔离的模块实验台。它们不会作为用户导航或生产
服务入口，也不应依赖普通用户页面才能工作。

## 统一入口

先准备仓库锁定的 Python 环境，再查看可用工具：

```bash
./elfienest.sh version
./developer.sh --help
```

当前有两个交互入口和一个批量入口：

| 工具 | 真实入口 | 本地默认 | 用途 |
| --- | --- | --- | --- |
| Elfie Lab | `./developer.sh elfie-lab` | `127.0.0.1:9001` | 单精灵档案、感知、决策和回合调试 |
| Nest Lab | `./developer.sh nest-lab` | HTTP `127.0.0.1:9002`、Godot WS `127.0.0.1:9003` | 固定房间、临时角色与 Godot Runtime 实验 |
| Brain Eval | `./developer.sh brain-eval` | 无服务端口 | 可复现的 Brain 配对捕获、评价与晋级证据 |

正式 App 使用 HTTP `8000`、Godot WebSocket `8765` 和管理 WebSocket `8766`，与 Lab
默认端口完全分离。直接运行 `./developer.sh elfie-lab` 或 `./developer.sh nest-lab` 时，
启动器会先正常终止**当前工作区的同类默认 Lab**，等待端口释放后再启动并打开新页面；
它不会删除 Lab 数据、不会终止正式 App，也不会终止其他项目或未知程序。若默认端口属于
未知进程，命令会明确报错而不是强杀。

显式 `--port`（Nest Lab 还包括 `--godot-ws-port`）保留并行实验语义，启动器不会回收
旧实例；Nest Lab 的 WebSocket 默认随 HTTP 端口加一，也可单独指定。

## 数据隔离

统一入口默认把 Web 实验台数据放在 `${ELFIE_DEV_HOME:-~/.elfienest-dev}` 下的独立子目录。
为一次实验提供显式临时目录更容易清理：

```bash
./developer.sh elfie-lab --data-dir /tmp/elfienest-elfie-lab --port 9001
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab --port 9002 --godot-ws-port 9003
```

Elfie Lab 会在隔离的 Lab 数据根中保存模型连接和测试粮食。页面的实验配置里可以选择
已安装的本地 Ollama 模型，也可以填写 OpenAI 兼容服务的 URL、Token 和模型。保存会
创建或更新一份测试粮食；Lab 不提前验证连接，第一次真实回合才会实际调用模型。不得把
任何实验数据、密钥或本机配置复制到 Git 跟踪文件。

## 各工具命令

Elfie Lab 和 Nest Lab 是本地 FastAPI 服务，会一直运行到进程退出：

```bash
./developer.sh elfie-lab --host 127.0.0.1 --port 9001
./developer.sh nest-lab --host 127.0.0.1 --port 9002 --godot-ws-port 9003
./developer.sh brain-eval catalog
```

Elfie Lab 和 Nest Lab 启动后都会自动打开网页，并自动复用或更新同一份
`build/components/godot-web/` 导出物：缺失或 Godot 源码变化时才重新导出，未变化时
不会重复编译。macOS 会自动发现标准 Godot 安装位置；只有自动发现失败或多版本并存时，
才需要通过 `--godot` 或 `GODOT_BIN` 指定构建工具。浏览器每次启动使用新的本地运行 URL，
避免旧工作区页面缓存遮住新版界面。床位、临时狐狸/小狗、随机游走、暂停、继续和重置
都只作用于这一次 Lab 进程的内存状态。

两个网页实验台共用 `devtools/web/` 的 React + TypeScript + Vite 源码；启动时会按源码
摘要自动复用或构建 `build/components/devtools-web/`。如需单独检查该产物，可运行：

```bash
./developer.sh build-devtools-web --ensure
```

Brain Eval 是批量工具。它在一次性 Elfie Lab 状态中运行真实 Brain 装配，只把产物写入
`build/brain-eval/<run-id>/`，也不会打开端口。先阅读
[Brain 评价工作流](../docs/zh/developer/engineering/brain-evaluation.md)；只有 Fixture、
事件/故障 Adapter、成功判据和证据路径都存在时，目录中的场景家族才算完成自动化。

## 边界

- 不修改或复用 `app/interfaces/web/static/` 的普通用户页面；
- 不把工具挂到生产启动入口或普通用户导航；
- 不用生产数据库、Owner 会话或默认用户数据做实验；
- 不把 `ElfieNestEngine`、Godot 或产品鉴权变成单模块调试的必要依赖；
- 不允许 Brain Eval 读取生产 `ELFIE_HOME`、写到 `build/brain-eval/` 之外，或让未校准
  Judge 触发自动晋级；
- 对工具行为的测试放在 `test/devtools/` 的镜像路径。
