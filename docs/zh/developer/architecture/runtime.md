# 运行时与数据

## 唯一 Runtime 服务与权威

`app/orchestration/lifecycle/RuntimeSupervisor` 是一个 ElfieNest Runtime
generation 的唯一生命周期所有者。源码与已安装 CLI 的生命周期命令都经过同一边界。
它启动和停止 Python Core 及其 Gateway，再启动选中的已导出 Godot 权威宿主；它不会
打开 Godot Editor。

只有 Core、Gateway 与 Godot 权威都 ready 时 Runtime 才 ready。配置的公共 Ollama
endpoint 作为第四组件被探测：其不可用会使 Runtime 处于 `degraded`，不会替代权威，
也不会创建私有模型 sidecar。`status --json` 会报告封闭组件集（`core`、`gateway`、
`godot_authority`、`ollama`）和生命周期状态。Supervisor 将当前收据写入
`<所选数据根>/runtime.json`。

权威宿主由 `godot_runtime/` 选择，不携带 Nest 状态、场景数据或协议凭据：

| 宿主类型 | 显示模式 | 用途 |
| --- | --- | --- |
| `web_authority` | 图形化 | 已导出的 Godot Web 权威 |
| `electron_authority` | 图形化 | 用于已导出 Web 权威的独立 Electron 权威角色 |
| `linux_dedicated` | 无显示 | Linux x64 已导出的 Dedicated 权威 |

`godot_project/` 仍是可编辑的源工程。Supervisor 承载的是已导出的 Runtime 产物；
Python 与 Desktop UI 都不会把 Godot 源资产当作 Runtime 依赖读取。

## Owner lease 与 Desktop 挂接

完整健康后，Supervisor 会记录含 `owner_id` 与 Runtime generation 的 owner lease。
发现健康 Runtime 的客户端只会挂接并取得 generation，不获得停止权；启动该 generation
的客户端才获得 lease，并且只能停止同一个 lease。这样一个仅观察的 Desktop 窗口不能
停止它没有创建的 Runtime。

Electron Observer 位于 `app/interfaces/desktop/`，不在已移除的顶层 `desktop/` 目录。
它的公开 lifecycle client 调用用户可见的 CLI 命令，绝不导入 Supervisor 内部实现、
Godot Gateway 协议帧或权威凭据。关闭 Observer 窗口没有生命周期副作用；只有客户端
持有 owner lease 时，显式退出应用才会停止 Runtime。

## Observer 权限、相机目录与非视频第一阶段

Observer 从已认证的产品会话开始，获得一个与会话绑定的不透明 capability。订阅范围只能
是一个房间或一只归属自己的 Elfie；interest 只能缩小既有授权结果。帧按
generation/sequence 顺序携带语义身份和状态，不携带场景 transform、几何、相机状态、
原始 Runtime 协议帧或权威凭据。

产品 Observer 的完整、版本化相机目录由 Godot 拥有。每个严格的目录 envelope 都携带
语义 view `id` 与 `label`、`active_id`、正数 `revision` 以及
`presentation_paused`。它描述当前可选择的视角，不导出相机坐标、transform 或房间几何。
React 消费该目录后，只能发出封闭的语义命令 `overview`、`select`、`reset` 与
`set_local_presentation_paused`。`select` 只能使用当前目录中的 ID；React 既不计算，也不
发送相机位置、transform 或布局事实。

产品 bridge 只接受来自当前同源 Godot iframe、且满足严格版本化消息格式的目录。它不暴露
原始 Runtime 帧、权威凭据或模拟控制。local presentation pause 仅是 Observer 的输入/呈现
状态；它绝不能暂停 Runtime、Gateway、Core 或后端模拟。

产品 Observer 也可以接收严格的语义实体快照，用于只读呈现。每个实体只携带身份、物种、外观、
房间/区域状态和语义 `home_anchor_id`，不携带坐标、transform、导航或碰撞事实。Godot 在本地
解析该 anchor，并负责角色放置与渲染。React bridge 只接受并转发经过校验、发往当前同源 Observer
iframe 的快照。

`/monitor` 是 Owner 与 Admin 可访问的完整观察页面。Owner/Admin 的精灵巢管理弹窗嵌入
同一个 `ObservationMonitor` 表面与 bridge，而不是实现另一套相机能力。

