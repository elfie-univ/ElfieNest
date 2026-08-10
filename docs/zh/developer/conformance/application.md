# 应用架构一致性台账

> 本文是规范性[应用架构契约](../contracts/application)的临时实现缺口台账，只记录
> 当前历史不合规，不定义架构，也不批准新的例外。当全部条目关闭且精确机器基线清零
> 后，删除本页及其导航入口。

## 状态与证据规则

- `open`：当前生产代码仍违反契约。
- `in progress`：一个业务域正在迁移，但完整完成条件尚未通过。
- `closed`：调用方、实现、测试和机器基线已经全部清理。
- 不能因为文档、接口或替代类已经存在就关闭条目；旧生产调用链也必须删除。
- 每个机器例外都带一个缺口 ID。禁止未登记例外，缺口 ID 也不能批准新增同类违规。

可执行事实源是 `test/architecture/baselines/app_layer.py`，其中条目精确到 import、
函数、构造点或 Route。架构测试要求它与当前代码精确一致：删除债务时必须在同一改动
删除基线条目；新增或恢复债务会失败。本文只按原因和验收门归组，不复制整份机器清单。

## 当前缺口

| ID | 严重级别 | 状态 | 当前缺口 | 验收门 |
| --- | --- | --- | --- | --- |
| APP-001 | P0 | open | Interface 直接导入具体持久化/设备实现，因此知道技术存储和 Gateway 细节。 | 所有 Interface 只依赖注入的 Feature/Orchestration 公开服务和协议模型；`interface -> infrastructure` 机器集合清零。 |
| APP-002 | P0 | open | Feature 导入具体 Infrastructure，部分公开用例接收 `db_path`，一个 Feature 导入 FastAPI；embodiment Orchestration 也导入持久化实现。 | 用使用方拥有的 Port 替代具体依赖，公开用例接收类型化依赖，Feature/Orchestration 隔离机器集合清零。 |
| APP-003 | P0 | open | 组合根不完整；API/CLI 工厂、Route 和依赖 helper 会构造 Repository、Store 或 Registry。 | Bootstrap 拥有构造和生命周期，入口接收应用 Container 或明确 Service，Interface 构造机器集合清零。 |
| APP-004 | P1 | open | Interface 和 Feature 导入其他 Feature 内部模块；Infrastructure 也依赖一个 Feature 私有模块；稳定包门面不一致。 | 每个已迁移领域只暴露一个公开门面，跨域调用使用门面或自有 Port；内部 import 机器集合清零，App import 图无环。 |
| APP-005 | P1 | open | 许多 JSON Route 没有命名 `response_model`，协议边界仍有松散字典/`Any` 注解。 | 所有产品 Route 使用严格请求/响应模型和统一错误 envelope；非 JSON 页面/流响应明确声明；Route 模型与松散注解机器集合清零。 |
| APP-006 | P1 | open | 认证、角色检查和错误映射散落在 Interface 与 Feature helper 中，没有统一 Principal/RequestContext 和业务错误分类。 | user/setup/admin/observer/device 使用严格主体；Interface 认证、Feature 授权；业务错误只有一套已测试协议映射。 |
| APP-007 | P1 | open | 事务所有权、Repository commit、类型化文件写入和外部工作流恢复尚未通过 Port 与测试统一表达。 | 每个已迁移 command 声明数据库、文件或外部工作流一致性类别；DB 事务内不等待外部响应；原子性和恢复测试通过。 |
| APP-008 | P1 | open | 部分 Feature 持有线程/Job 或阻塞平台工作，任务取消、超时、回执和重启语义不一致。 | Scheduler/Runner Port 拥有后台工作，Bootstrap/lifecycle 拥有 Runner；异步边界和长任务语义有聚焦测试。 |
| APP-009 | P1 | open | 全局 MyPy 仍非 strict，尚未建立已迁移领域严格区。 | 每个已迁移领域及其公开调用方通过 strict MyPy，不使用 `Any` 逃生口；领域关闭时扩大 strict override。 |
| APP-010 | P1 | open | 外部身体持久化与设备注册存在重叠 Registry/Repository；embodiment 契约导入持久化 Record，Orchestration 携带 `db_path`。 | 只保留一套外部身体产品模型和使用方 Port；设备传输是 Infrastructure Adapter；托管/归巢仍属于 Orchestration；删除重复事实和具体 import。 |
| APP-011 | P1 | open | 版本化和历史产品 API 并存，存在重复调用方投影和无类型旧资源。 | 按 `app/interfaces/api/AGENTS.md` 逐业务域迁移，移动全部真实调用方，再删除旧 Route、Client、DTO 和夹具，不保留别名。 |
| APP-012 | P1 | open | App 各领域的配置、Secret 和缓存尚未共用一套可执行所有权模板。 | 每个已迁移配置只有一个类型化所有者/写入者和优先级；Secret 使用引用/Secret Port；缓存声明权威源、失效、寿命和重建方式。 |

