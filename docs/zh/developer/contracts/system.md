# 系统架构契约

**契约版本：** 1.4
**采用日期：** 2026-08-10
**适用范围：** 全仓目标架构
**宏观架构基线：** v1（已冻结）

> **规范性目标。** 本契约定义 ElfieNest 最终的模块所有权、依赖方向和系统级
> Ports/Adapters，是根模块迁移的权威。它不表示当前目录已经合规；精确偏差记录在
> [系统架构一致性台账](../conformance/system)。

系统契约管理根目录位置和跨模块边界；应用契约管理 `app/` 内部行为。模型、Food 与
工具行为契约只作为当前迁移包的行为清单，不定义目标模块，也不能反转本契约。子契约若
写的是历史所有者或路径，目标以本契约为准，过渡状态进入一致性台账。

## 目标系统形态

ElfieNest 最终收敛到四个顶级 Python 生产代码所有权模块：

```text
app/                 产品入口、用例、编排和组合根
elfie/               一只完整精灵的领域核心
nest/                精灵巢世界语义的领域核心
infrastructure/      外部系统、持久化与平台 Adapter
```

一套运行中的 ElfieNest 永远只有一个精灵巢。

`elfie/` 和 `nest/` 是中间核心领域层；`app/` 位于其上，把用户或运维意图转成产品
用例；`infrastructure/` 位于其下，通过强类型 Port 实现模型访问、工具执行、Godot
接入、持久化、设备、外部通信、文件、网络、进程和操作系统能力。

`godot_project/` 永久保持为独立 Godot 源工程和运行时 authority。它不是第五个
Python 所有权模块，也绝不移动到 `infrastructure/` 下。Python 侧宿主、协议和 Adapter
属于 Infrastructure；Godot 资产、物理、导航、碰撞和渲染留在 `godot_project/`。

目标 Infrastructure 必须按能力分区，不能成为无所有权的杂物目录：

```text
infrastructure/
├── models/           Provider 发现、验证和模型调用 Adapter
├── tools/            搜索、工作区文件和沙箱执行 Adapter
├── godot/            Gateway、authority 宿主、产物与协议 Adapter
├── persistence/      数据库与持久文件 Adapter
├── devices/          外部身体与设备传输
├── communication/    外部通信渠道 Adapter
└── platform/         文件、时钟、进程和操作系统 Adapter
```

Infrastructure Adapter 可以具有复杂内部实现，例如协议状态、连接池、重试、超时、
进程控制、沙箱和技术验证；但它们不拥有 Elfie 认知、Nest 规则、产品授权或管理员
工作流。

Infrastructure 各能力包不得导入或构造其他能力包的具体 Adapter。一个能力需要另一
能力时，只能依赖窄 Port 或共享技术模型，由 Bootstrap 提供具体实现。

原 `ai_runtime/`、`godot_runtime/` 和 `app/infrastructure/` 根已退役；其技术职责已
归入现有目标 Infrastructure 能力目录，没有创建 `infrastructure/ai_runtime/`。
`elfie/`、`nest/` 内仍存在的具体技术代码属于迁移期路径，只能通过后续单独批准的
迁移切片收缩。

## 系统依赖方向

```text
App Interface / Use-case / Orchestration
          |                         |
          | 入站 Facade             | App 自有出站 Port
          v                         v
   Elfie Core + Nest Core -----> Infrastructure Adapter
          |                         |
          | Core 自有 Port          v
          +-----------------> 数据库、模型、Godot、
                               设备、渠道和 OS
```

左侧是进入 Elfie/Nest Facade 的产品调用或跨 authority 调用；右侧是 App Feature 或
Orchestration 自己需要的账户持久化、时钟、Secret Store、外部工作流等能力。不能为了
让分层图看起来整齐，强迫这些 App 能力绕经 Elfie 或 Nest。

源码依赖遵守依赖倒置：

```text
app              -> Elfie/Nest 公开 Facade 与边界模型
infrastructure   -> 它实现的 App/Elfie/Nest Port
app/bootstrap    -> 仅为装配导入全部具体构造对象
elfie            -X-> app、nest 或具体 infrastructure
nest             -X-> app、elfie 或具体 infrastructure
```

