# Elfie Brain 内部架构契约

**契约版本：** 1.0
**采用日期：** 2026-08-12
**适用范围：** `elfie/brain/` 和单只 Elfie 的私有认知协调

> **规范性目标。** 本契约定义同一只持续存在的 Elfie 如何接纳事件、维护心智状态、
> 思考、提交决定和恢复跨回合工作。已接受的 Brain 迁移现已完成，这些边界由永久
> 架构测试直接守护。

[Elfie 内部架构契约](./elfie)仍然是 Profile、Brain、NervousSystem、Body、
Communication 和 Genesis 所有权的上位权威。本契约只细化 Brain 内部，不增加第三条
对外线路、第二人格或第二套系统 Runtime。

## 目标与明确不做的事

Brain 服务的是一只持续、自主、具身的智慧体，而不是一次请求结束就消失的助手。它拥有
当前认知、缓慢变化的心智状态、跨 Turn 存续的工作，以及无外部副作用的心智整理。数字
通信生活和具身生活共享同一 Selfhood 与 Memory，但各自的 Turn 和输出 authority 隔离。

本契约固定语义所有者、生命周期边界和确定性守卫，不固定 Prompt、模型供应商、存储
Schema、评分公式、阈值、类数量或进程拓扑。十个系统是概念所有者，不代表必须建立十个
进程、数据库或空包。

## 十个概念系统

| 编号 | 系统 | 拥有 | 产生 | 绝对不能做 |
| --- | --- | --- | --- | --- |
| 1 | 事件工作区 | 有界 Communication、Embodied、Internal Lane；准入、保序、去重、背压、显著性和单域成帧 | 一个不可变 `TurnFrame`，或明确延后/拒绝结果 | 把多个来源域合成一个 Turn、理解复杂内容或执行行动 |
| 2 | 自我定位 | 带来源的当前身体、地点、时间、附近人物、会话、Activity、Affordance 和不确定性 | 版本化 `OrientationSnapshot` | 复制世界 authority、保存完整历史或定义人格 |
| 3 | 自我认知 | 由不可变 Profile 锚定的可变自我模型、人格倾向、规范及慢变化证据 | 版本化 Selfhood/Personality/Norms 快照和已校验更新 | 改写 Profile、接受单条消息改变人格或扩大能力 |
| 4 | 情绪 | 持续情感、刺激评估、叠加、衰减和恢复 | `EmotionSnapshot` 及对注意、回忆和表达的有界影响 | 创建 Goal、消息或身体动作 |
| 5 | 能量 | 稳态、昼夜状态、认知/行动预算、紧急储备和降级模式 | `EnergySnapshot`、预算预留和认知模式约束 | 选择语义 Goal 或取代 NervousSystem 安全反射 |
| 6 | 动机 | 固定驱力、压力、满足、竞争、饱和、冷却和重复抑制 | `AttentionBias`、`GoalCandidate` 或 `InternalTriggerCandidate` | 创建 Activity 或直接对外行动 |
| 7 | 记忆 | 主观情景、工作记忆、知识、人物、关系、来源、检索、巩固和遗忘 | 有界检索结果和已校验记忆提交 | 拥有当前 Orientation、Run 状态或 Activity 状态 |
| 8 | 思考中枢 | 上下文组装、有界 Model/Skill/Tool 循环、Observation、验证、抑制、完成判断和一个 `TurnDecision` | 一个已结算决定及内部状态候选 | 跨 Turn 等待、宣称执行成功或绕过确定性策略 |
| 9 | 跨回合活动 | 经过校验且跨当前 Turn 存续的 Goal 和工作；Step、条件、调度、暂停/恢复/取消、重试、幂等和回执 | Preflight 结果、状态事件和有界 Internal Trigger | 成为第二个 Brain 或直接执行开放式外部行动 |
| 10 | 心智整理 | 在无外部副作用 Scope 中可中断地整理睡眠/空闲期记忆、Activity、情绪轨迹和结果 | 已校验状态候选或未来 Internal Trigger | 直接发消息、移动、创建 Activity、扩权或改写权威状态 |

上下文组装、Turn 结算、决策治理、路由、Journal、Checkpoint 和回执对账是服务这些
所有者的必需机制，不是额外平级心智系统。

## 守恒规则

1. Brain 只接收 `Communication`、`Embodied`、`Internal` 三类事件来源域。
   消息/命令回执与 Activity 状态事件以绑定原始因果身份的 `Internal` 事件重新进入；
   随后在世界中实际观察到的事实仍是新的 `Embodied` 事件。回执不形成第四个来源域。
