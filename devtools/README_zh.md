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

当前有三个无参数入口；它们启动同一个 Developer Tools HTTP 服务，只由命令选择首次打开的页面：

| 命令 | 首次打开 | 本地默认 | 用途 |
| --- | --- | --- | --- |
| `./developer.sh elfie-lab` | `/elfie/experiment` | HTTP `127.0.0.1:9001` | 单精灵实验 |
| `./developer.sh brain-eval` | `/elfie/evaluations` | 同上 | 批量评测与报告 |
| `./developer.sh nest-lab` | `/nest/experiment` | 同上（Godot WS 为内部 `9002`） | 精灵巢与 Godot Runtime 实验 |

正式 App 使用 HTTP `8000`、Godot WebSocket `8765` 和管理 WebSocket `8766`，与 Lab
默认端口完全分离。三个命令都会复用同一个 HTTP 服务；启动器会先正常终止**当前工作区的
默认 Developer Tools 实例**，等待端口释放后再启动并打开对应页面；
它不会删除 Lab 数据、不会终止正式 App，也不会终止其他项目或未知程序。若默认端口属于
未知进程，命令会明确报错而不是强杀。

显式 `--port`（Nest Lab 还包括内部 `--godot-ws-port`）仅用于诊断并行实例；默认使用一个
HTTP 端口，Nest 的 WebSocket 默认随 HTTP 端口加一且不作为页面入口。

## 数据隔离

统一入口默认把 Web 实验台数据放在 `${ELFIE_DEV_HOME:-~/.elfienest-dev}` 下的独立子目录。
为一次实验提供显式临时目录更容易清理：

```bash
./developer.sh elfie-lab --data-dir /tmp/elfienest-devtools --port 9001
```

Elfie Lab 会在隔离的 Lab 数据根中保存粮食及其专属模型连接。粮食表单明确分成两种连接方式：
**本机 Ollama** 默认使用 `http://127.0.0.1:11434`，只检测这个明确地址、不扫描端口，也不显示
API Key；高级设置可覆盖本机回环地址和端口。**自定义 OpenAI 兼容接口**填写 API URL，并可选填
API Key，因此也支持不鉴权的私人部署。两种方式都由用户明确填写模型 ID 和各角色模型。模型
冒烟请求失败时会在当前表单显示原因，且不会落盘。编辑粮食时可以修改名称、模型列表和角色
分配，已保存的连接方式、URL 与密钥状态保持只读。不得把任何实验数据、密钥或本机配置复制到
Git 跟踪文件。

Elfie Lab 还提供独立全屏的**批量评测**工作区：全局表格把每次执行保存为一份不可变报告，
配对 A/B 报告放在可展开父行下，单份详情和双份对比都在宽右抽屉中查看。快速检查运行 3 个场景，
标准评测运行 8 个场景；Food 配对会给两个候选克隆同一份冻结精灵快照，报告对比明确区分严格
配对、多变量观察和条件不兼容。这两套预设属于探索评测，不要求 Godot 评测场景。具体使用循环，
以及 Lab 快速反馈与正式晋级证据的边界，见
[Brain 评价工作流](../docs/zh/developer/engineering/brain-evaluation.md#11-在-elfie-lab-做日常版本评测)。

## 三个入口

本地 FastAPI 服务会一直运行到进程退出；日常只需要下面三个无参数命令：

```bash
./developer.sh elfie-lab
./developer.sh brain-eval
./developer.sh nest-lab
```

一个服务提供三个同源稳定地址：
`http://127.0.0.1:9001/elfie/experiment`（单精灵实验）、
`http://127.0.0.1:9001/elfie/evaluations`（批量评测）和
`http://127.0.0.1:9001/nest/experiment`（精灵巢实验）。左侧窄导航在三页之间切换，直接刷新
任一地址会保留当前页面；批量评测内的
报告列表、单份报告和对比报告仍然是同一页面中的列表与右侧抽屉，不额外拆成顶层页面。

三个入口启动后都会自动打开网页，并自动复用或更新同一份
`build/components/godot-web/` 导出物：缺失或 Godot 源码变化时才重新导出，未变化时
不会重复编译。macOS 会自动发现标准 Godot 安装位置；只有自动发现失败或多版本并存时，
才需要通过 `--godot` 或 `GODOT_BIN` 指定构建工具。浏览器每次启动使用新的本地运行 URL，
避免旧工作区页面缓存遮住新版界面。床位、临时狐狸/小狗、随机游走、暂停、继续和重置
都只作用于这一次 Lab 进程的内存状态。

三个页面共用 `devtools/web/` 的 React + TypeScript + Vite 源码；启动时会按源码
摘要自动复用或构建 `build/components/devtools-web/`。如需单独检查该产物，可运行：

```bash
./developer.sh build-devtools-web --ensure
```

Brain Eval 的显式 `catalog`、`capture`、`compare`、`calibrate` 子命令仍用于批量工具链；
不带子命令时只打开上面的批量评测页面。显式动作在一次性 Elfie Lab 状态中运行真实 Brain
装配，只把产物写入
`build/brain-eval/<run-id>/`。先阅读
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
