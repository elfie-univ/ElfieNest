# 系统架构一致性台账

> 本文是规范性[系统架构契约](../contracts/system)的临时迁移台账，只记录当前偏差，
> 不改变目标。全部条目及其精确机器基线关闭后删除本页。

## 当前缺口

| ID | 严重级别 | 状态 | 当前偏差 | 关闭门槛 |
| --- | --- | --- | --- | --- |
| SYS-001 | P0 | in progress | 根 `infrastructure/` 已拥有目标能力目录、Data Home、持久化、模型/Provider 与 Runtime 技术、工具技术、终端宿主、Godot Gateway、authority 宿主和产物校验；原 `app/infrastructure/`、`godot_runtime/` 与 `ai_runtime/` 根已消失。剩余所有权债仅限 Observer/Core 残留。 | 保持已退役根目录不存在，并在不引入兼容 import 的前提下关闭单独登记的 Elfie/Nest 残留。 |
| SYS-002 | P0 | open | Elfie Memory/Profile 会构造 SQLite、YAML 和路径实现，Factory/Runtime 仍知道具体存储或 Godot 传输细节；这是已登记的 Elfie 内部债，不属于当前顶层归位批次。 | Elfie 只保留语义模型、算法、Facade 和 Port；Infrastructure 实现存储/身体/渠道 Adapter；Bootstrap 注入；聚焦 Elfie 测试使用 Fake 且无技术 I/O。 |
| SYS-003 | P0 | in progress | 原始 WebSocket、JSON、Bundle、协议与 Session 已归位 `infrastructure/godot/gateway/`，Nest 已无 WebSocket import；`nest/godot_gateway/observer.py` 仍是被 Nest Session 私有消费的已登记混合语义投影。 | APP-G06 用所有者公开导出或消费方 Port Model 替换最后一个 Observer 私有模型 import，随后删除残留 Nest 目录；世界语义、状态、事件和协议行为不得改变。 |
| SYS-004 | P0 | closed | 生产服务与交互脚本从 `app/bootstrap/` 获取 Runtime、存储、Nest Session 和 Elfie 恢复装配；Bootstrap 构造鉴权管理 WebSocket Gateway 并注入 API 启停回调；Runtime、管理 Gateway 与 Godot 通道只经 Lifecycle 启停。Interface 只保留协议映射。 | 永久架构测试持续禁止 Interface 构造具体实现，并断言 API lifespan 把通道控制委托给 Lifecycle。 |
| SYS-005 | P1 | open | 系统 Facade 和出站 Port 已部分存在，但没有一份稳定强类型边界清单；部分路径仍使用 `Any`、具体路径或协议细节。 | Elfie/Nest Facade，以及 Food、模型、工具、身体、世界、通信和持久化 Port 全部使用强类型模型；重复或技术命名的边界 API 删除。 |
| SYS-006 | P1 | open | 现有永久规则只覆盖部分目标：系统精确 Scanner 主要检查 Elfie/Nest 技术 import，尚未完整棘轮 Bootstrap 装配、Infrastructure 跨能力组合和打包所有权。 | Core 测试使用 Fake/内存 Port，Adapter 测试分离，Bootstrap 有装配测试，迁移路径有端到端证据，并且系统精确基线清零。 |
| SYS-007 | P0 | in progress | 原 `ai_runtime/` 根和 import 已清零；Provider/模型客户端与 Runtime 技术进入 `infrastructure/models/`，工具技术进入 `infrastructure/tools/`，Food 策略位于 App Food Feature，只读 Food Port 位于 Elfie。等价搬迁后的 Runtime 协调器与实验台内部仍组合多个具体 Infrastructure 能力。 | 保持 Provider → Food → 模型 → 工具 → 保底粮行为不变，再只用窄注入 Port 替换剩余 Infrastructure 跨能力具体构造；不得重设计 Elfie 认知或恢复旧根。 |

## 当前执行边界

当前最高优先级是**顶层物理所有权与跨根边界稳定**。本批允许关闭 Bootstrap、Data
Home、打包与 Lifecycle 装配缺口；等价迁移现有 Godot 宿主/Gateway 和其他纯技术
实现；迁移其调用方；只有旧路径调用方清零后才能删除旧路径。

Elfie 与 Nest 内部算法、状态机、子模块交互和用户可见行为全部保持不变。本批尤其
不重设计认知、Memory、Skills、模型/工具循环、Nest 世界语义、Resident 同步或事件
传播。如果旧模块无法在此约束下等价移动，就继续登记为后续 Elfie 或 Nest 内部专项，
不能为了清空目录强行塞进 Infrastructure。

## 机器覆盖

当前系统精确 Scanner 与 `system_layer.py` 基线只覆盖 `SYS-002`、`SYS-003`：Elfie 和
Nest 的禁止跨根依赖与直接技术依赖。其他架构测试保护现有 Runtime、Observer、存储、
Godot 和工程结构安全规则，但不能据此关闭其余目标条目。`SYS-001`、`SYS-005`、
`SYS-006`、`SYS-007` 仍然需要完整迁移调用链、聚焦行为证据和维护者审查，
不能只因为 Scanner 通过就标记关闭。

## 迁移顺序

本台账不授权一次性移动全仓。每次只迁移一个完整边界：

1. 锁定 Facade/Port 和事实所有者；
2. 增加目标 Adapter 与 Bootstrap 装配；
3. 迁移全部生产调用方和聚焦测试；
4. 删除旧实现与 import 路径；
5. 缩减机器基线，只关闭受影响条目。

当前批次采用更窄的依赖顺序：

1. 冻结现有行为、公开边界和 Lifecycle 所有者；
2. 关闭目标 Infrastructure 包所需的 Bootstrap、Data Home 和打包基础；
3. 把 Godot 宿主/产物与 Gateway/协议技术等价迁到 `infrastructure/godot/`，切换全部
   调用方后删除旧根；
4. 棘轮已经完成的 `ai_runtime/` 拆解：模型与 Runtime 技术在
   `infrastructure/models/`，工具在 `infrastructure/tools/`，Food 策略在 App
   Feature，只读 Port 在 Elfie；
5. 单独审查剩余 Elfie/Nest 内部债务，不得恢复已退役根目录；
6. 只缩减已经实际消失的精确基线；缺失的永久规则必须等实时违规清零后，以独立治理
   变更加入。

App 领域迁移继续由[应用架构一致性台账](./application)单独跟踪。Elfie 与 Nest
内部清理不属于本次顶层迁移。
