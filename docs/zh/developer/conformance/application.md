# 应用架构一致性

> 本页是规范性[应用架构契约](../contracts/application)的可执行完成记录。契约定义
> 目标，本记录说明当前 App 结果，以及防止旧结构恢复的机器门。

## 当前状态

目标 App 目录与当前已经实现的 deny-all 规则均已落地，App 精确基线为空。但人工审查
发现了现有 Scanner 覆盖不到的契约缺口，因此 App 迁移仍为 **in progress**。
deny-all 为零只表示现有规则没有检出违规，不能证明整份 Application 契约已经关闭。

| ID | 严重度 | 状态 | 当前结果 |
| --- | --- | --- | --- |
| APP-001 | P0 | open | 大部分 Interface 已使用注入的公开边界，但 API Factory 与旧 WebSocket Gateway 仍导入或构造具体技术实现。 |
| APP-002 | P0 | closed | Feature 与 Orchestration 使用使用方拥有的 Port，不含禁止的框架或 Infrastructure 依赖。 |
| APP-003 | P0 | open | 大部分装配已进入 Bootstrap，但 API Factory 和多个 CLI 命令仍解析路径、初始化存储或构造技术服务。 |
| APP-004 | P1 | open | 两个 Workflow Model 仍导入 Feature 私有模型或 Gateway 内部模型，部分 Route 仍协调多个应用边界。 |
| APP-005 | P1 | open | HTTP Middleware/Dependency 仍返回 FastAPI `detail` 错误，公开 WebSocket Frame 仍含宽松字典。 |
| APP-006 | P1 | open | 认证已经类型化，但登出与安全设置副作用仍由 Route 协调。 |
| APP-007 | P1 | closed | 数据库、文件和外部工作流一致性由类型化 Port 与原子性/恢复测试表达。 |
| APP-008 | P1 | open | 旧 WebSocket Interface 仍持有线程、事件循环、Server 启动和停止。 |
| APP-009 | P1 | closed | 全部 App Python 包及公开调用方通过 App strict MyPy 门。 |
| APP-010 | P1 | closed | Bodies 与 Embodiment 只有一套产品事实、租约工作流和根设备 Adapter。 |
| APP-011 | P1 | closed | 产品 API 与真实调用方使用版本化资源目录，旧 Route 与别名已删除。 |
| APP-012 | P1 | open | Provider 初始化和 Accounts 缓存失效仍发生在一个明确产品用例之外。 |

## 待清理台账

以下编号只是 Conformance 跟踪标签，不是新增契约规则。清理必须保留已经从 `main`
迁移过来的行为；不得新增能力、别名、fallback Route、双写或第二事实源。

| 缺口 | 对应契约项 | 当前证据 | 完成门 |
| --- | --- | --- | --- |
| APP-G01 旧 WebSocket 生命周期 | APP-001、APP-003、APP-008 | `app/interfaces/api/ws_gateway*` 持有 8766 Server 的线程/事件循环，`app/interfaces/api/app.py` 负责启停。 | 先由唯一同源传输保留“用户消息 accepted 后投递、回复持久化与 fan-out”，再删除旧 Server 和全部生产调用方；不得保留别名或第二传输。 |
| APP-G02 API Factory 装配 | APP-001、APP-003 | `app/interfaces/api/app.py` 解析数据路径、初始化/Seed 持久化、构造通信 Infrastructure 并检查 Godot Web Bundle；`app/bootstrap/api.py` 也初始化数据库。 | Bootstrap 只保留一条装配/初始化路径；API Factory 只装 FastAPI、Middleware、Route 与注入的公开边界；删除 `app.state` 中无生产用途的具体对象。 |
| APP-G03 HTTP/WS 边界严格性 | APP-005 | 全局异常/CSRF、请求大小、Service Access 与多个 Dependency 返回 `detail` 错误；`app/interfaces/api/v1/realtime/bodies` 和旧 Gateway 消息暴露宽松 payload 字典。 | 认证、CSRF、校验、请求体过大、服务未装配与未知错误统一为 `{error:{code,message,details}}`；每种公开 WebSocket Frame 都有严格命名/可判别 DTO。 |
| APP-G04 Route 自有编排 | APP-004、APP-006、APP-012 | 登出同时调用 Accounts 与 Observer；安全设置先改 Settings 再让 Accounts 缓存失效；Mobile Access Route 直接读取 `ServiceAccessPolicy`。 | 每个入站用例只调用一个公开 Facade/Workflow 或一个注入的自有 Port，同时保留撤销、缓存即时生效和 Mobile URL 投影行为。 |
| APP-G05 CLI 具体依赖 | APP-003 | Owner、Lifecycle、Doctor 与 Uninstall 命令仍直接导入 data-home helper 或构造 `RuntimeLab`。 | 由 Bootstrap 通过公开边界或窄 Port 注入路径、诊断和卸载能力；现有命令、参数、输出与退出行为保持不变。 |
| APP-G06 私有模型导入 | APP-004 | Resident Admission 导入 `app.features.adoption.models.SpeciesId`；Nest Session 导入 `nest.godot_gateway.observer.ObserverSemanticEntity`。 | 改用所有者公开导出或使用方拥有的 Port Model；保持当前语义字段，不复制 Godot 几何或 Runtime 事实。 |
| APP-G07 Bootstrap 产品动作 | APP-003、APP-012 | Container 与 CLI 装配调用 `ensure_local_connection`，数据库初始化存在多个所有者。 | Bootstrap 只构造和连接依赖；产品状态创建进入明确 Feature/Setup 用例；数据库初始化只有一个所有者。 |
| APP-G08 机器门覆盖缺口 | APP-001、APP-004、APP-005、APP-008 | Scanner 只把 `app.infrastructure` 识别为 Infrastructure，未覆盖 Workflow 私有导入或 Interface 生命周期所有权；只检查 HTTP 注解，不检查 WebSocket DTO 与统一错误 envelope。 | 对应修复与聚焦规则一起落地；deny-all 保持为零且不新增 Baseline 例外，并用回归测试证明每种旧模式不能恢复。 |

