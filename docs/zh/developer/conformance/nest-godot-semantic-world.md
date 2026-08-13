# Nest–Godot 语义世界一致性

> [Nest–Godot 语义世界契约](../contracts/nest-godot-semantic-world)的临时迁移台账。
> 它记录当前实现缺口，不降低或重定义目标。全部条目关闭后，删除中英文台账及其注册项。
> 强制执行顺序和每卡验收证据见[迁移规约](./nest-godot-semantic-world-migration)。

## 当前缺口

| ID | 严重度 | 状态 | 当前偏差 | 关闭条件 |
| --- | --- | --- | --- | --- |
| NGW-001 | P0 | open | `nest/` 目前围绕宽泛 state/engine/interaction 容器组织；`InteractionHub` 混合虚拟说话、用户消息、碰撞和触觉缓冲，没有形成已经接受的四个功能所有者。 | 真实 Nest Facade 委托给已实现的空间设施、生活规则、时间环境和精灵与巢交互所有权，不建立空包；用户消息留在 Communication，身体接触离开 Nest。 |
| NGW-002 | P0 | open | `NestRuntimeEventRouter` 会先把多类 Runtime 事件送入每个 Body transport，再单独处理说话或触觉；事件第一次路由并不由语义类型和目标决定。 | 每个 Runtime 事件投递前已经分类；actor 回执/感知、语义结果、环境事实、Nest 事件和生命周期事件各有一条类型化路径与显式目标，并有聚焦的禁止跨路由测试。 |
| NGW-003 | P0 | open | Native Godot Body Sensor 丢弃 Runtime 输入，而触觉又经 Nest 重建；事件身份可能变化，Python 还根据归一化强度伪造力值。 | Godot 身体感知只进入所属 Body，并保留原 event/cause 身份和物理值；`NativeSensors` 排队类型化输入；删除 Nest 触觉兼容路径和伪造物理量。 |
| NGW-004 | P0 | open | 说话文字穿过 Godot 命令/事件协议，听众仅用同 Zone 近似，同一次发生还可能同时经过 Body 广播与 Nest 投递。 | Nest 保存 utterance 内容和表露情绪；Godot 只接收不透明 occurrence ID，并按已接受物理模型返回空间可达；Nest 为每个最终听者幂等地产生一条定向 `HeardUtterance`。 |
| NGW-005 | P1 | open | 虚拟视觉仍依赖 Camera 截图/路径猜测，没有 actor 作用域、考虑遮挡的 `VisibleSet` 到 `SemanticVisualScene` 路径。 | Godot 为一个 actor 和 observation ID 产生有界类型化可见实体；Nest 做一次批量语义关联并投递一条定向视觉感知，不使用截图、VLM 或持久周围列表。 |
| NGW-006 | P0 | open | 尚无完整 `SemanticBodyIntent` → 已解析目标 → 物理结果 → `SemanticActionResult` 工作流；Home 查询与身体执行不是一次关联行动周期。 | 一个已授权 intent 在 Nest 规则解析与 Godot 执行间保留 actor/intent 身份，不要求第二个 Brain Turn，只产生一个语义终态，而且 Nest 不能自行创建或改写。 |
| NGW-007 | P1 | open | Nest 时钟只推进 elapsed seconds；Godot 没有灯、门、可移动设施及生活阶段同步所需的统一环境命令/事实表面。 | 时间与环境拥有阶段和期望状态；有状态世界对象接收类型化命令并返回实际事实/结果；新 Runtime generation 只接收当前期望状态，不重放过期副作用。 |
| NGW-008 | P1 | open | Godot actor catalog 仍携带 Home 元数据，Nest 又保存超出规则最小需要的宽泛姿态/actor mirror，家庭与物理 authority 边界模糊。 | Home 与归属只留在 Nest；Godot 只接收已解析 spawn/action 目标；Nest 保留的每个物理投影都带来源与 generation、保持最小，并在 authority 变化时失效。 |
| NGW-009 | P1 | open | 多数场景家具缺少稳定对象语义和窄状态行为，环境对象变化还不能在不泄漏 NodePath 或坐标的前提下一致表达。 | Godot 场景 Manifest 为必需房间、区域、Anchor 与交互对象发布稳定 ID；Nest 拥有以它们为键的无坐标语义目录；只有有状态对象编写窄脚本；Manifest、命令和事实不含 NodePath 或不必要坐标。 |
| NGW-010 | P0 | open | `WorldRuntimePort` 和协议模型把世界配置、actor 同步、身体事件与互动事件混在一起，没有形成已接受的语义线路边界。 | 消费方拥有的类型化能力区分直接 Body、语义行动、视觉、说话、环境与 Runtime 控制，同时允许一个 Gateway 实现它们；Bootstrap 接线和聚焦契约测试证明没有第二 Gateway 或 authority。 |

## 迁移顺序

强制顺序是[详细迁移规约](./nest-godot-semantic-world-migration)中的 `NG-M01` 至
`NG-M15`：

1. 先建立协议身份、事件分类和直接 Body 输入；
2. 再建立空间与设施、生活规则、持久化和时间与环境；
3. 从 Nest 移除用户消息归属，并建立 Godot 语义场景；
4. 逐条完成说话/事件、结构化视觉和语义行动；
5. 加入环境对象/恢复，收口窄 Port，最后才做结构整理；
6. 在独立仅治理改动中删除临时一致性材料。

本概览不够具体时，以详细迁移卡为准。任何卡都不得提前关闭缺口、预建空 Package、
保留被替换路径，或引入兼容/双存储。

## 现有机器覆盖

永久 System Scanner 已经禁止 Nest import Elfie、App 和具体 Infrastructure，也禁止
Nest 直接 import 技术传输。Contract Registry、双语版本检查及聚焦 System/Gateway/
Observer 架构测试共同治理本目标。语义事件所有权和路由唯一性需要在后续迁移切片中
加入聚焦产品测试；本治理变更不声称这些测试或行为已经存在。