2. 一个 `TurnFrame` 只有一个 `SourceDomain`、一个 `InteractionScope` 和一个有界
   `ResponseScope`；模型输出不能扩大任一范围。
3. 同时到达的通信与具身事件必须形成不同 Turn。它们可以读取共享的已提交心智状态，
   但不能共享 Frame、临时推理状态或输出 authority。
4. 跨域后果必须成为经过校验的跨回合活动请求，或者未来 Internal 事件和新 Turn。
   Communication Turn 当前不能输出 NervousSystem 指令。
5. 每个 Turn 只结算为一个 `TurnDecision`。它至多请求一个外部执行域：Communication
   或 NervousSystem；可以同时携带一个已校验跨回合活动请求；全部为空即 `No-op`。
6. Model、Skill、Tool、Worker 和心智整理的输出都只是提案或 Observation。它们不能
   证明外部行动发生，也不能直接写入权威状态。
7. 所有权威心智状态更新均采用“候选—校验—提交”，每次提交必须带来源、因果身份、
   版本和幂等语义。
8. 只有类型化外部回执能证明消息或身体执行，只有 Activity 状态事件能证明持久工作迁移。
9. 所有开放决策经过唯一、串行、确定性的提交边界，统一校验来源/响应/执行 Scope、
   能力、预算、隐私、截止时间、身体 generation 和幂等。
10. 快速确定性安全反射留在 NervousSystem，不能等待开放式模型 Turn。

## 在线 Turn 生命周期

### 准入与成帧

生产者发布语义事件，不把原始设备帧或平台 Payload 交给 Brain。事件工作区维护三个有界
逻辑 Lane 和明确背压。它可以去重、合并状态更新、习惯化重复刺激、优先处理安全事件并
保证公平，但必须保留来源和因果身份。

准入生成不可变单域 `TurnFrame`，其中包含稳定 Turn ID、来源域、交互 Scope、触发事件、
cutoff、截止时间和响应范围。Communication Scope 绑定渠道、会话和相关参与者，不同会话
必须形成不同 Turn；Embodied Scope 绑定当前 Body ID/generation 和一个连贯现场窗口；
Internal Scope 绑定一个 Trigger 或 Activity 因果链。因此一个 Frame 可以聚合多个兼容
事件，但不能混合独立会话、身体 generation 或内部原因。cutoff 之外的事件留给后续
Turn。无法准入必须产生可观察的延后、拒绝或背压结果，不能静默丢失。

### 上下文与思考

思考中枢只组装本 Turn 需要的上下文。上下文快照记录 Profile 锚点、自我定位、自我
认知、情绪、能量、动机、记忆、Activity 和有效能力的版本与采集时间，并区分事实、
推测和未知。

一个 `ReasoningRun` 可以包含多个 Cognitive Step，以及多次 Model、Skill、Tool 和
Observation 循环。它必须有明确预算、截止时间、取消状态和完成条件。Tool Observation
回到同一个 Run。受限 Worker 只能获得最小 Context Capsule，不拥有独立身份、持久状态
写权或外部行动线路。

Run 最终形成一个结构化 `TurnDecision`、明确失败或安全 `No-op`。超时、模型不可用、
Tool 被拒或预算耗尽不能表示为成功完成。

### 决定、执行与结算

确定性边界在提交 Directive 前，根据被接纳 Turn 和当前状态校验决定。唯一行动类型为：

- `CommunicationDirective`：投递数字消息；
- `NervousSystemDirective`：具身说话、表达或运动；
- `PersistentActivityRequest`：提交超出当前 Turn 的已校验工作；
- 没有行动提交时为 `No-op`。

Memory、Emotion、Selfhood、Orientation、Energy 或 Motivation 候选属于 Turn 结算材料，
不是第四类行动。结算把每个候选或回执交给真实所有者；所有者根据当前版本和因果身份
校验后提交。陈旧或重复结果必须拒绝或对账，不能只通过下一轮 Prompt 假设状态已经修正。

## 响应范围

- Communication Turn 可以产生 Communication 指令、已校验跨回合活动请求或 `No-op`，
  不能产生 NervousSystem 指令。直接回复必须留在被接纳的渠道/会话；联系另一个人或
  会话必须形成经过校验的后续 Scope。
- Embodied Turn 可以产生 NervousSystem 指令、已校验跨回合活动请求或 `No-op`，不能
  产生数字消息指令。
