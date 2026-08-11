# 应用架构契约

**契约版本：** 1.5
**采用日期：** 2026-08-10
**适用范围：** `app/`，以及迁往根 `infrastructure/` 的 App Adapter

> **规范性目标。** 本文是 `app/` 下新增代码和已迁移代码的长期架构权威，定义
> 所有权、依赖方向和边界语义；它不表示全部历史实现已经合规。当前偏差记录在
> [应用架构一致性台账](../conformance/application)。中英文文件是同一份逻辑契约的
> 两个语言镜像，必须同步修改。

权威顺序为：

1. 本版本化契约定义架构；
2. `app/AGENTS.md` 为编码工作提供执行摘要；
3. 子目录 `AGENTS.md` 只能细化局部规则，不能反转本契约；
4. 架构测试执行可机器检查的约束；
5. 一致性台账只记录临时缺口，不能批准新的例外。

若要改变所有权或依赖方向，必须先明确升级契约版本，再开始实现。普通迁移只更新
代码、测试和一致性台账，不重写目标。

## 目标与明确不做的事

应用层采用轻量 Ports/Adapters 结构，使产品规则不依赖 FastAPI、SQLite、文件、
设备或模型平台的具体实现。目标是所有权清楚、技术边缘可替换、用例可测试、依赖
只在一个位置装配，而不是增加架构仪式。

本契约**不引入**微服务、通用事件总线、完整 CQRS、Event Sourcing、分布式事务、
万能 Repository、自动扫描式依赖注入框架，也不要求每个 helper 都定义 Port。这些
机制只有在出现独立且已证明的需求并获得批准后才能引入。

[系统架构契约](system)负责顶层物理目录。生产 Adapter 已归位根
`infrastructure/`；禁止恢复已退役的 `app/infrastructure/` 路径。

## 四个 App 区域及其 Infrastructure Adapter

| 区域 | 负责 | 不得负责 |
| --- | --- | --- |
| `app/interfaces/` | HTTP、WebSocket、CLI、Web、Desktop 协议入口；凭据解析；请求响应映射；协议错误映射 | 产品规则、SQL、数据根解析、具体 Repository、Runtime authority |
| `app/features/` | 产品用例、授权、命令、查询、结果、业务错误和用例所需 Port | FastAPI、SQLite、具体 Adapter、线程/进程所有权、跨 authority Runtime 流程 |
| `app/orchestration/` | 跨两个以上 authority 的流程、非原子外部副作用、Runtime 生命周期协同 | 普通 CRUD、协议 DTO、具体持久化或设备 Adapter |
| `infrastructure/` | 持久化、文件、网络、模型平台、设备和操作系统能力的 Port 实现 | 产品授权、页面行为、用例流程决策 |
| `app/bootstrap/` | 组合根：创建、注入、对象生命周期、启动和收束装配 | 业务分支、SQL、协议映射、第二套配置事实 |

四个 App 自有区域是 Interface、Feature、Orchestration 和 Bootstrap。根
Infrastructure 是它们使用的独立 Adapter 层；表格列出它，是为了明确 App 与该层的
依赖边界，而不是把它算成第五个 App 内部区域。

## App 最终业务与工作流地图

以下目录地图是已迁移 App 代码的规范性目标。它冻结所有权和迁移单元，但不要求在真实
切片开始前创建空目录。

```text
app/features/
├── accounts/
├── adoption/
├── communication/
├── elfies/
├── nest_management/
├── configuration/
│   ├── providers/
│   ├── food/
│   ├── capabilities/
│   └── settings/
├── setup/
├── bodies/
└── operations/

app/orchestration/
├── lifecycle/
├── nest_session/
├── resident_admission/
├── setup_installation/
├── message_delivery/
├── embodiment/
└── observer/
```

Feature 所有者如下：

