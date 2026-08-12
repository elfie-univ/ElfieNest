# 系统架构一致性台账

> 本文是规范性[系统架构契约](../contracts/system)的临时迁移台账，只记录当前偏差，
> 不改变目标。全部条目及其精确机器基线关闭后删除本页。

## 当前缺口

| ID | 严重级别 | 状态 | 当前偏差 | 关闭门槛 |
| --- | --- | --- | --- | --- |
| SYS-001 | P0 | closed | 根 `infrastructure/` 已拥有目标能力目录、Data Home、持久化、模型/Provider 与 Runtime 技术、工具技术、终端宿主、Godot Gateway、authority 宿主和产物校验；原 `app/infrastructure/`、`godot_runtime/` 与 `ai_runtime/` 根不存在，Elfie/Nest 及跨能力所有权机器门禁均已清零。 | 保持退役根目录不存在，并保持系统 deny-all 扫描器与 Port/Adapter 棘轮通过。 |
| SYS-002 | P0 | closed | Elfie Memory/Profile 与 Factory 切片已不再构造 SQLite/YAML/路径实现，也不再知道具体 Godot 传输；存储、Profile、工具 Adapter 位于 Infrastructure 并由 Bootstrap 注入。 | Elfie/Nest 技术 import 精确基线清零；Brain Memory 使用 Fake，Infrastructure 拥有持久化集成测试，类型化 Factory/ToolPort 装配测试通过。 |
| SYS-003 | P0 | closed | 原始 WebSocket、JSON、Bundle、协议与 Session 已归位 `infrastructure/godot/gateway/`；Nest 已无 Gateway 传输或 Observer 实现目录。Nest Session 消费 App 自有的 Observer 语义 Port Model，`infrastructure/godot/observer_world.py` 只翻译强类型世界事实和高层意图。 | 保持退役的 `nest/godot_gateway/` 路径不存在，并由现有 Gateway 与 Observer 边界测试持续保护世界语义、状态、事件和协议行为。 |
| SYS-004 | P0 | closed | 生产服务与交互脚本从 `app/bootstrap/` 获取 Runtime、存储、Nest Session 和 Elfie 恢复装配；Bootstrap 构造鉴权管理 WebSocket Gateway 并注入 API 启停回调；Runtime、管理 Gateway 与 Godot 通道只经 Lifecycle 启停。Interface 只保留协议映射。 | 永久架构测试持续禁止 Interface 构造具体实现，并断言 API lifespan 把通道控制委托给 Lifecycle。 |
| SYS-005 | P1 | closed | 系统 Facade 和出站 Port 已有一份严格的机器清单。Port 方法使用命名模型或受限 JSON 值；跨能力具体 Adapter 与未经校验的边界对象都会被拦截。 | 保持 `test_system_ports_contract.py`、App/Elfie/Nest 边界测试和严格聚焦类型检查通过。 |
| SYS-006 | P1 | closed | Bootstrap 装配、Infrastructure 跨能力组合、通信入站和打包所有权已与系统精确 Scanner 一起永久棘轮。Core/Adapter 分离及迁移端到端证据由聚焦和完整架构测试覆盖。 | 保持 Bootstrap、跨能力、打包和 deny-all 门禁通过；系统精确基线保持清零。 |
| SYS-007 | P0 | closed | 原 `ai_runtime/` 根和 import 已清零；Provider/模型客户端与 Runtime 技术位于 `infrastructure/models/`，工具技术位于 `infrastructure/tools/`，Food 策略位于 App Food Feature，只读 Food Port 位于 Elfie。Runtime 执行与模型验证路径现在接收 Brain 所有的 ToolPort，不再在调用链中构造具体工具插件。 | Provider → Food → 模型 → 工具 → 保底粮、限定作用域工具执行及 Runtime/Tool 聚焦端到端路径保持通过；不得恢复 `infrastructure/ai_runtime/` 或宽 Runtime 工具桥。 |

## 当前执行边界

当前最高优先级是**顶层物理所有权与跨根边界稳定**。本批允许关闭 Bootstrap、Data
Home、打包与 Lifecycle 装配缺口；等价迁移现有 Godot 宿主/Gateway 和其他纯技术
实现；迁移其调用方；只有旧路径调用方清零后才能删除旧路径。

Elfie 与 Nest 内部算法、状态机、子模块交互和用户可见行为全部保持不变。本批尤其
不重设计认知、Memory、Skills、模型/工具循环、Nest 世界语义、Resident 同步或事件
传播。如果旧模块无法在此约束下等价移动，就继续登记为后续 Elfie 或 Nest 内部专项，
不能为了清空目录强行塞进 Infrastructure。

## 机器覆盖

当前系统精确 Scanner 与 `system_layer.py` 基线覆盖 `SYS-002`、`SYS-003`：Elfie 和
Nest 的禁止跨根依赖与直接技术依赖。`test_system_ports_contract.py` 对严格 Port 注解、
跨能力 peer import、认证通信入站和 Bootstrap 组合进行棘轮。Bootstrap、Runtime、
Observer、存储、Godot、打包和工程结构测试提供其余装配与行为证据。系统精确基线与
deny-all 扫描均已清零。

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