## 机器覆盖

当前 App 精确 Scanner 与 `app_layer.py` 基线覆盖 `APP-001`、`APP-002`、`APP-003`、
`APP-004`、`APP-005`、`APP-008`、`APP-011`。其余授权、事务、严格类型、外部躯体事实和
配置所有权条目，需要在选中各业务域迁移时补充专属测试和审查。Scanner 通过只证明未
新增已覆盖违规且基线精确，不代表整个 App 契约已经达标。

## 迁移单元记录

每个获批的领域迁移在改代码前向本节添加一份短记录：

```text
业务域：
缺口 ID：
当前权威事实：
Route 与生产调用方：
目标公开门面与模型：
Port 与 Adapter：
一致性类别：
Principal 与授权：
超时 / 重试 / 幂等：
历史删除清单：
聚焦测试与端到端验收：
需要删除的机器基线条目：
状态：open | in progress | closed
```

这份记录是执行检查表，不是设计权威。只有应用架构契约中的十二项完成条件全部通过，
领域才能关闭。即使属于同一业务域，API 调用方迁移、持久化变化和 UI 变化仍应保持
可分别审阅。

### Accounts：认证与会话

```text
领域：accounts / authentication-session
缺口 ID：APP-001、APP-002、APP-003、APP-004、APP-005、APP-006、APP-009、APP-011、APP-012
当前权威事实：nest.db 中的用户凭据与角色；nest.db 中哈希保存的浏览器会话；runtime.yaml 的 system.security 会话 TTL 与登录限流设置
路由与生产调用方：POST /api/v1/auth/login 与 /logout；浏览器 session client；HTTP、页面、WS、Setup、Observer 的认证依赖
目标公共门面与模型：Accounts 认证/会话门面；严格 Account Principal、登录 Command 与认证会话 Result
Port 与 Adapter：账户凭据/会话持久化 Port 由根 Infrastructure SQLite 实现；强类型安全策略 Port 由根 Infrastructure Runtime 配置实现
一致性类别：每次签发或撤销会话各自一个数据库事务；配置保持强类型文件读取
Principal 与授权：Interface 解析凭据/Cookie，并把 Feature 结果构造成请求 Principal；Accounts 判定 Owner/Manager 权限
超时、重试与幂等：本地同步存储与配置读取；不重试；撤销会话具备幂等性
旧实现删除清单：app/features/accounts/auth.py；旧登录/登出路由与路径；对 Feature 内部认证模块的直接导入；认证链中的具体持久化/配置构造
聚焦测试与端到端门：Accounts service 与 Adapter；共享 HTTP 依赖；登录/登出 Cookie 与 CSRF 流程；WebSocket 会话校验；前端 session client；聚焦 App 架构扫描
已删除的机器基线条目：accounts/auth Feature 隔离与内部导入条目；被替代的 Interface 构造/内部导入条目；POST /api/auth/login 与 POST /api/auth/logout
状态：closed
```

