# Nest–Godot 语义世界契约

**契约版本：** 1.0
**采用日期：** 2026-08-13
**适用范围：** `nest/`、Godot 语义边界及受影响的 App 编排

> **规范性目标。** 本契约定义 Nest 内部事实所有权、与权威 Godot 世界的语义交互，
> 以及面向 Elfie 的唯一事件路由。当前差距记录在
> [Nest–Godot 一致性台账](../conformance/nest-godot-semantic-world)，批准后的迁移卡顺序由
> 临时[迁移规约](../conformance/nest-godot-semantic-world-migration)固定。

全仓所有者和依赖方向仍由[系统架构契约](./system)治理。本契约只细化该边界，不创建
新的根模块、物理 authority、组合根或生命周期所有者。

## Authority 模型

| 部分 | 拥有 | 不得拥有 |
| --- | --- | --- |
| Elfie | 个体意图、认知、身体行动发起、感知、情绪、记忆与反应 | 家庭规则、3D 几何或环境对象 authority |
| Nest | 家庭语义、规则、时间/环境意图、语义交互和 Nest 事件 | 独立的 Elfie 身体意图、物理模拟或真实 Elfie 对象 |
| Godot | 场景、位置、物理身体、导航、碰撞、可见性、可听性、渲染和实际执行 | Home、归属、家庭规则、说话内容或 Elfie 认知 |
| App | 装配、跨 authority 对象查找、Runtime 生命周期与恢复 | 第二套世界模型、日常身体控制或 Nest 业务决策 |

一套运行中的 ElfieNest 只有一个 Nest 和一个当前权威 Godot Runtime generation。
一个事实只有一个语义所有者；其他部分只能保存类型化、带来源且受 revision 限定的投影。

## Nest 功能所有权

Nest 有四个一级功能所有者：

| 所有者 | 拥有 | 不得拥有 |
| --- | --- | --- |
| 空间与设施 | Nest ID，以及以 Godot 拥有的稳定房间/区域/Anchor/对象 ID 为键的无坐标语义目录、设施类型、用途、能力和规则所需的最小离散环境投影 | 物理对象 ID 的创建、坐标、碰撞体、路径、逐帧运动、居民归属或动态周围列表 |
| 巢内生活规则 | 居民 ID、Home、归属、共享、预约、占用、访问、环境覆盖和事件受众规则 | 真实 Elfie 对象、物理可达性、说话内容存储或消息传输 |
| 时间与环境 | 巢内时钟、暂停/倍率、生活阶段、定时环境规则和期望环境状态 | 单只 Elfie 的能量/睡眠决定、渲染参数、物理 Tick 或 Actor 命令 |
| 精灵与巢交互 | 短期 observation、utterance、semantic intent 关联，以及语义视觉、虚拟听觉和语义行动拼装 | 其他三个所有者的源事实、物理计算、自主身体决定或具体传输 |

这些是概念和行为所有者，不要求建立四个 Package、进程、数据库或预创建目录。只有
存在真实状态、契约或行为时才建立物理模块。稳定 `Nest` Facade 继续作为聚合入站边界，
对外提供类型化用例而非可变内部子模块。

`nest/` 只保存居民 ID 和巢内状态，不持有或构造真实 Elfie。真实 Elfie 实例与 Nest
状态只在 App Orchestration 中组合。

## 公共 Nest 事件机制

事件机制横贯四个所有者，但不是第五个业务模块。

- 事实的语义所有者产生事件；
- 只有需要家庭规则时，巢内生活规则才解析受众；
- 事件路由器接收已经分类的事件，并向显式目标 ID 投递一次；
- 广播只是“全部有效居民”或“明确居民集合”等受众形态，绝不是 Runtime 事件默认路由；
- 一个语义事件只有一条投递路径；一次物理原因产生的不同事实使用不同事件 ID 和类型，
  可以共享一个 cause ID；
- 重试保留事件身份；Runtime generation 和 world revision 用于拒绝过期物理输入，不能
  生成替代事件身份。

类型化 Nest 事件 Envelope 按需携带：

- 稳定 `event_id`、事件类型、事实所有者和发生时间；
- 可选 `cause_id` 以及原请求、intent、utterance 或 observation ID；
- 显式目标居民 ID，或等待规则解析的策略型受众选择器；
- Godot 来源事实的 Runtime ID、generation 和 world revision；
- 不含协议帧、坐标或未校验字典的有界类型化 Payload。

所有者事件示例包括：空间与设施产生设施状态变化；巢内生活规则产生访问规则变化；
时间与环境产生安静时段变化；精灵与巢交互产生 `HeardUtterance`、
`SemanticVisualScene` 或 `SemanticActionResult`。

原始身体回执、触觉/本体感知、原始 `VisibleSet`、原始环境事实和 Runtime 生命周期帧
都不是 Nest 广播。

## 语义路径

| 路径 | 方向 | 规则 |
| --- | --- | --- |
| `NestQuery` | Elfie ↔ Nest | 纯家庭语义查询，不立即执行物理行为 |
| `DirectBodyChannel` | Elfie Body ↔ Godot | 目标已知且不需要当前家庭语义解析；回执和身体感知只返回所属 Elfie |
| `SemanticAction` | Elfie → Nest → Godot → Nest → Elfie | 一个已授权 intent 覆盖确定性目标解析、物理执行和一个语义结果，不要求第二个 Brain Turn |
| `SemanticVision` | Elfie → Nest → Godot → Nest → Elfie，或 Godot → Nest → Elfie | 主动观察是一次完整关联请求；Godot 也可上报有界的重大变化。Godot 计算物理可见实体集合，Nest 只补家庭含义并产生一条定向语义视觉感知 |
| `SpeechBridge` | Elfie → Nest → Godot → Nest → 目标 Elfie | Nest 保存内容和表露情绪，Godot 把物理听众候选返回 Nest，规则过滤居民，Nest 产生定向听觉事件 |
| `EnvironmentChannel` | Nest ↔ Godot 世界对象 | Nest 发出期望环境命令，Godot 返回实际离散事实与命令结果 |
| `RuntimeControl` | App Lifecycle ↔ Godot Host/Gateway | 只处理启动、就绪、generation、健康、断线和恢复 |

