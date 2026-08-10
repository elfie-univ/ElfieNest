# 系统架构一致性台账

> 本文是规范性[系统架构契约](../contracts/system)的临时迁移台账，只记录当前偏差，
> 不改变目标。全部条目及其精确机器基线关闭后删除本页。

## 当前缺口

| ID | 严重级别 | 状态 | 当前偏差 | 关闭门槛 |
| --- | --- | --- | --- | --- |
| SYS-001 | P0 | open | 技术 Adapter 分散在 `app/infrastructure/`、`ai_runtime/`、`godot_runtime/`、`nest/godot_gateway/` 和 Elfie/Nest 具体存储或传输代码中；目标根 `infrastructure/` 尚不存在。 | 技术实现分别进入 `models`、`tools`、`persistence`、`godot`、`devices`、`communication` 或 `platform`；旧技术根和兼容 import 删除，根 `godot_project/` 保持不动。 |
| SYS-002 | P0 | open | Elfie Memory/Profile 会构造 SQLite、YAML 和路径实现，Factory/Runtime 仍知道具体存储或 Godot 传输细节。 | Elfie 只保留语义模型、算法、Facade 和 Port；Infrastructure 实现存储/身体/渠道 Adapter；Bootstrap 注入；聚焦 Elfie 测试使用 Fake 且无技术 I/O。 |
| SYS-003 | P0 | open | Nest 内含具体 WebSocket、JSON、环境、Bundle 和 Godot 传输实现。 | Nest 只保留世界语义、规则、Facade 和 Port；Infrastructure 拥有协议/宿主 Adapter；全局事实经过 Nest，actor 回执走身体通道。 |
| SYS-004 | P0 | open | 具体构造散落在 App Route、Feature、Factory 和 Orchestration；`app/bootstrap/` 尚不是完整组合根。 | Bootstrap 构造全部跨系统具体 Adapter 并注入系统 Port；产品/Runtime 代码不再有 Service Locator 或具体 Adapter 构造。 |
| SYS-005 | P1 | open | 系统 Facade 和出站 Port 已部分存在，但没有一份稳定强类型边界清单；部分路径仍使用 `Any`、具体路径或协议细节。 | Elfie/Nest Facade，以及 Food、模型、工具、身体、世界、通信和持久化 Port 全部使用强类型模型；重复或技术命名的边界 API 删除。 |
| SYS-006 | P1 | open | 当前部分 Core 测试仍依赖真实 Adapter，系统级架构债尚未全部进入精确棘轮。 | Core 测试使用 Fake/内存 Port，Adapter 测试分离，Bootstrap 有装配测试，迁移路径有端到端证据，并且系统精确基线清零。 |
| SYS-007 | P0 | open | 当前 `ai_runtime/` 把 Provider/模型 Adapter、Food 管理、报告、持久化、工具执行和推理协调混在一个已废弃的目标所有者中。 | Provider/模型访问进入 `infrastructure/models`，工具执行进入 `infrastructure/tools`，持久化实现消费方 Port，App 拥有 Food 管理与报告，Elfie 直接使用注入的 `FoodPort`、`ModelPort`、`ToolPort`；全部调用方迁移后删除旧根，不整体移动。 |

## 机器覆盖

当前系统精确 Scanner 与 `system_layer.py` 基线只覆盖 `SYS-002`、`SYS-003`：Elfie 和
Nest 的禁止跨根依赖与直接技术依赖。其他架构测试保护现有 Runtime、Observer、存储、
Godot 和工程结构安全规则，但不能据此关闭其余目标条目。`SYS-001`、`SYS-004`、
`SYS-005`、`SYS-006`、`SYS-007` 仍然需要完整迁移调用链、聚焦行为证据和维护者审查，
不能只因为 Scanner 通过就标记关闭。

## 迁移顺序

本台账不授权一次性移动全仓。每次只迁移一个完整边界：

1. 锁定 Facade/Port 和事实所有者；
2. 增加目标 Adapter 与 Bootstrap 装配；
3. 迁移全部生产调用方和聚焦测试；
4. 删除旧实现与 import 路径；
5. 缩减机器基线，只关闭受影响条目。

建议依赖顺序为：Bootstrap 基础、Elfie Food/模型/工具 Port、模型与工具 Adapter、
Elfie 持久化、Nest 持久化、Godot Gateway/宿主接入、Nest 世界 authority、外部设备
与通信，最后处理剩余平台能力。App 领域迁移继续由
[应用架构一致性台账](./application)单独跟踪；当前 `ai_runtime/` 行为债务在迁移包
删除前继续由 [AI Runtime 一致性台账](./ai-runtime)记录。