上述方向同时约束静态 import 和有效依赖。通过模块名、可执行脚本、subprocess、子进程、
Shell 命令或动态加载器启动仓库模块，会形成一条从调用方所有者到目标所有者的依赖边。
把禁止模块名从 import 移到命令字符串中，不能改变或隐藏这条边。Developer Tools 可以
为了隔离实验依赖产品公开边界，但生产根目录和产品入口脚本永远不得以 `devtools/` 为
运行目标。

运行时允许 Core 通过注入的 Port 调用 Adapter，但这不授权 Core 导入、创建、配置或
检查具体 Adapter。

`elfie/` 与 `nest/` 永不互相 import。`app/orchestration/` 只拥有组合真实 Elfie
对象与 Nest 状态，或跨两个以上 authority 的工作流。单只精灵通过注入 Port 读取
Food、调用模型、读取文件或执行工具，不属于 Orchestration。

## 入站 Facade 与显式 Port

稳定、强类型的公开 Facade 本身就可以承担入站 Port。`Elfie`、`ElfieFactory` 和
`Nest` 不需要为了名称对称再复制 `ElfieInboundPort` 或 `NestInboundPort` Protocol。

只有存在真实需求时才增加显式入站 Protocol：多个实现、独立版本、进程边界、Facade
无法提供的调用方隔离，或边界测试替身需要复用。模块重要并不是复制 Facade 的理由。

入站和出站 Port 不成对；一个 Core 按真实提供的用例和所需外部能力，拥有任意数量的
两类 Port。

## 系统级出站 Port

系统级 Port 只表达语义能力，禁止暴露具体技术产品名、传输帧、数据库 Row、路径或
SDK 对象。

### Elfie

Elfie 保留 Profile、认知、情绪、记忆语义、Skills、通信语义、身体契约和生命周期。
它需要的系统级能力包括：

- 通过窄 `FoodPort` 读取当前有效模型套餐；
- 通过窄 `ModelPort` 请求模型生成；
- 通过窄 `ToolPort` 执行已批准工具；
- 通过 `BodyPort` 和窄 actor-body 传输契约获得可替换的身体执行与感知；
- 通过强类型 channel 契约连接外部通信渠道；
- 通过语义存储契约保存私有 Profile 和 Memory 事实。

Infrastructure 持久化实现 `FoodPort`，模型 Adapter 实现 `ModelPort`，工具 Adapter
实现 `ToolPort`；Bootstrap 把它们直接注入 Elfie。Elfie 不 import App 或
Infrastructure，也不自行执行 SQL。记忆算法、语义模型角色选择、Skill 声明与
allow-list、身体命令和感知模型仍属于 Elfie。

### Nest

Nest 保留居民、住处、世界语义、环境时间、互动传播，以及说话听众、触觉后果等规则。
它需要的能力包括：

- 通过 Nest 自有 Repository Port 持久化语义状态；
- 通过窄世界契约完成 authority 配置、同步与世界事件输入。

具体 SQLite、WebSocket、JSON 传输、Godot Bundle、环境变量和进程实现属于
Infrastructure。Nest 语义模型和规则仍属于 Nest。

### App

App Feature 可以为产品持久化、文件、时钟、Scheduler、Secret、平台探测和外部工作流
定义自己的出站 Port，由 Infrastructure 实现。App 内部 Ports/Adapters 是系统架构的
嵌套实例，具体规则见[应用架构契约](./application)。

## 权威事实与写入者

架构所有权不只是目录位置。每个持久或运行事实都有唯一语义 authority、唯一写入链路
和明确读者：