### Nest Management

```text
领域：nest_management
缺口 ID：APP-001、APP-002、APP-003、APP-004、APP-005、APP-006、APP-007、APP-009、APP-011
当前权威事实：公开 NestConfig 的唯一 Nest 身份与容量约束；nest.db 的 nest_settings 和可空 Elfie 床位号
路由与生产调用方：/api/v1/admin/nest 的房间、床位数和 Elfie 床位资源；Owner Nest client、监控投影与存储端到端链路
目标公共门面与模型：带强类型容量/分配 Command 和 Result 的授权 Nest Management 门面
Port 与 Adapter：NestManagementPort 由根 Infrastructure SQLite Adapter 实现，并由 Bootstrap 注入
一致性类别：每个容量或分配命令拥有一个 immediate SQLite 事务；读取不创建状态
Principal 与授权：Interface 认证账户 Principal；Nest Management 授权管理员
超时、重试与幂等：本地 SQLite；不重试；重复设置相同容量或分配具备幂等性
旧实现删除清单：app/features/nest_registration；app/interfaces/api/nest_routes.py；旧 /api/owner/nest 资源及 Interface 直接 Repository 构造
聚焦测试与端到端门：Feature、Adapter、严格 Route；Owner Nest/监控前端；最终存储产品链路；App/System/Storage 架构门
已删除的机器基线条目：旧 Nest Interface 构造/import；松散/缺失 Route 模型；旧 GET/PUT /api/owner/nest 资源
状态：closed
```

### Configuration：全局设置

```text
领域：configuration/settings
缺口 ID：APP-001、APP-003、APP-004、APP-005、APP-006、APP-007、APP-009、APP-011、APP-012
当前权威事实：runtime.yaml 的 system.adoption、system.engine 与 system.security；默认值仍唯一来自 DEFAULT_SYSTEM_SETTINGS
路由与生产调用方：/api/v1/admin/settings/{elfies,runtime,security}；管理端设置面板；Adoption 与 Accounts 的实时配置读取
目标公共门面与模型：三个现有资源各自使用强类型 Query、Patch Command 与 Result 的 Settings 门面
Port 与 Adapter：SettingsStorePort 由根 Infrastructure Runtime 设置 Adapter 实现，并由 Bootstrap 单次注入
一致性类别：本地同步类型化文件读取；每次 Patch 原子替换一个自有 section，同时保留无关 Runtime 字段
Principal 与授权：Interface 认证严格账户 Principal；Settings 授权管理员；安全设置变更使 Accounts 限流缓存失效
超时、重试与幂等：本地文件访问；不重试；重复提交相同 Patch 具备幂等性
旧实现删除清单：app/interfaces/api/system_routes.py；通用 /api/owner/system/{section}；旧前端调用与 Route 夹具
聚焦测试与端到端门：Settings Service、Adapter、DTO；Adoption/Security 实时集成行为；前端设置面板；聚焦 App 架构扫描
已删除的机器基线条目：旧 Settings 内部 import；松散/缺失 Route 模型；GET 与 PUT /api/owner/system/{section}
状态：closed
```

### Elfies：授权目录与档案投影