## 必须遵守的清理顺序

1. APP-G01 与 APP-G02 都涉及 API 启动和生命周期所有权，必须原子关闭。
2. APP-G05 与 APP-G06 不依赖启动链，可在隔离 Worktree 中并行清理。
3. APP-G03、APP-G04 与 APP-G07 在装配收口后执行，避免再次产生多所有者。
4. APP-G08 随对应修复同步加入，最后用 deny-all 和聚焦行为回归关闭重新打开的契约项。

## 机器门

- `test/architecture/baselines/app_layer.py` 只包含空集合。
- `scripts/architecture/app_layer_scan.py --mode deny-all` 必须报告零违规。
- `test/architecture/test_app_layer_boundaries.py` 对精确基线执行依赖、构造、DTO 和
  Route 规则。
- strict MyPy 覆盖 `app/features`、`app/orchestration`、`app/bootstrap`、
  `app/interfaces/api` 与 `app/interfaces/cli`；不会用导入的历史实现弱化 App 结果。
- 各业务域测试镜像最终源码目录，覆盖授权、事务/恢复、Adapter 以及版本化 HTTP/WS
  契约。

这些是当前生效的机器门，不是 APP-G01 至 APP-G08 的豁免。在 APP-G08 关闭前，本台账
中的人工证据也是验收门的一部分。

仓库级 System Scanner 仍可报告另行登记的非 App 迁移债务；这些债务不得加入 App
基线。

## 最终依赖矩阵

| 调用方 | 可以依赖 | 禁止依赖 |
| --- | --- | --- |
| `app/interfaces/` | Feature/Orchestration 公开门面、Interface DTO、注入的请求依赖 | 具体 Infrastructure、Feature/Orchestration 私有模块、装配逻辑 |
| `app/features/` | 自有模型/Port、稳定 Core 门面；确属真实入站边界时可依赖另一领域公开门面 | FastAPI、具体 Infrastructure、任务/进程所有权、其他 Feature 内部 |
| `app/orchestration/` | Feature/Core 公开门面和工作流自有 Port | 具体 Infrastructure、HTTP DTO、Godot 物理或进程机制 |
| `app/bootstrap/` | App 公开边界和根 Infrastructure 具体 Adapter | 产品规则、传输 DTO 映射、第二份事实或默认值 |
| `infrastructure/` | 自己实现的使用方 Port 和低层技术库 | 其他具体 Adapter、Interface DTO、产品授权或工作流策略 |
| `elfie/` 与 `nest/` | 各自领域代码和自有 Port | App、具体 Infrastructure 或彼此导入 |

HTTP/WS/CLI 入站边界只调用一个公开门面。Command、Query、Result 归 App；出站 Port
Model 归使用方；HTTP DTO 归 Interface，不能成为持久化或领域模型。

## 最终目录地图

本地图只到文件夹级，不规定具体文件名。

```text
app/
├── features/
│   ├── accounts/
│   ├── adoption/
│   ├── bodies/
│   ├── communication/
│   ├── configuration/
│   │   ├── capabilities/
│   │   ├── food/
│   │   ├── providers/
│   │   └── settings/
│   ├── elfies/
│   ├── nest_management/
│   ├── operations/
│   └── setup/
├── orchestration/
│   ├── embodiment/
│   ├── lifecycle/
│   ├── message_delivery/
│   ├── nest_session/
│   ├── observer/
│   ├── resident_admission/
│   └── setup_installation/
├── interfaces/
│   └── api/
│       └── v1/
│           ├── auth/
│           ├── setup/
│           ├── me/
│           ├── elfies/
│           ├── admin/
│           ├── observer/
│           └── realtime/
└── bootstrap/
```

`/api/v1` 按资源和 Principal 组织，不按页面组织。`admin/`、`me/`、`elfies/`、
`observer/`、`realtime/` 可继续包含资源子目录。唯一未版本化 JSON 例外是轻量
`/api/health` 进程探针；HTML 页面和静态资源 Route 不属于产品 JSON 资源。

`app/infrastructure/` 只保留本地治理说明。生产 Adapter 位于根 `infrastructure/`
能力包，由 `app/bootstrap/Container` 统一创建和装配。

## 旧目录到最终所有者

| 已退役所有权 | 最终所有权 |
| --- | --- |
| `administration` | `accounts`、`operations`、`orchestration/lifecycle` |
| `chat` 和 Interface 自有投递/持久化 | `communication`、`orchestration/message_delivery`、根通信/持久化 Adapter |
| `elfie_profile` 和混合 Elfie 投影 | `elfies`；Food、Nest、Embodiment 保持独立资源 |
| `nest_registration` 与平铺 Nest 工作流 | `nest_management`、`orchestration/nest_session` |
| Feature 自有 Setup Installer 与平台工作 | `setup`、`orchestration/setup_installation`、根平台/模型 Adapter |
| Feature 自有 Embodiment 持久化/设备 | `bodies`、`orchestration/embodiment`、根设备/持久化 Adapter |
| `app/infrastructure` 产品实现 | 对应的根 `infrastructure/` 能力包 |
| 未版本化或按页面分组的产品 Route | 资源归属的 `app/interfaces/api/v1/` 目录 |

目标目录迁移已经落地，但在 APP-G01 至 APP-G08 清零前，Application Conformance
仍未关闭。后续清理只改变结构和所有权；不得删除现有行为，也不得新增产品能力、兼容
别名、fallback Route、双写或第二事实源。
