# Elfie 内部架构契约

**契约版本：** 1.0
**采用日期：** 2026-08-11
**适用范围：** `elfie/`，以及 Infrastructure 为单只 Elfie 限定作用域的 Port View

> **规范性目标。** 本契约定义一只完整 Elfie 的内部所有权、依赖方向、公开 Facade
> 和出站 Port。它细化但不改变已冻结的[系统架构契约](./system)。当前实现尚未完全
> 合规；精确迁移缺口记录在 [Elfie 一致性台账](../conformance/elfie)。

根模块、系统 authority 和技术 Adapter 最终位置仍以系统契约为权威；`elfie/` 内部以
本契约为权威。旧 `ai_runtime/` 已完成退役；当前目标所有者实现的模型、Food 与工具
既有行为仍以对应行为契约为准。

## 目标与明确不做的事

`elfie/` 拥有一只完整、可独立测试的精灵：稳定 Profile、认知、情绪、记忆语义、
Skills、神经系统处理、身体语义、数字通信语义和自身生命周期。内部采用轻量嵌套
Ports/Adapters，使领域行为不依赖 SQLite、用户可变 YAML、Provider SDK、Godot 帧、
设备传输或通信平台协议。

本契约不引入微服务、事件总线、通用依赖注入框架、万能 Repository、每个 helper 一个
Protocol 或第二套 App Orchestration。稳定的 `Elfie` 和 `ElfieFactory` Facade 不需要
复制同形入站 Protocol。

## 聚合形态

一只 Elfie 是一个聚合，也是一个内部生命周期边界；它不是系统 Runtime authority：

```text
Elfie / ElfieFactory Facade
            |
            v
私有 Elfie 认知协调
   |          |             |
   v          v             v
 Brain   NervousSystem   Communication
   |          |             |
   |       BodyPort    CommunicationChannel
   |
   +--> FoodPort / ModelPort / ToolPort
   +--> MemoryStorePort

Profile --> ProfileStorePort
```

根 Facade 协调各子模块。Brain 拥有认知和决策；它不构造或导入具体 Body、Channel、
模型、工具或存储实现。`ElfieCognitiveRuntime` 或其后继者是私有聚合协调，不是 App
Runtime、Infrastructure Adapter 或公开产品 API。

## 内部模块所有权

| 模块 | 拥有 | 不得拥有 |
| --- | --- | --- |
| `elfie/profile/` | 身份、物种、外貌、人格、稳定能力、限制、来源和随源码发布的不可变默认资源 | YAML/文件持久化、用户路径、App 领养或账户规则 |
| `elfie/brain/` | 感知工作区、上下文、评估、认知、决策计划、输出路由、情绪、能量、记忆语义和 Skills | Provider 选择/配置、SDK 请求、具体工具执行或产品工作流 |
| `elfie/brain/memory/` | 记忆节点、关系、编码、检索、巩固和语义存储 Port | SQLite 连接、Schema、路径或持久化 Record |
| `elfie/brain/skills/` | Skill 声明、单只精灵的目录、策略和语义工具请求授权 | Runtime 代理、平台工具、工作区路径或工具执行 |
| `elfie/nervous_system/` | 身体事件规范化、过滤、反射、感知投递和已校验身体意图转换 | 设备传输、Godot 协议、几何或身体注册策略 |
| `elfie/body/` | 身体身份、能力、解剖、命令、传感事件、回执、注册和绑定语义 | Godot/WebSocket/设备传输、凭据、进程所有权或设备产品授权 |
| `elfie/communication/` | 标准 Envelope、准入与投递语义、策略、Inbox/Outbox、Hub 和渠道路由 | 产品会话 authority/历史、账户成员、平台 SDK、凭据或网络传输 |

Skills 属于 Brain，因为它们影响认知并授权某只 Elfie 可以提出哪些语义工具请求。
Skill 只命名语义 `tool_key` 或能力，不包装 Runtime 对象，也不自行执行工具。
随源码发布的 Skill 声明和单只 Elfie 的内存策略不需要持久化 Port。可变 Skill 安装、
修改或单只 Elfie 持久 Skill 状态不在本契约范围内；引入它们必须先有单独获批的契约
决策，不能从 Brain 直接写文件开始。