```text
领域：elfies
缺口 ID：APP-001、APP-003、APP-004、APP-005、APP-006、APP-009、APP-011
当前权威事实：nest.db 的 Elfie 身份与领养关系；每只 Elfie 的权威 profile.yaml；每只 Elfie 的 cognition SQLite
路由与生产调用方：成员 Elfie 列表/档案、对话列表与管理员监控聚合；目标资源为 /api/v1/elfies 与 /api/v1/admin/elfies
目标公共门面与模型：授权 Elfies 查询门面；严格关系、权限、Profile、认知、成员与管理员 Result
Port 与 Adapter：ElfiesQueryPort 由根 Infrastructure 的只读 SQLite/Workspace 投影 Adapter 实现，并由 Bootstrap 注入
一致性类别：只读查询；缺失或损坏的 Profile/认知分别投影为 empty 或 unavailable，不创建或修复状态
Principal 与授权：Interface 认证账户 Principal；Elfies 门面约束成员所有权并授权管理员全局投影
超时、重试与幂等：本地只读 SQLite/YAML；认知库短 busy timeout；不重试；查询幂等
旧实现删除清单：app/features/elfie_profile；旧 Interface cognition reader；混合成员/管理员 Route 中的 Elfies 自有拼装；旧 DTO、前端 Client 和夹具
聚焦测试与端到端门：Feature、Adapter、严格成员/管理员 Route；现有成员 Profile/对话和管理员监控回归；前端 Elfie 页面；App/System/Storage 架构门
已删除的机器基线条目：旧 cognition Feature 到 Infrastructure import；成员 Route 对旧 cognition 投影和 reader 的直接依赖
状态：in progress
```

### Configuration：模型 Provider 管理

```text
领域：configuration/providers
缺口 ID：APP-001、APP-003、APP-004、APP-005、APP-006、APP-007、APP-009、APP-011、APP-012
当前权威事实：v2 providers.yaml 连接与模型记录；credential reference 指向的 Secret；现有 Provider 目录和验证/benchmark 报告
路由与生产调用方：/api/v1/admin/model-providers 的目录、连接、模型、验证、矩阵和 benchmark 资源；管理端 Provider Client；历史 CLI 配置入口；Setup/Ollama 混合入口
目标公共门面与模型：Providers 管理门面；现有 CRUD、生命周期、验证、刷新、矩阵、benchmark 的严格 Command、Query 与 Result
Port 与 Adapter：目录/连接、Food 引用保护、技术探测/发现/报告由使用方拥有的窄 Port 表达；根 Infrastructure Models 与 Persistence Adapter 实现并由 Bootstrap 注入
一致性类别：v2 类型化连接/Secret 写入保持现有原子更新；验证、发现和 benchmark 是有界外部工作；报告使用现有持久化事实
Principal 与授权：Interface 认证账户 Principal；Providers 门面授权管理员；普通成员不能读取管理投影
超时、重试与幂等：沿用现有 Provider 技术边界的有界超时、并发上限与缓存/验证策略；不新增自动重试或 Provider 能力
旧实现删除清单：旧 Provider 管理 Route 与 /api/owner/providers 连接/模型资源；API 层技术验证实现；旧管理前端路径；CLI 的 runtime.yaml/auth.env v1 写入链
聚焦测试与端到端门：Feature、Adapter、严格 v1 Route；CRUD、验证、刷新、矩阵、benchmark、取消/失败和 Food 引用保护回归；前端 Provider/监控 Client；App 与 AI Runtime 架构门
已删除的机器基线条目：旧 Provider Route 构造、松散模型、未版本化连接/模型资源及已迁移 API 技术实现
状态：in progress
```

### Communication 与消息投递

```text
业务域：communication / message_delivery
缺口 ID：APP-001、APP-003、APP-004、APP-005、APP-006、APP-007、APP-009、APP-011
当前权威事实：每只 Elfie 唯一的 conversations/history.sqlite；Elfies 所有权投影；现有强类型 Elfie 接纳回执
路由与生产调用方：/api/v1/me/conversations、/api/v1/ws/chat、已认证的历史 socket 传输和浏览器 Chat 界面
目标公共门面与模型：CommunicationFacade 负责授权历史，MessageDeliveryFacade 负责实时用户/精灵消息投递
Port 与 Adapter：根 Infrastructure 的 SQLite 历史、Elfie 投递和同源实时 Adapter，由 Bootstrap 装配
一致性类别：先授权并接纳，再唯一追加用户历史；精灵回复先唯一持久化，再广播同一记录
Principal 与授权：Interface 认证 AccountPrincipal；Communication 通过公共 Elfies 门面校验可见所有权
超时、重试与幂等：保留现有同步接纳行为；不新增重试；duplicate 接纳永不追加历史
旧实现删除清单：app/features/chat、Interface 聊天持久化 helper、重复 v1 client 聊天 Route 与旧同源 realtime helper
聚焦测试与端到端门：Feature/工作流/Adapter、严格 HTTP 与 WebSocket 资源、历史 socket 桥、浏览器聊天、最终存储链路和 App/System/Storage 门
已删除的机器基线条目：已删除的聊天 Interface 构造/具体 import、宽松 conversation Route 与被替换的持久化路径
状态：closed
```