| Feature | 拥有 | 明确不拥有 |
| --- | --- | --- |
| `accounts` | 账户、Session、密码、角色、成员资料、成员管理和偏好 | 领养决策、Runtime 生命周期或协议认证 DTO |
| `adoption` | 候选、领养和所有权关系、单成员额度覆盖与最终领养资格 | Nest 床位容量、Elfie Profile 事实或实时 Nest 接纳 |
| `communication` | 产品当前已有的会话关系和用户可见消息历史 | Elfie 通信/记忆语义、传输 Session 或实时投递协调 |
| `elfies` | 获授权的 Elfie 目录、关系/权限投影，以及成员/管理员 Profile 或认知视图 | Elfie Profile、认知或记忆事实；领养所有权；Nest 居民状态 |
| `nest_management` | 通过唯一公开 Nest 门面提供的授权产品用例 | 第二套 Nest Repository 语义、几何、坐标或真实 Elfie 组合 |
| `configuration/providers` | Provider 连接管理、凭据引用和模型资源管理投影 | 技术模型发现、探测、请求转换或模型调用 |
| `configuration/food` | Food 包管理、分配、生成和管理报告 | 单只 Elfie 的语义模型角色选择或物理存储实现 |
| `configuration/capabilities` | 当前已有的管理员全局工具和能力开关 | 工具执行、Elfie Skill 策略或猜测性新能力 |
| `configuration/settings` | 其他当前已有、具备唯一类型化所有者和写入者的全局产品设置 | Nest 容量、Provider/Food 事实或任意无类型 section |
| `setup` | 首装草稿、选择、校验、状态和受限投影 | 账户、Provider、Food、Nest 事实及安装任务所有权 |
| `bodies` | 外部身体注册、配对、撤销、授权和 Elfie/body 关联 | 凭据内容、设备传输 Session、身体语义或托管/归巢工作流 |
| `operations` | 当前已有的授权系统统计、维护、备份/重置用例和稳定 Runtime 管理投影 | Runtime 生命周期决策、Observer Session、原始技术对象或重复业务事实 |

Orchestration 工作流如下：

| 工作流 | 协调范围 |
| --- | --- |
| `lifecycle` | Core、Gateway、Godot authority 的启动、停止、重启、恢复和就绪状态 |
| `nest_session` | 唯一 Nest、真实 Elfie 实例、世界事件和共享 Godot world channel |
| `resident_admission` | 已接受领养、Elfie 构造、Nest 接纳和明确失败补偿 |
| `setup_installation` | Setup 状态与 Accounts、Provider/模型、Food、Nest、受管安装 Runner |
| `message_delivery` | 已授权会话命令、用户可见历史、真实 Elfie 投递和回执 |
| `embodiment` | 真实 Elfie、Nest 和外部身体的托管、归巢、切换与恢复 |
| `observer` | 受限 Observer 主体/能力、授权投影和允许的高层意图 |

这些目录不是逐层一一镜像。Accounts、Configuration、Elfie 投影、Nest 管理和运维留在
Feature，只有真实流程跨 authority 时才进入 Orchestration。浏览器 HTTP 和同源
WebSocket 仍属于 App Interface；`infrastructure/communication/` 实现外部通信 Port，
不接管 API 协议所有权。

目标版本化 API 代码位于 `app/interfaces/api/v1/`，按 `auth`、`setup`、`me`、
`elfies`、`admin`、`observer`、`realtime` 资源范围组织。Admin 资源按 `users`、
`elfies`、`nest`、`model_providers`、`food_packages`、`settings`、`runtime` 组织。
Python 物理目录使用 snake_case，公开 URL 继续遵守 API 契约的 kebab-case 规则。
`/api/health` 仍是唯一不版本化技术探针。

`app/bootstrap/` 仍是唯一组合根，不要求按业务域镜像。每个纵向迁移切片只增加自己
实际需要的装配。

应用层有两个平面。`features/` 处理能够在一个业务 authority 内完整推理的产品用例；
当流程跨越 `elfie/`、`nest/`、Godot、设备或受管理进程等 authority 时，由
`orchestration/` 协调。一个流程函数多，并不自动等于 Orchestration。单只精灵通过
注入 Port 读取 Food 或调用模型/工具，明确不属于 App Orchestration。

## 允许的依赖方向

```text
interfaces    -> Feature 公开用例 / Orchestration 公开门面
features      -> 自有模型和 Port + 获准的领域公开 API
orchestration -> App Port + elfie / nest 公开 API
infrastructure-> 实现 Feature / Orchestration Port + 技术库
bootstrap     -> 所有区域，但只做装配
```

详细矩阵如下：

| 来源 | 可以依赖 | 禁止方向 |
| --- | --- | --- |
| Interface | Feature 和 Orchestration 公开 API；协议库 | Infrastructure 具体实现、Bootstrap、其他 Interface 私有实现 |
| Feature | 自有模型和 Port；其他 Feature 公开门面；获准的领域公开 API | Interface、Bootstrap、具体 Infrastructure、其他 Feature 内部模块 |
| Orchestration | Feature 公开契约、自有 Port、`elfie`/`nest` 公开 API | Interface、Bootstrap、具体 Infrastructure |
| Infrastructure | 自己实现的 Feature/Orchestration 契约；技术库 | Interface、Bootstrap、产品规则或 Feature 私有实现 |
| Bootstrap | 所有需要装配的具体对象 | 装配与生命周期之外的产品决策 |