| 事实或决策 | 语义 authority | 具体写入或执行者 | 允许的读者或协调者 |
| --- | --- | --- | --- |
| 账户、Session、角色和成员偏好 | App Account Feature | Infrastructure 通过 App 自有 Port 持久化 | 已认证 App 用例和获授权投影 |
| 领养、归属和成员额度决策 | App Adoption Feature | Infrastructure 通过 App 自有 Port 持久化 | 管理员/成员用例；Nest 容量只是输入，不是重复所有者 |
| 社交关系、会话成员和用户可见消息历史 | App Communication Feature | Infrastructure 通过 App 自有 Port 持久化 | 已授权 App 用例；Elfie 拥有交流和记忆语义，不拥有产品会话 |
| 单只精灵的 Profile、认知和记忆语义 | `elfie/` | Infrastructure 通过 Elfie 自有 Port 持久化 | 精灵自身和明确获授权的 App 投影 |
| Nest 居民、床位、环境时间和互动后果 | `nest/` | Infrastructure 通过 Nest 自有 Port 持久化 | App Orchestration 和获授权 Observer 投影 |
| Food 套餐管理和全局工具启用 | App Configuration Feature | Infrastructure 通过 App 自有 Port 持久化 | Elfie 只通过自有 Port 获得有效强类型投影 |
| Provider 连接管理和凭据引用 | App Configuration Feature | Infrastructure 通过 App 自有 Port 执行持久化与 Secret Adapter | 已授权 App 管理用例；Infrastructure 只接收限定技术输入 |
| Endpoint 模型观测、技术验证和模型调用 | Infrastructure 模型能力 | `infrastructure/models/` 与持久化/报告 Adapter | App 管理投影和 Elfie `ModelPort` 调用 |
| 单次认知步骤的工具选择 | `elfie/` Skills 与认知策略 | `infrastructure/tools/` 执行获批准的受限请求 | Elfie 消费强类型结果；App 配置全局可用性 |
| 房屋几何、坐标、碰撞、导航和已发生物理事件 | `godot_project/` authority | Godot authority 经 `infrastructure/godot/` 协议 Adapter | Nest 接收世界事实；actor body 接收自己的回执 |
| 设备注册、授权和 Elfie/body 关联 | App 设备 Feature | Infrastructure 通过 App 自有 Port 持久化 | 已授权 App 用例和 Orchestration |
| 设备凭据材料 | Infrastructure Secret 能力 | Secret 存储和 `infrastructure/devices/` Adapter | App 只保留引用；获授权设备 Adapter 获得限定访问 |
| 设备传输 Session 和技术健康 | Infrastructure 设备能力 | `infrastructure/devices/` | App 健康投影和授权范围内的 Elfie body 契约 |
| 身体命令和感知语义 | `elfie/body` | 注入的身体/设备 Adapter 执行传输 | 该 Elfie；只有跨 authority 流程进入 Orchestration |
| 进程生命周期和技术就绪状态 | `app/orchestration/lifecycle` | 由 Bootstrap 构造的 Lifecycle Runner 和技术探针 | Owner/Observer 健康投影；业务积压单独展示 |

Infrastructure 可以把多个事实物理存入同一数据库，但存储共址不会合并其语义所有者。
任何其他模块都不能通过复制、缓存或投影同一 Record 创建第二权威事实。

## 模型、Food 与工具所有权

目标架构不存在 AI Runtime 模块。原 `ai_runtime/` 已按下表拆分到对应所有者：

| 职责 | 目标所有者 |
| --- | --- |
| Provider 发现、模型列表、技术探测、请求转换、流式处理、重试与模型调用 | `infrastructure/models/` |
| Food 管理、自动生成套餐、模型管理报告和全局工具设置 | App Feature |
| 读取单只精灵的有效 Food、选择语义模型角色、决定工具使用并消费结果 | `elfie/` 通过自有 Port 完成 |
| Food/配置等持久事实的物理存储 | `infrastructure/persistence/` 实现语义所有者的 Port；存储不是第二 authority |
| 搜索、受限工作区文件、代码沙箱和设备支持的工具执行 | `infrastructure/tools/` |

普通推理链路直接完成：

```text
Elfie -> FoodPort -> Infrastructure 持久化 Adapter -> 数据库
Elfie -> ModelPort -> Infrastructure 模型 Adapter   -> Provider
Elfie -> ToolPort  -> Infrastructure 工具 Adapter   -> 外部能力
```

App 通过 Feature 用例管理配置，但不处在 Elfie 与这些 Adapter 之间的运行时链路。
只有流程真正跨越 Elfie、Nest、Godot、设备或其他 authority 时，才进入 Orchestration。

App Configuration Feature 写入 Food 可见性、授权、分配和套餐选择。持久化 Adapter
根据这些已保存事实，为请求中的 Elfie 作用域解析有效投影，不重新作出授权决策。
Elfie 自己选择语义角色，并单独调用 `ModelPort`。

## Godot authority 双通道

Godot authority 通过一个共享、版本化且经过认证的 Gateway 连接访问，不能每只 Elfie
各自建立原始连接。语义边界拆为两条通道：

1. **Actor 身体通道。** Elfie 通过 body/actor Port 发出语义身体意图；Godot Adapter
   向原身体返回 accepted、started、terminal、blocked、cancelled 或 timed-out 回执。