是否需要寻路不能决定路径。寻路永远属于 Godot；只有必须解析“我的、共享的、可用的、
允许的”等当前家庭语义时，请求才经过 Nest。

Nest 只有在命令保留原始 Elfie intent 身份、actor 身份和授权时，才能转发已解析 Actor
目标。Nest 不能独立创建、定时触发、恢复或改写 Actor 行为。时间和家庭规则可以独立
命令灯、门等环境对象，因为那是 Nest 拥有的世界意图，不是 Elfie 身体意图。

## 结构化虚拟感知

MVP 虚拟视觉不为每只 Elfie 渲染主观 Camera Viewport，也不走截图到 VLM 推理。Godot
根据 actor Transform、视野、距离、遮挡和当前物理状态计算有界 `VisibleSet`；Nest 将
稳定语义 ID 与设施含义、归属和规则拼装，向对应 Elfie 产生一条
`SemanticVisualScene`。Nest 不持久化每只 Elfie 的周围对象列表，也不重新计算可见性。

MVP 虚拟听觉不走 TTS → 3D Audio → STT。Nest 保存 utterance 文字、表露情绪和身份；
Godot 只返回本次发生的物理听众候选；Nest 应用居民与传播规则，向每个最终听者产生
`HeardUtterance`。可选 TTS 或 3D 音频只供人类观察者呈现，不能证明 Elfie 听见。

## Godot 边界与项目逻辑

Godot 继续作为场景对象、虚拟身体、物理/导航、空间查询和呈现的物理 authority。
SceneTree、CharacterBody3D、碰撞、NavigationServer3D、动画、Area3D、Ray/空间查询、
音频播放器、渲染和 WebSocket 传输等引擎原语直接复用。

ElfieNest 自有 Godot 代码只补语义胶水和有状态行为：

- Actor Controller 把高层命令映射到移动/动画，并产生定向回执与身体感知；
- World Controller 发布语义场景/对象清单、执行环境命令，并计算 `VisibleSet` 与声音可达；
- Runtime Endpoint 校验协议身份，并通过共享认证连接产生已分类的类型化 Frame；
- 只有门、灯、可移动或特殊设施等有状态交互对象才编写窄脚本。

Godot 不保存 Home、居民归属、家庭权限或说话内容。Python 不复制坐标、几何、导航、
碰撞、遮挡、声学可达性或物理帧状态。

物理房间、区域、Anchor 和对象的稳定 ID 随 Godot 场景编写，并由其 Manifest
发布；空间与设施只拥有以这些 ID 为键的无坐标家庭语义目录与含义，不创建
竞争的物理身份，也不把 NodePath 暴露为身份。

## 投递、编排与依赖

Nest 与 Elfie 不得互相 import，也不得导入具体 Godot Infrastructure。消费方拥有的类型化
Port 由 `infrastructure/godot/` 实现，并由 Bootstrap 接线。一个具体 Gateway 可以实现
多个窄能力；共享连接不会合并语义线路。

App Orchestration 可以把真实 Elfie 实例与 Nest 居民 ID 关联，并把已经授权的类型化感知
投递给目标聚合；它不选择家庭含义、不编造物理事实，也不代理直接身体流量。只有 App
Lifecycle 可以启动、停止和恢复 Godot authority。

协议帧、WebSocket 状态、进程对象和 Runtime 凭据不得进入 Nest。领域命令、结果和事件
不得暴露 NodePath、原始坐标、数据库 Record 或任意 JSON。

## 状态与恢复

| 状态 | Authority 与恢复规则 |
| --- | --- |
| 居民、Home、设施语义和家庭规则 | 通过 Nest 自有 Repository Port 恢复的持久 Nest 状态 |
| 巢内时间、生活阶段和期望环境状态 | 持久 Nest 状态；新 Godot generation 就绪后重新同步 |
| actor 位置、速度、姿态、导航和对象实际状态 | 当前 Godot/Body Runtime；generation 改变后旧 Python 投影失效 |
| 规则所需的离散环境投影 | 带来源 Nest 投影；generation/revision 改变后失效并重建 |
| utterance、observation 和 semantic intent 关联 | 短期 Nest 交互状态；换代时中断或对账，绝不盲目重放 |
| 直接身体命令与回执 | 所属 Elfie Body 与 Godot；不通过 Nest 恢复 |
| Runtime generation 与健康 | App Lifecycle |

恢复后只重新同步当前期望环境状态；过期动画、utterance 和物理副作用不重放。

## 验证与迁移纪律

每次迁移只完成一个可独立审查的纵向切片：冻结类型化边界，迁移完整生产者到消费者
调用链，证明定向路由和因果身份，删除被替代路径，并只关闭对应一致性条目。不得建立
兼容 Alias、双写、第二世界投影或空架构包。

聚焦证据必须区分直接身体回执、身体感知、语义物理结果、VisibleSet、环境事实、声音
可达、Nest 事件和 Runtime 生命周期事件。仅有传输测试通过，不能证明语义路由或
authority 所有权正确。

临时[Nest–Godot 迁移规约](../conformance/nest-godot-semantic-world-migration)定义强制迁移
卡顺序、数据决策门、每卡范围和退出证据；它可以细化执行过程，但不能重新定义本目标。