## 对上的公开入站面

生产调用方只通过 `Elfie` 和 `ElfieFactory` 进入聚合。`elfie/__init__.py` 只导出这些
Facade 和有意稳定的边界类型。App 生产代码不得通过直接访问 `BrainCoordinator`、
`MemorySystem`、`CommunicationHub`、`NervousSystem` 或可变 Registry 来编排聚合。

`Elfie` Facade 提供以下强类型能力组：

- 身份与不可变 Profile/状态投影；
- start、stop、join 和显式推进 Elfie 自身时间；
- 类型化身体感知与通信入站；
- 可用身体的注册、绑定和解绑，以及已授权渠道的注册、连接和断开；
- 获授权 Orchestration 或 Observer 投影需要的类型化回合结果、决策和执行回执。

Facade 不暴露数据库路径、工作区路径、Provider 对象、Godot API、传输帧、SQLite/YAML
Store、可变字典或可变内部子模块。

`ElfieFactory` 是由 Bootstrap 调用的领域聚合 Builder，不是第二个生产 Composition
Root。它从显式强类型依赖或封闭不可变装配记录返回一只已经完整装配、尚未启动的
Elfie。它可以构造 Elfie 自有组件，但不构造技术 Adapter，不解析产品数据根，不接收
`godot_api: Any`，也不让认知在对象已经部分配置或运行后才被补充注入。

## 出站 Port 所有权

Port 定义在使用它的语义所有者旁边。可以用一个精简的 `elfie.ports` 表面为 Bootstrap
重导出，但不得重新定义模型或变成 Service Locator。

| Port | 使用方所有者 | 语义契约 |
| --- | --- | --- |
| `FoodPort` | Brain | 读取当前 Elfie 已授权的有效 Food 投影，保留行为契约规定的命名语义角色、精确不透明模型引用及单 Fallback/Emergency 形状 |
| `ModelPort` | Brain | 使用强类型 deadline、取消和结果元数据完成 Provider 无关的模型生成 |
| `ToolPort` | Brain（Skills 负责授权） | 强制技术安全作用域，执行一个已经由 Brain 授权的语义工具请求，或返回类型化拒绝/有界结果 |
| `MemoryStorePort` | Brain/Memory | 保存和查询类型化记忆节点、边及语义搜索结果 |
| `ProfileStorePort` | Profile | 加载和保存已校验稳定 Profile，不暴露 YAML 或路径 |
| `BodyPort` | Body（由 NervousSystem 与聚合路由使用） | 暴露一具可替换身体的能力、命令、事件、回执和快照 |
| `CommunicationChannel` | Communication | 连接一个渠道并投递标准 Envelope，返回类型化回执 |

每个注入 Port 只暴露一只已授权 Elfie 的作用域。具体 Adapter 可以在多个限定作用域的
Port View 背后共享容器级连接池、Provider Client 或 Godot Gateway；共享技术生命周期
不得暴露跨 Elfie 查询，也不得把清理所有权转给 Elfie。因此 `ToolPort` 接收语义资源
标识而非任意文件系统路径，由其限定作用域的 Adapter 解析已授权 Root；`FoodPort` 不
提供跨 Elfie 通用查询 API。边界模型只使用领域语言，不泄漏 SDK 对象、SQL Row、未
校验字典或协议帧。

## Food、模型与工具认知

Brain 选择语义模型角色，并决定是否允许模型提出的工具调用。`FoodPort` 保留模型、
Food 与工具行为契约规定的精确命名角色、一个可选 Fallback 和 Emergency 行为，不得
发明任意 Fallback 列表；`ModelPort` 解释不透明技术模型引用并完成生成。

Brain Skill 授权是工具执行的必要但非充分条件。`ToolPort` Adapter 还要把请求与全局
可用性及本次调用的技术安全作用域求交，可以返回类型化拒绝，且永远不能扩大 Brain
授权的能力。App 配置可用性，但不代理调用。

普通链路直接完成：