### Orchestration：实时 Nest Session

```text
业务域：orchestration/nest_session
缺口 ID：APP-002、APP-003、APP-004、APP-007、APP-009
当前权威事实：公共 Nest 状态/Repository 契约、真实 Elfie 实例和已认证 Godot protocol-v2 世界事实
路由与生产调用方：源码 serve/chat/验证入口、HTTP 健康、领养接纳、Observer 投影和 Nest Lab
目标公共门面与模型：唯一 NestSession/ElfieNestEngine 工作流与 App-owned 语义世界 Port Model
Port 与 Adapter：根 GodotNestSessionAdapter；Bootstrap 构造 Engine、Repository 和认知 Runtime factory；Lifecycle 启停进程内 channel
一致性类别：Nest Repository 修改保留现有事务语义；Runtime mirror 仍为短期态，Godot 仍是物理权威
Principal 与授权：内部工作流只接收已授权的产品命令，不认证 HTTP 调用者
超时、重试与幂等：保留现有 tick 和 Runtime generation 行为；不新增重试；限制一个 Engine loop 和一个 Runtime generation
旧实现删除清单：已删除平铺 Engine/Session/runtime-sync/event/scene 模块与重复 owner-message helper；剩余 Observer 投影和旧 Nest persistence 位置由各自切片闭合
聚焦测试与端到端门：Nest Session 与 Godot Adapter、Gateway/Nest state、serve 入口、Observer 语义投影、Nest Lab 和架构门
已删除的机器基线条目：Interface 构造/import Nest state Adapter 的条目；未新增 App 基线债务
状态：in progress
```

### Operations：维护与 Runtime 状态

```text
领域：operations
缺口 ID：APP-001、APP-002、APP-003、APP-004、APP-005、APP-006、APP-007、APP-009、APP-011
当前权威事实：选定最终数据根上的用量、Session、表计数投影和数据库维护；现有进程内 RuntimeObserver 快照
路由与生产调用方：/api/v1/admin/runtime/status；监控 Client；本地数据库状态、统计、Session、备份和重置 CLI 流程
目标公共门面与模型：带严格投影、维护与只读 Runtime 状态 Query、Command、Result 的 OperationsFacade
Port 与 Adapter：一个根 SQLite Operations Adapter 实现投影与维护 Port；根 Models Adapter 投影现有 Runtime observer；Bootstrap 向 HTTP 与 CLI 入口注入门面
一致性类别：投影只读；备份复用现有 SQLite 安全复制流程；重置保留现有最终数据根安全校验
Principal 与授权：HTTP Interface 认证账户 Principal，Operations 授权管理员；本地维护仍是 CLI 专属操作并保留现有重置确认
超时、重试与幂等：本地同步存储和进程内快照读取；不重试；备份创建带时间戳副本，重置保留现有重复执行行为
旧实现删除清单：administration 中的 Operations 函数/模型；旧 database-maintenance 与 system Repository；未版本化 Runtime 状态 Route；CLI/TUI 对 system-service 的直接调用
聚焦测试与端到端门：Feature、SQLite 与 observer Adapter、严格 Route、CLI/TUI 和 monitor Client；App/System/Storage/Runtime observer 架构门
已删除的机器基线条目：administration 具体 import 与 db-path 用例；config TUI 内部 import；旧 Runtime Route 松散/缺失模型和未版本化资源
状态：closed
```