2. **世界通道。** Godot 世界事实进入 Nest 边界；Nest 应用房间规则和互动传播；
   Orchestration 把结果转成强类型感知投递给受影响的 Elfie。

Actor 命令不必机械经过 Nest；全局世界事实不得绕过 Nest authority。两个 Port 可以由
同一个共享 Godot Gateway Adapter 实现。

Godot 协议传输、authority 宿主选择、产物与进程启动属于
`infrastructure/godot/`；Godot 源资产和物理 authority 永久保留在根
`godot_project/`。Nest 和 Elfie 永不导入 Godot 专用传输或进程实现。

## Bootstrap 与 Orchestration

`app/bootstrap/` 是唯一生产组合根：创建具体 Adapter，构造 Core 和 Service，注入
Port，拥有 Container 对象生命周期并注册清理。Runtime 组件的启动、停止、重启决策
和流程只属于 `app/orchestration/lifecycle`；Bootstrap 只构造并调用其公开边界。测试
和隔离开发工具可以构造 Fake 或沙箱 Container，但不因此成为第二个生产组合根。
Bootstrap 不写产品分支、世界规则、协议映射或持久化逻辑。

`app/orchestration/` 执行跨 authority 的运行时工作流。它可以协调 Elfie、Nest 和
注入的能力契约，但不能构造具体 Infrastructure、成为 Service Locator，或代理普通
Food/模型/工具调用。Bootstrap 接线，Orchestration 指挥。

## 持久化、工具与静态资源

领域 Core 拥有语义存储 Port 和领域模型。Infrastructure 拥有连接、SQL、Schema、
事务、路径、序列化、原子写和技术 Record。数据库 Row、Connection、任意字典和用户
路径不得穿过领域边界。

Elfie Skills 描述某只精灵可以请求什么，保留在 Elfie；App Feature 拥有管理员可见的
全局启用和配置。搜索、文件、代码或设备执行实现属于 `infrastructure/tools/`，并继续
受工具安全和有界结果契约约束。

随领域代码发布的不可变资源，例如默认人格、物种或情绪映射，可以保留在领域模块。
用户数据、可变配置、Runtime 状态和生成文件必须通过 Infrastructure Adapter。

## 边界模型与错误

每个公开 Facade 和 Port 使用由边界消费方或提供方拥有的命名强类型模型。HTTP DTO、
领域模型、Port Model、协议帧和持久化 Record 相互独立。映射发生在 Adapter 或
Orchestration，禁止使用未经校验的 `Any` 或无约束字典穿透边界。

Infrastructure 异常必须先转换成稳定领域/应用错误，再到达 Facade。每个外部操作都要
明确超时、取消、重试、幂等和回执语义。

## 测试与改动收敛

Elfie 和 Nest 单元测试使用内存或 Fake Port，不依赖 SQLite、文件、网络、设备或
Godot。Infrastructure Adapter 单独做聚焦集成测试；Bootstrap 做装配测试；每个完成
迁移的跨系统能力至少有一条真实端到端路径。

保持 Facade 和 Port 不变的内部实现修改应收敛在所有者模块；替换技术只修改 Adapter。
系统级 Port 变化必然同时迁移 Facade/消费方、Adapter 和相关调用方。架构隔离减少意外
跨模块修改，但不会隐藏有意的契约变化。

## 迁移与机器约束

迁移必须渐进执行，治理变更与生产迁移分开。每个切片：

1. 确认当前事实所有者和完整调用链；
2. 定义或确认 Facade、Port 和强类型模型；
3. 实现 Infrastructure Adapter 和 Bootstrap 装配；
4. 迁移全部生产调用方；
5. 删除该已迁移能力及完整调用链对应的旧技术实现和兼容路径；
6. 缩减精确一致性基线并关闭台账条目。

新代码立即遵守本契约。历史偏差只能存在于系统一致性台账和机器基线中；产品或迁移
变更只能缩减基线，不能扩张。
全部条目清零后，删除旧架构基线和一致性页面，永久 Scanner 进入 deny-all 模式。

## 明确不做的事

本契约不要求每个 Facade 或 helper 都定义 Protocol，不要求一个 Adapter 对应一个
Port，也不要求每个方法一个 Port；不引入全局万能 Repository、Service Locator、自动
依赖注入、微服务、完整 CQRS、Event Sourcing 或分布式事务。