```text
Brain -> FoodPort  -> Infrastructure 持久化 Adapter
Brain -> ModelPort -> Infrastructure 模型 Adapter
Brain -> ToolPort  -> Infrastructure 工具 Adapter
```

App Configuration 管理全局可用性、分配和授权，但不代理运行链路；App Orchestration
不是模型或工具 Gateway。当前宽泛的 `CorticalRuntimePort` 与 `RuntimeSkillAdapter`
属于迁移路径，不是目标所有权。

## Body Port 与多具身体

一只 Elfie 可以注册多具身体。每个身体实例拥有稳定 `BodyId`、能力 revision 和独立
生命周期，并实现同一份 `BodyPort`。具体实例可以是 Godot actor 身体、一具或多具
玩具身体、设备身体，以及 Headless/测试身体。

`BodyRegistry` 拥有可用身体实例，`BodyBinding` 拥有明确的当前路由关系。初始绑定策略
可以在保留多具已注册身体的同时选择一具主要命令身体。命令和事件始终携带 `BodyId`，
因此未来扩展角色化或并发绑定时无需另建技术专用契约。任何多身体并发策略都必须显式
定义，不能根据连接状态自行推断。

Registry 只包含已经由 App Device 用例发现、授权和关联的 Adapter View。连接或健康
状态不能自动授予、关联或绑定身体。不同身体的事件携带稳定事件 ID 和时间，不存在隐式
的跨身体全局顺序。

`BodyPort` 是稳定的聚合边界。身体实现内部确有测试价值时可以使用更窄的 Sensor/
Actuator Protocol，但调用方不获得第二套重复公开身体 API。

身体命令、传感事件、能力和生命周期回执留在 `elfie/body/`。确定性的纯领域参考身体或
测试 Fake 可以留在领域测试中；产品 Headless 托管以及所有 Godot 传输、设备 Session、
蓝牙/LAN、凭据和进程控制属于 Infrastructure。App Device Feature 拥有发现、登记、
授权和 Elfie/body 关联；跨 authority 的托管、身体切换或归巢工作流属于 App
Orchestration。

Body Channel 只承载 Actor 作用域的命令、感知、本体感觉和回执。权威房屋几何、坐标、
碰撞/导航及全局互动事实通过 World Channel 进入 Nest；Orchestration 只把由此产生且已
授权的语义感知交给受影响 Elfie。同一个共享 Godot Gateway 可以支撑两种限定作用域的
View，但 `BodyPort` 永远不能成为绕过 Nest authority 的路径。

## Communication Port 与多渠道

一只 Elfie 可以同时连接多个通信渠道。网页聊天、ElfieNest 独立 App、微信、钉钉、
飞书、Telegram 和未来平台，都各自以一个渠道实例实现同一份
`CommunicationChannel` Port。`CommunicationRouter` 按稳定 `channel_id` 路由，
`CommunicationHub` 拥有校验、去重、策略、Inbox/Outbox 和标准投递语义。

对于外部入站流量，平台 Adapter 先认证并转换原生 Payload；App Communication Feature
再解析账户、会话成员、目标 Elfie 与授权；只有之后才通过 `Elfie` Facade 传入标准
`CommunicationEnvelope`。已经由 App 限定作用域的可信本地渠道可以直接使用同一
Facade。Infrastructure 永不选择 Elfie，也不得绕过产品授权。Facade 本身就是领域入站
边界；没有独立进程或多实现需求时，不为了对称增加 `InboundCommunicationPort`。出站
Envelope 通过已注册 Channel Port 投递，并返回类型化 `DeliveryReceipt`。

每个 Envelope 与回执都携带稳定消息/关联身份及 `channel_id`。去重必须幂等；回复默认
回到来源渠道，除非决策显式选择另一个已授权渠道；并发渠道之间不存在隐式全局总顺序。
平台原生 Sender ID 永远不能直接视为已经认证的 ElfieNest Principal。