### Configuration：Food 管理

```text
领域：configuration/food
缺口 ID：APP-001、APP-002、APP-003、APP-004、APP-005、APP-006、APP-007、APP-009、APP-011、APP-012
当前权威事实：nest.db 的 Food 包与 Elfie 主粮分配；现有 AI Runtime 实现中的模型证据、健康与规划算法
路由与生产调用方：/api/v1/admin/food-packages 与 /api/v1/elfies/{elfie_id}/food-policy；管理端 Food 页面、Elfie 档案/监控投影与 Runtime 主粮选择
目标公共门面与模型：包含严格包管理、生命周期、预览、分配和解析 Command、Query、Result 的 Food 管理门面
Port 与 Adapter：一个根 SQLite Adapter 实现目录/分配 Port；根 Models Adapter 委托唯一现有证据、健康和规划实现；Bootstrap 注入门面
一致性类别：每个目录或分配修改拥有一个 SQLite 事务；证据与健康是只读技术投影
Principal 与授权：Interface 认证账户 Principal；Food 对管理操作授权管理员，对成员策略访问校验 Elfie 所有权；Runtime 使用非用户解析 Query
超时、重试与幂等：保留现有有界模型证据与规划行为；不新增重试；重复策略/生命周期更新保留现有幂等性
旧实现删除清单：旧 Food Feature helper、分配持久化 helper、未版本化 Owner/成员 Food Route 与 API support；Setup 和 Runtime 目录调用方迁移后删除旧 App Food Repository
聚焦测试与端到端门：Feature、SQLite/技术 Adapter、严格 Route；混合 Elfie 投影与 Runtime 选择；前端 Food Client；App/System/Storage/AI Runtime 架构门
已删除的机器基线条目：旧 Food Feature 具体 import/db_path 调用；Interface 构造、具体/内部 import；松散/缺失模型与未版本化 Food 资源
状态：in progress
```

### Configuration：全局能力

```text
领域：configuration/capabilities
缺口 ID：APP-001、APP-003、APP-004、APP-005、APP-006、APP-007、APP-009、APP-011、APP-012
当前权威事实：复合 Runtime 设置 Store 中的逻辑 runtime_policy.tools 投影；专用 Secret Store 中的凭据引用；现有 DirectToolValidationRunner 结果
路由与生产调用方：/api/v1/admin/settings/capabilities 与管理端 Tools Client
目标公共门面与模型：只针对现有 web-search、local-file 能力，提供严格 list、patch、verification Command、Query、Result 的 Capabilities 门面
Port 与 Adapter：Runtime 配置、Secret、验证 Port 由根 Infrastructure Tools Adapter 实现并由 Bootstrap 注入
一致性类别：能力 Patch 复用现有原子类型化文件写入；Secret 写入仍在 Secret Store；GET 只读
Principal 与授权：Interface 认证账户 Principal；Capabilities 授权管理员且永不返回 Secret 值
超时、重试与幂等：保留现有直接验证边界；不重试；重复相同 Patch 具备幂等性
旧实现删除清单：tool_owner_routes.py、/api/owner/runtime/tools 资源和旧前端路径/夹具
聚焦测试与端到端门：Feature 和三个根 Adapter；包含只读 GET 与 Secret 处理的严格 Route；前端 Client；App/System 架构门
已删除的机器基线条目：旧能力 Feature 内部 import、松散/缺失 Route 模型和未版本化 tool 资源
状态：closed
```

### Adoption 与 Resident Admission