App 内不能形成 import 环。Feature 通过包门面暴露稳定用例和边界模型；其他 Feature
或 Interface 不导入它的内部 service、helper 或 Repository。Bootstrap 可以导入
具体构造目标，但不能成为产品代码运行时调用的 Service Locator。

## Feature 形态与 Port 所有权

完成迁移的 Feature 通常包含：

```text
app/features/<domain>/
├── __init__.py      # 稳定公开门面
├── models.py        # command、query、result 和值对象
├── ports.py         # 本领域需要的 Protocol
├── errors.py        # 稳定业务错误
└── service.py       # 用例实现
```

这是职责图，不要求创建空文件。小领域可以合并文件，但必须保留相同边界。

Port 归使用者所有。Feature 定义自己需要的持久化、时钟、任务、外部服务或设备能力；
Infrastructure 实现；Bootstrap 注入。只有外部事实、可替换技术能力或副作用边界才
建立 Port，纯计算和私有 helper 保持普通的强类型函数。

Adapter 不能把 Port 扩张成第二套业务 API。持久化 Record 是 Adapter 内部类型。
Repository 可以表达事实的保存和查询，但不能决定管理员是否可以领养精灵，或页面
应该展示哪个字段。

### 外部身体与设备

外部身体概念、命令和感知契约属于 `elfie/body`。设备注册、列表、撤销、授权和
Elfie/body 关联属于 App Feature。凭据材料、局域网传输、设备 Session 和技术健康属于
Secret 与 `infrastructure/devices` Adapter；App 只保存凭据引用。托管、归巢、离线和身体切换需要
协调真实精灵、Nest 和设备时属于 Orchestration。持久化实现对应
Feature/Orchestration Port，Bootstrap 完成装配。设备传输本身既不是产品流程，也不是
授权 authority。

## 每个边界的模型

每个边界都有一个明确所有者的模型：

- Interface DTO：校验后的 HTTP/WS/CLI 输入输出；
- Feature command/query/result：产品意图和投影；
- Principal/RequestContext：认证身份和请求元数据；
- Port model：跨技术边界所需的最小数据；
- persistence record：数据库表示，只在 Adapter 内部使用；
- domain public model：`elfie` 或 `nest` 导出的公开类型。

FastAPI Request、SQLite Connection/Row、ORM Record 和未校验字典不能跨越这些
边界。公开边界不得新增 `Any`、`Dict[str, Any]`、随角色变化的动态结构或未检查
断言。外部数据和配置使用 Pydantic 校验；内部可使用 dataclass、Protocol、Enum
和值对象。代码模型是契约事实源，不再手写第二份 JSON Schema。

新增和已迁移领域进入严格 MyPy 范围。现有全局类型债按领域逐步减少，不能成为在
已迁移边界继续新增松散类型的理由。

## 身份、授权与错误

Interface 验证凭据并构造严格 Principal；Feature 根据用例和资源关系执行授权。
隐藏按钮、Route 名称、客户端自报的用户或精灵 ID 都不是授权。

`user`、`setup`、`admin`、`observer`、`device` 使用相互独立、最小权限的主体类型。
设备和 Observer 凭据不得复用 Owner 或 Runtime authority 凭据。RequestContext 可
额外携带关联 ID、语言和安全客户端元数据，但不能变成任意请求袋。

Feature 和 Orchestration 返回类型化结果，或抛出稳定业务错误，例如 validation、
not-found、conflict、forbidden、unavailable 和 retryable-external-failure。Interface
把它们统一映射为协议状态和版本化错误 envelope。Infrastructure 异常在 Adapter/
用例边界转换，不能直接泄漏给调用方。

## 命令、查询与一致性

ElfieNest 使用轻量命令/查询分离，而不是完整 CQRS：

- command 修改权威事实，使用命令服务和写 Port；
- query 读取权威事实或明确的派生投影，使用查询服务和查询 Port；
- 读操作不能偷偷修复、迁移或创建产品状态。

三类一致性必须明确：

1. **数据库事务。** 一个用例拥有一个 Unit of Work。Repository 不能隐藏会破坏多步
   不变量的 commit。SQL 仍只能位于获准的持久化边界。
2. **类型化文件更新。** 一个写入者拥有一份已校验文档，通过临时文件和原子替换
   更新；不双写，不建立 fallback 事实源。