封闭的本地导航 intent 是 `request_resync`、`focus_room` 与 `focus_elfie`。唯一会改变
世界的请求是单独授权、限流的高层 `request_interaction`（`greet` 或 `rest`），它经由
应用边界送到 world sink。第一阶段的 Observer 不是相机/视频传输：不发送 JPEG 帧，也
不提供相机流 API。

## Runtime 产物契约

产物清单只接受四个原生 target：`darwin-arm64`、`darwin-x64`、`win32-x64` 与
`linux-x64`。每个 target 都有 `godot-web` Observer 组件和 `desktop-observer` 组件；
只有 `linux-x64` 额外拥有无显示的 `linux-dedicated` 权威组件。清单验证组件模式、入口、
文件哈希与 target 适用范围。这是产物契约，不表示任何具体安装包已构建或已安装。

## 数据目录

| 类型 | 位置 | 是否提交 |
| --- | --- | --- |
| 用户配置、数据库、精灵档案、本地密钥和 Runtime 收据 | 所选产品数据根 | 否 |
| 可再生中间产物 | `build/` | 否 |
| 最终发行物 | `dist/` | 否 |
| 公开文档源 | `docs/` | 是 |

## 生产目录契约

正式安装默认使用 `~/.elfienest`；源码与 worktree 运行默认使用
`<当前worktree>/.elfienest.local`。`--data-home PATH` 与 `ELFIE_HOME` 可以覆盖
默认值，全部生命周期收据与产品数据都跟随唯一所选数据根。

一台电脑只有一个生产 Nest 根 `${ELFIE_HOME:-~/.elfienest}`。`nest.db` 只包含最终
8 张 Nest 级表：用户、会话、本机安装/Setup、Nest 设置、精灵、外部身体、身体审计
和具身租约。聊天与记忆不使用根数据库。

Provider、模型、粮食、工具、凭据、报告和 Runtime 收据的所有权只由
[AI Runtime 设计契约](../contracts/ai-runtime) 定义。完整生产目录树以及
“每项持久化事实只能有一个类型化写入者”的规则也只在该契约中维护，本页不再复制这些
Schema。

```text
${ELFIE_HOME:-~/.elfienest}/
├── nest.db                         # 最终 8 张 Nest 级表
├── configs/                        # Runtime、鉴权和粮食配置
├── reports/                        # 模型证据与验证报告
├── assets/users/<user_id>/         # 头像与隔离的本地文件
├── runtime/                        # runtime.json 与锁
├── logs/                           # Runtime 事件与 Token 用量
└── elfies/
    └── <8位elfie_id>/               # 稳定 ID，不使用可变名称
        ├── profile/profile.yaml
        ├── assets/ godot/ skills/
        ├── conversations/history.sqlite # 最终 7 张聊天表
        └── memory/knowledge.sqlite      # 最终 9 张知识表
```

`history.sqlite` 记录会话、渠道、发送方、用户关系、文本、元数据和附件引用。不会建立
用户视角的本机聊天副本，也不会把附件二进制塞进数据库。网页、桌面、微信或飞书等
渠道都按所属精灵写入这一个工作区。

## 开发与安装路径

只有一条源码开发路径：在 checkout 中运行 `./elfienest.sh`；它会先检查锁定的开发
环境，再进入产品菜单。它不是安装方式。

正式安装方式恰好有三种：面向当前原生 target 的源码安装 `./install.sh`；取得匹配平台
原生安装包后手动安装；以及在公开 endpoint 发布后使用远程校验 bootstrap。第三种当前
没有公开下载命令。这三种方式会收敛到同一产物契约；本页不声称目前存在可用产物。

## 开发边界

Developer Tools 默认使用独立根 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，其下的
`elfie_lab/`、`nest_lab/`、`runtime_lab/` 不得回退读取生产根。测试应同时设置临时
`ELFIE_HOME` 与 `ELFIE_DEV_HOME`。

应用在产生写入前就会拒绝旧数据根和旧 schema。请先备份，再重建所选数据根；不提供
兼容读取、复制、重放、双写或自动迁移。新聊天只能位于对应精灵工作区。

## 内部契约

Pydantic 模型是内部数据结构的唯一事实源。代码需要时可以运行时调用
`model_json_schema()`；仓库不维护第二份 JSON Schema 文件。