```text
业务域：adoption / resident_admission
缺口 ID：APP-001、APP-002、APP-003、APP-004、APP-005、APP-006、APP-007、APP-009、APP-011、APP-012
当前权威事实：Settings 领养策略；nest.db 的账户额度与 Elfie ownership；唯一 30 分钟进程内候选集；最终 Elfie 档案 Workspace；实时 Nest Session
路由与生产调用方：/api/v1/me/adoption 的选项与提交、candidate-set 与回复资源、浏览器领养旅程、源码模式默认 Elfie seed
目标公共门面与模型：AdoptionService 负责选项、候选、回复与原子 ownership 预留；ResidentAdmissionService 负责最终档案、Elfie 构造、实时接纳与补偿
Port 与 Adapter：Settings 策略、SQLite ownership、最终档案 Workspace、Elfie Factory 与 Nest Session Port；具体 Adapter 全部由 Bootstrap 装配
一致性类别：额度校验与 ownership 预留共用一个 immediate SQLite 事务；候选仍只在进程内；接纳失败只补偿 Workspace 与 ownership 预留
Principal 与授权：/me 从已认证 AccountPrincipal 得到成员；每个候选集按 owner 隔离；SQLite 预留在同一事务内重新校验账户额度
超时、重试与幂等：候选 TTL 保持 30 分钟；不新增重试或状态机；接纳失败不保留半成品 Workspace 或 ownership 记录
旧实现删除清单：未版本化 /api/user 领养 Route；旧 candidates/config/generator/service；通用前端领养 API；直接 Engine 与 Persistence 构造
聚焦测试与端到端门：Feature、工作流、SQLite/档案/策略/Factory Adapter、严格 Route 与实时 Settings；浏览器旅程；默认 seed；最终存储链路；App/System/Storage 架构门
已删除的机器基线条目：全部旧 Adoption Feature db-path/具体 import；旧 Route 内部 import、松散/缺失模型和 /api/user/adoption 资源
状态：closed
```

### Orchestration：Observer

```text
业务域：orchestration/observer
缺口 ID：APP-001、APP-003、APP-004、APP-005、APP-006、APP-007、APP-009、APP-011
当前权威事实：Accounts 已认证 Session、Elfies 授权可见关系，以及现有 Nest Session 语义世界投影
路由与生产调用方：/api/v1/observer 的 Session、Interest、Frame 与高层 Intent；浏览器 Observer 界面；退出登录时撤销 capability
目标公共门面与模型：ObserverFacade，以及严格 Principal、Capability、Subscription、Frame、高层 Intent Command、Query、Result
Port 与 Adapter：消费方拥有的 World、Clock、Capability Port；根 Godot/Platform Adapter；Bootstrap 注入 Accounts、Elfies 和现有 Nest Session 投影
一致性类别：Capability 与投影队列只在进程内短期存在；世界读取不创建状态；不复制物理或 Runtime 事实
Principal 与授权：Capability 绑定已认证 Session 指纹；管理员只看授权房间投影，成员只看可见 Elfie；退出时撤销该登录的全部 Capability
超时、重试与幂等：Capability 过期沿用 Accounts Session TTL；保留现有有界投影与 Intent 限制；不重试；重复撤销幂等
旧实现删除清单：未版本化 Observer Route；Route 内 Registry 与 SQLite 授权查询；Nest Gateway Observer Session Registry；旧前端路径
聚焦测试与端到端门：Facade Capability/投影/授权；严格 Route 与退出；Godot/Platform Adapter；浏览器 Client；App/System/Gateway/Runtime 架构门
已删除的机器基线条目：旧 Observer Route 构造、具体 Persistence import、松散/缺失 Route 模型和全部 /api/observer 资源
状态：closed
```

## 当前到目标的迁移映射

规范性所有者只由应用架构契约定义。本表记录当前实现应进入哪里，以及迁移期位置何时
可以删除；本表不规定执行顺序。

