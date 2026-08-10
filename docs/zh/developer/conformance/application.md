# 应用架构一致性

> 本页是规范性[应用架构契约](../contracts/application)的可执行完成记录。契约定义
> 目标，本记录说明当前 App 结果，以及防止旧结构恢复的机器门。

## 当前状态

当前没有已登记的 App 架构例外。App 精确基线为空，deny-all 模式报告零违规。

| ID | 严重度 | 状态 | 关闭结果 |
| --- | --- | --- | --- |
| APP-001 | P0 | closed | Interface 只依赖注入的 Feature/Orchestration 公开边界，不依赖具体 Adapter。 |
| APP-002 | P0 | closed | Feature 与 Orchestration 使用使用方拥有的 Port，不含禁止的框架或 Infrastructure 依赖。 |
| APP-003 | P0 | closed | Bootstrap 是唯一组合根，API 与 CLI 入口接收已装配服务。 |
| APP-004 | P1 | closed | 跨域调用使用公开门面或自有 Port，不存在跨 Feature 私有导入。 |
| APP-005 | P1 | closed | 产品 JSON Route 使用严格命名 DTO、response model 和统一错误 envelope。 |
| APP-006 | P1 | closed | Interface 认证严格 Principal，应用服务负责授权与业务错误。 |
| APP-007 | P1 | closed | 数据库、文件和外部工作流一致性由类型化 Port 与原子性/恢复测试表达。 |
| APP-008 | P1 | closed | 后台与平台工作由注入的 Runner/Adapter 和 lifecycle 编排拥有。 |
| APP-009 | P1 | closed | 全部 App Python 包及公开调用方通过 App strict MyPy 门。 |
| APP-010 | P1 | closed | Bodies 与 Embodiment 只有一套产品事实、租约工作流和根设备 Adapter。 |
| APP-011 | P1 | closed | 产品 API 与真实调用方使用版本化资源目录，旧 Route 与别名已删除。 |
| APP-012 | P1 | closed | 配置、Secret 与缓存所有权类型化、单写入并显式注入。 |

## 机器门

- `test/architecture/baselines/app_layer.py` 只包含空集合。
- `scripts/architecture/app_layer_scan.py --mode deny-all` 必须报告零违规。
- `test/architecture/test_app_layer_boundaries.py` 对精确基线执行依赖、构造、DTO 和
  Route 规则。
- strict MyPy 覆盖 `app/features`、`app/orchestration`、`app/bootstrap`、
  `app/interfaces/api` 与 `app/interfaces/cli`；不会用导入的历史实现弱化 App 结果。
- 各业务域测试镜像最终源码目录，覆盖授权、事务/恢复、Adapter 以及版本化 HTTP/WS
  契约。

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

本次关闭只改变结构和所有权，不新增产品能力、兼容别名、fallback Route、双写或第二
事实源。