- Internal Turn 可以在自身 `ExecutionScope` 允许范围内选择至多一个外部域，可以创建或
  更新已校验 Activity，也可以选择 `No-op`。
- 澄清必须使用当前来源域。目标身份、联系方式、能力、时间语义或成功条件缺失时，应尽量
  在原始 Turn 当场确认，不能拖到 Activity 到期时才发现。

## 跨回合活动生命周期

跨回合活动拥有 `Goal -> Activity -> ActivityStep -> ActivityRun` 语义，但不拥有第二人格
或第二套推理引擎。Turn 提交持久 Activity 前，思考中枢可以把无副作用的 `ActivityDraft`
同步交给 Preflight。Preflight 检查目标身份、联系方式、能力、预算、时间语义、依赖、
成功条件和执行 Scope，并返回 `VALIDATED`、`NEEDS_CLARIFICATION` 或 `REJECTED`；它不
产生持久化或外部副作用。

只有已校验 Draft 可以在 Turn 结算后正式提交。到期时间、条件、重试或回执只产生类型化
Internal 事件，不能直接执行开放行动。通信与具身后果必须是不同 Activity Step 和不同
Turn。稳定因果 ID、幂等键、Checkpoint 和回执保证中断或重启后不丢承诺、不重复副作用。

动机和心智整理不能直接创建 Activity，只能产生重新进入事件工作区的 Internal Turn 候选。
跨回合活动尚未具备有界创建、取消、冷却和恢复前，不得把 Motivation 开放为行动来源。

## 能量、长思考与中断

能量决定可用认知模式和资源预留，不决定语义内容。策略至少区分普通工作、有界长思考、
降级响应和紧急储备。紧急储备保留基本定位、拒绝、确认和求助能力，但禁止长思考和可选
后台工作。

长 `ReasoningRun` 可以让步或中断。新到达的紧急事件必须形成新 Turn，不能注入现有 Run。
“我正在忙”之类快速确认同样是拥有独立 Scope 和预算的新 Turn。只有临时状态完全隔离时，
多个 Run 才可以并行计算；它们仍必须经过唯一串行提交边界。基于陈旧状态、过期截止时间或
旧身体 generation 的输出不得提交。

## 认知工具与外设

Brain Skills 授权语义认知能力。`ToolPort` 只执行由注入且限定 Elfie 作用域的 Runtime
提供的工具，例如有界搜索、检索、命令执行、简单代码，以及当前 Elfie 获授权认知工作区
内的文件操作。Runtime 通过进程沙箱、命令允许列表、网络策略、工作区 Root 和配额进行
确定性约束；在该 Envelope 内不需要逐操作人工批准。

数字通信渠道、身体控制和设备状态不是 Tool。它们是最终决定结算后才能经 Communication
或 NervousSystem 访问的外设。Tool 不能暴露隐藏的消息、设备或身体线路，其文本声明永远
不是执行回执。

## 状态、持久化与恢复

`MemoryState`、`ReasoningRunState` 和 `ActivityState` 必须分离。持久认知基础设施提供
Event Journal、权威 State Store、Run/Activity Checkpoint、预算账本、因果 Trace、幂等
记录和回执对账。它们为十个系统保存状态，但不成为第十一个心智系统，也不决定行为。

重启后，Brain 恢复最后已提交状态，对账未完成 Directive 和 Activity，拒绝旧身体
generation，只恢复 Scope 和截止时间仍然有效的工作。模型服务缺失只会延后或降级开放
认知，不能擦除身份、情绪、记忆、承诺或基本反射能力。

## 依赖与目录规则

Brain 只依赖自身定义的强类型使用方 Port 和 Elfie 语义契约，不导入 App、Nest、具体
Infrastructure、Provider SDK、平台 Payload、设备传输、文件系统 Root 或数据库 Record。
AI Runtime 实现留在 Brain 外部；Brain 拥有在 Run 中何时以及为什么调用它们。

规范包名是 `workspace/`、`orientation/`、`selfhood/`、`emotion/`、`energy/`、
`motivation/`、`memory/`、`reasoning/`、`activity/` 和 `consolidation/`。每个包必须拥有
真实状态、契约或行为；禁止恢复同义根级扁平模块，也禁止只有架构形状的空目录。

私有认知协调和上下文组装归 Brain。根 Elfie Facade 可以启动、停止和观察聚合，但不能
拥有 Turn 状态、模型循环或心智状态。产品实现只能通过一致性台账记录、另行批准的垂直
切片推进；本契约本身不授权迁移源码。