| 当前目录或归组 | 目标所有者或工作流 | 相关缺口 | 删除门 |
| --- | --- | --- | --- |
| `app/features/accounts/` | `app/features/accounts/` | APP-002、APP-004、APP-006、APP-009 | 认证退出 FastAPI 和具体持久化/配置，全部调用方使用 accounts 公开门面。 |
| `app/features/administration/` | 账户行为进入 `accounts`；维护投影进入 `operations`；生命周期行为进入 `orchestration/lifecycle` | APP-002、APP-004、APP-006、APP-007 | 成员、Owner、Session、维护和生命周期调用方使用最终所有者，旧目录删除。 |
| `app/features/adoption/` | 业务决策进入 `adoption`；实时接纳和补偿进入 `orchestration/resident_admission` | APP-002、APP-004、APP-007、APP-009 | 领养只有一条事实/写路径，接纳只使用公开门面和 Port，删除直接 Engine、路径和持久化耦合。 |
| `app/features/chat/` 及 Interface 聊天持久化/投递 | `communication` 与 `orchestration/message_delivery` | APP-001、APP-004、APP-005、APP-006、APP-007、APP-011 | HTTP/WS 调用方复用一个门面，历史只有一个所有者，实时投递有回执，删除旧 Interface 持久化 helper。 |
| `app/features/elfie_profile/` 及 Interface 查询拼装 | `elfies` 授权查询/投影 Feature | APP-001、APP-004、APP-005、APP-009、APP-011 | 成员/管理员调用方使用一个类型化门面，App 不成为 Elfie Profile、认知或记忆的第二写入者。 |
| `app/features/nest_management/` 与 `app/features/nest_registration/` | `nest_management`；实时组合仍归 `orchestration/nest_session` | APP-001、APP-002、APP-004、APP-007 | 产品命令使用公开 Nest 边界，删除重复注册所有权和 `nest_registration`。 |
| `app/features/configuration/` 及 `ai_runtime/` 中的 App 管理行为 | `configuration/providers`、`food`、`capabilities`、`settings` | APP-001、APP-002、APP-004、APP-008、APP-009、APP-012 | 每个子域具有唯一门面、类型化所有者/写入者和 Port；技术模型/工具/存储实现进入根 Infrastructure 能力包并删除旧所有权。 |
| `app/features/setup/` | Setup 决策进入 `setup`；外部安装进入 `orchestration/setup_installation`；账户、配置、Nest 事实回归各自公开所有者 | APP-002、APP-003、APP-004、APP-007、APP-008、APP-009、APP-012 | Feature 不再持有线程和具体 Adapter，工作流通过注入 Port 可恢复，Setup 不再直接写其他领域事实。 |
| `app/features/embodiment/` | 注册/授权/关联进入 `bodies`；托管/归巢/切换进入 `orchestration/embodiment` | APP-002、APP-004、APP-007、APP-009、APP-010 | 只保留一套外部身体产品模型和 Port；持久化 Record、`db_path`、具体设备 Adapter 不再跨边界。 |
| `app/orchestration/` 平铺文件 | 按契约进入 `nest_session`、`message_delivery` 或具体实现所在的根 Infrastructure 能力包 | APP-002、APP-004、APP-007、APP-009 | 工作流只导入公开门面/自有 Port，技术 Adapter 退出 Orchestration，删除旧平铺所有权。 |
| `app/infrastructure/` 及 `ai_runtime/` 技术部分 | 根 `infrastructure/models`、`tools`、`godot`、`persistence`、`devices`、`communication`、`platform` | APP-001、APP-002、APP-003、APP-004、APP-012 | 每个迁移 Adapter 实现使用方 Port，由 Bootstrap 注入；旧路径持续缩减且不建立目标 `infrastructure/ai_runtime`。 |
| 历史和混合 API Route 归组 | 契约定义的 `app/interfaces/api/v1/` 资源目录 | APP-001、APP-003、APP-004、APP-005、APP-006、APP-011 | 全部真实调用方使用版本化资源，DTO 严格、构造已注入，删除被替代 Route/Client/夹具且不保留别名。 |

容量闭环、基于硬件的推荐及其他行为变化仍是独立产品任务，不能藏进架构迁移。