产品账户、关系、会话成员和用户可见历史属于 App Communication Feature。
Infrastructure 拥有平台 SDK、凭据、Webhook、网络 Session、传输重试和外部协议映射。
Elfie 只拥有交流与认知语义。Communication Inbox/Outbox 只是有界处理和投递状态，不是
第二份持久产品会话历史，也不是传输重试 authority。Elfie Memory 可以形成自己对互动的
语义记忆，但不能复制或成为 App 会话记录的 authority。

## 神经系统与内部 Adapter

NervousSystem 把 Body 事件转换为 Brain 感知，应用物理限制与反射，并把已校验身体意图
送往当前 Body Port。Communication 把标准 Envelope 和投递回执转换为独立的数字感知流。
身体与数字通信不能折叠成一条通用输入通道。

当两端都是 Elfie 自有语义契约时，Perception Adapter 或 Intent Executor 等内部桥接
可以保留在 Elfie。它们是内部协调，不授权在领域包中嵌入外部技术 Adapter。

## 边界模型、错误与生命周期

公开 Facade 和 Port 使用命名不可变模型。Profile 字段、记忆元数据、工具参数/结果、
身体命令/事件和通信 Envelope 必须逐步移除 `Any`、无约束字典和按角色变化的动态结构。
Pydantic 模型仍是机器可读契约；仓库不维护重复 JSON Schema 文件。

技术失败必须先在 Adapter 边界转换成稳定 Elfie 错误或类型化回执。外部调用明确超时、
取消、重试、幂等和终态回执语义。Bootstrap 构造限定作用域 View、拥有容器对象生命期
并登记清理；只有 `app/orchestration/lifecycle` 决定和协调系统 Runtime 组件的 start、
stop 或 restart。Elfie 只拥有内部聚合 start/stop/join 顺序，并且只有注入的生命周期
契约明确授予单只 Elfie 独占所有权时才能关闭对应 Port；它永不启动或停止 Core、
Gateway、Godot authority 或共享 Adapter 资源。

## 依赖规则

```text
Elfie Facade -> Profile + 私有协调
私有协调 -> Brain + NervousSystem + Body + Communication
Brain -> 自有 Food/Model/Tool/Memory Port
NervousSystem -> Body 语义契约 + Brain 感知 Port
Communication -> 自有 Channel Port + Brain 感知 Port
Profile -> 自有持久化 Port
Infrastructure -> 只依赖它实现的 Elfie Port
```

`elfie/` 永不导入 `app`、`nest`、`ai_runtime`、`godot_runtime`、具体
`infrastructure`、平台 SDK 或产品数据根 resolver。技术 Adapter 包可以反向导入自己
实现的 Elfie Port 与模型，这是依赖倒置。Elfie 子模块之间不得形成 import 环。

## 测试与迁移棘轮

Brain、Memory、NervousSystem、Body 和 Communication 测试使用类型化 Fake 或内存
Port，不依赖 SQLite、用户可变 YAML、网络、Godot 或物理设备。Infrastructure Adapter
做聚焦集成测试，Bootstrap 做装配测试，每一类完成迁移的生产 Body 或 Channel Adapter
至少有一条真实端到端路径。

迁移按仓库治理契约渐进执行。每个切片只修复一条完整边界：冻结所有者和模型，定义使用方
Port，实现并注入 Adapter，迁移全部生产调用方，删除旧实现与兼容路径，然后关闭对应
一致性缺口。现有系统 Baseline 只能缩减；本契约不创建第二份旧架构 Baseline。

建议顺序为：公开 Facade 和边界盘点、Brain Skills、Food/Model/Tool Ports、Memory
持久化、Profile 持久化、Body 技术 Adapter、Communication 平台 Adapter，最后完成
Factory 和公开导出清理。每个切片必须保持可运行，并确保每项事实只有一个活动 authority。

## 明确拒绝的设计

本契约拒绝各子模块任意互相导入的扁平包、一个万能 `ElfiePort`、每个 helper 一个
Protocol、通用 Runtime 代理、Elfie 内的技术 Body/Channel SDK、让 App Orchestration
代理普通认知、多写入者持久化、兼容 Alias、Fallback Read，以及藏在 `ElfieFactory`
中的 Service Locator。