3. **外部工作流。** 网络、模型、Godot、设备操作按需要使用持久工作流状态、幂等键、
   超时、回执和明确补偿/恢复；不能伪装成数据库事务。

数据库事务内不得等待网络、模型、Godot 或设备响应。应先保存意图并结束事务，再
执行外部动作，最后按工作流契约保存回执或失败。

## 生命周期、异步工作与可靠性

Bootstrap 拥有生产 Container 的对象生命周期和通用清理：

| 生命周期 | 典型对象 |
| --- | --- |
| 进程/Container | 应用 Container、Gateway、无状态 Service、Scheduler |
| 请求/用例 | Principal、RequestContext、Unit of Work、写/查询 Adapter |
| 连接 | WebSocket Session 和连接级缓冲 |
| Job/Task | 取消 Token、进度、回执和持久任务状态 |

Feature 不启动线程、进程、无限循环或无人管理的 `asyncio.create_task`。后台工作由
Scheduler/Runner Port 拥有，并定义收束行为。Runtime 进程启动、停止、重启的决策和
流程仍只属于 `app/orchestration/lifecycle`；Bootstrap 只构造并调用其公开边界。测试
可以构造 Fake，但不因此成为第二个生产组合根。

Port 明确同步或异步语义。异步 Interface 不在事件循环中执行长时间阻塞操作。
跨边界调用有明确超时。重试只用于已分类为可重试且幂等的操作，使用有限退避，并
保持同一个关联/幂等 ID。长任务返回稳定 `task_id`，并定义状态查询、失败、取消、
超时和进程重启后的语义。

## 配置、密钥、缓存与可观测性

每份配置文档只有一个类型化所有者、一个优先级和一个写入者。Feature 通过 Port
请求配置，不解析 `ELFIE_HOME`，也不直接读 YAML/SQLite。Secret 只以引用或专用
Secret Port 流动，不进入普通 DTO、日志、报告和缓存。

缓存必须声明权威源、Key 作用域、失效触发、最长寿命和重建方式，不能成为第二事实源。

请求、任务和外部工作流通过 Port 调用和安全结构化日志传递关联 ID。日志记录用例和
结果，但不记录密码、Token、API Key、完整设备凭据或私密内容。系统健康只表达技术
可运行性；业务待办进入事件或产品投影。

## 组合根与 API 映射

组合根创建具体 Adapter，组装 Feature Service 和 Orchestration Facade，再注入
HTTP/WS/CLI/Desktop 入口。Route 和依赖函数不得实例化 Repository、Registry 或
Store。Setup 与 Admin 可以暴露同一能力的不同投影，但必须复用相同 Feature 和
Adapter，不能复制事实或算法。

API 资源、版本和 DTO 细则由 `app/interfaces/api/AGENTS.md` 进一步规定；App 契约
仍是依赖方向和所有权的权威。

## 机器约束与迁移

`scripts/architecture/app_layer_scan.py` 扫描依赖图、Feature 隔离、组合边界、Route
模型和部分公开类型规则；`test/architecture/test_app_layer_boundaries.py` 保护扫描器及
周边契约。精确历史基线是临时的，并通过缺口 ID 关联一致性台账。基线必须精确匹配
当前债务：清除债务时同一改动必须缩减基线；新增或恢复条目直接失败。

仓库级变更流程、契约与台账生命周期以及主分支对照门禁由
[仓库架构治理契约](./repository-governance)定义。本契约负责定义 App 目标，不能为
自己的机器例外放行。

迁移按业务域逐个闭环。一个领域只有同时满足以下条件才算完成：

1. 已盘点 Route、调用方、Service、Adapter 和事实源；
2. 已建立唯一 Feature 公开门面和严格 command/query/result 模型；
3. 所需 Port 由使用方拥有；
4. Infrastructure Adapter 实现 Port，Bootstrap 完成注入；
5. 不再存在禁止的跨层或跨 Feature 内部 import；
6. 授权和 Principal 行为有聚焦测试；
7. 事务、文件或外部工作流语义有聚焦测试；
8. 适用时已测试错误、超时、重试和幂等；
9. 所有生产调用方都使用新路径；
10. 旧 Route、DTO、Adapter、兼容分支和夹具已删除；
11. 精确架构基线和一致性台账已缩减；
12. 至少一条真实端到端用例证明最终调用链。

只有存在代码和测试证据时才能关闭台账条目。已经登记的缺口也不能授权新代码重复它。
