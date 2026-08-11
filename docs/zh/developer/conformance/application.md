# 应用架构一致性

> 本页是规范性[应用架构契约](../contracts/application)的可执行完成记录。契约定义
> 目标，本记录说明当前 App 结果，以及防止旧结构恢复的机器门。

## 当前状态

目标 App 目录已经落地，App 精确基线为空，人工登记的 APP-G01 至 APP-G08 已全部关闭。
增强后的 Scanner 已覆盖根 Infrastructure 导入、Workflow 私有导入、Interface Runtime
生命周期、宽松 WebSocket payload 与非标准错误响应。Application 迁移状态为
**closed**；仓库级 System 债务继续单独跟踪。

| ID | 严重度 | 状态 | 当前结果 |
| --- | --- | --- | --- |
| APP-001 | P0 | closed | Interface 使用注入的公开边界；API Factory 不再构造具体技术实现，旧 WebSocket Gateway 已删除。 |
| APP-002 | P0 | closed | Feature 与 Orchestration 使用使用方拥有的 Port，不含禁止的框架或 Infrastructure 依赖。 |
| APP-003 | P0 | closed | Bootstrap 是具体装配所有者；API 与 CLI 只消费注入的公开边界或窄 Port。 |
| APP-004 | P1 | closed | Orchestration 只消费 Feature 公开边界或使用方 Port Model，已登记的 Route 多边界协调已收口。 |
| APP-005 | P1 | closed | HTTP 错误使用统一 envelope，公开 WebSocket Frame 使用严格命名 DTO。 |
| APP-006 | P1 | closed | 认证、登出撤销与安全设置失效均通过类型化单入口 Workflow/用例表达。 |
| APP-007 | P1 | closed | 数据库、文件和外部工作流一致性由类型化 Port 与原子性/恢复测试表达。 |
| APP-008 | P1 | closed | Interface 不持有 Runtime 线程、事件循环或 Server 生命周期，8766 传输已退役。 |
| APP-009 | P1 | closed | 全部 App Python 包及公开调用方通过 App strict MyPy 门。 |
| APP-010 | P1 | closed | Bodies 与 Embodiment 只有一套产品事实、租约工作流和根设备 Adapter。 |
| APP-011 | P1 | closed | 产品 API 与真实调用方使用版本化资源目录，旧 Route 与别名已删除。 |
| APP-012 | P1 | closed | Provider 初始化、首个 Owner Seed 与 Accounts 缓存失效均为明确 Feature 用例。 |

## 已关闭清理台账

以下编号只是 Conformance 跟踪标签，不是新增契约规则。清理必须保留已经从 `main`
迁移过来的行为；不得新增能力、别名、fallback Route、双写或第二事实源。

| 缺口 | 对应契约项 | 关闭证据 | 永久门禁 |
| --- | --- | --- | --- |
| APP-G01 旧 WebSocket 生命周期 | APP-001、APP-003、APP-008 | 8766 Server 与全部 `ws_gateway*` 模块/调用方已删除；同源 Chat 保留 accepted 投递、持久化与 fan-out。 | Storage boundary 测试禁止恢复退役模块。 |
| APP-G02 API Factory 装配 | APP-001、APP-003 | Bootstrap 统一拥有 lifespan、存储/Setup 恢复、Service Access 与 Web/Godot 资源发现；API Factory 只装配注入的应用。 | 构造与禁止导入 Scanner 持续为零。 |
| APP-G03 HTTP/WS 边界严格性 | APP-005 | HTTP 失败使用 `{error:{code,message,details}}`；Body/Chat WebSocket Frame 使用严格 DTO。 | 错误 envelope 与宽松 WebSocket 扫描持续为零。 |
| APP-G04 Route 自有编排 | APP-004、APP-006、APP-012 | 登出、安全失效与 Mobile Access 各自只进入一个 Workflow/用例或注入投影 Port。 | Interface 构造与私有边界规则持续为零。 |
| APP-G05 CLI 具体依赖 | APP-003 | Data Home、Doctor、Uninstall 与终端展示机制均由 Bootstrap 注入；CLI 无根 Infrastructure 导入。 | Interface 禁止导入扫描覆盖 CLI 与根 Infrastructure。 |
| APP-G06 私有模型导入 | APP-004 | Adoption 使用公开 `SpeciesId`；Nest Session 拥有自己的 Observer 语义 Port Model。 | Workflow 私有导入与 Gateway 私有导入均被拒绝。 |
| APP-G07 Bootstrap 产品动作 | APP-003、APP-012 | 默认 Provider 连接和首个 Owner 创建均为明确 Feature Command；Schema 初始化只有一个所有者。 | Bootstrap 构造规则与 Feature 聚焦测试禁止直接 Adapter 产品动作。 |
| APP-G08 机器门覆盖缺口 | APP-001、APP-004、APP-005、APP-008 | Scanner 已覆盖全部登记缺口，精确基线保持为空。 | deny-all 与精确基线测试必须同时通过且不得增加例外。 |

## 已完成的清理顺序

1. APP-G01 与 APP-G02 已围绕 API 启动和生命周期原子关闭。
2. APP-G05 与 APP-G06 已清除 CLI 具体依赖和私有模型依赖。
3. APP-G03、APP-G04 与 APP-G07 在装配稳定后关闭严格边界与单所有者用例。
4. APP-G08 已把这些退役模式固化为零基线规则。

## 机器门

- `test/architecture/baselines/app_layer.py` 只包含空集合。
- `scripts/architecture/app_layer_scan.py --mode deny-all` 必须报告零违规。
- `test/architecture/test_app_layer_boundaries.py` 对精确基线执行依赖、构造、DTO 和
  Route 规则。
- strict MyPy 覆盖 `app/features`、`app/orchestration`、`app/bootstrap`、
  `app/interfaces/api` 与 `app/interfaces/cli`；不会用导入的历史实现弱化 App 结果。
- 各业务域测试镜像最终源码目录，覆盖授权、事务/恢复、Adapter 以及版本化 HTTP/WS
  契约。

这些机器门持续保证 APP-G01 至 APP-G08 关闭。本台账的人工说明不能豁免任何机器门
失败。

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

`app/infrastructure/` 已删除。生产 Adapter 及其局部治理规则位于根
`infrastructure/` 能力包，由 `app/bootstrap/Container` 统一创建和装配。

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

Application Conformance 已关闭。后续变更必须保持 APP-G01 至 APP-G08 为零，不得
恢复产品能力别名、fallback Route、双写或第二事实源。
