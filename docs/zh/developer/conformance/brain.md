# Elfie Brain 内部架构一致性

> [Brain 内部架构契约](../contracts/brain)的临时缺口台账。它记录当前实现事实和关闭
> 证据，不降低目标。

这些条目只是细分尚未关闭的主体级缺口，不形成第二份迁移事实源：BRN-001/002/004
细化 ELF-011，BRN-003 细化 ELF-016，BRN-005/010 细化 ELF-014，BRN-006/007
细化 ELF-010 与 ELF-017，BRN-008/009 细化 ELF-015。关闭 Brain 条目时，必须同步
更新已经满足关闭条件的主体级条目。

## 当前缺口

| ID | 严重度 | 状态 | 当前偏差 | 关闭证据 |
| --- | --- | --- | --- | --- |
| BRN-001 | P0 | open | `PerceptionFrame` 可以同时包含 physical、social、execution 和 internal Payload，缺少权威 `SourceDomain`、`InteractionScope`、`ResponseScope` 和单域校验器。 | Communication、Embodied、Internal Lane 分别产生类型化 `TurnFrame`；不同会话、身体 generation 和内部原因保持独立 Scope；同时到达的跨域事件仍是不同 Turn；要求移动的 Communication Turn 不能提交身体指令。 |
| BRN-002 | P0 | open | `BrainContext` 只有 Frame、情绪、稳态、会话、记忆和能力，缺少权威 Orientation、Selfhood、Motivation、Activity 快照及完整来源/版本/未知语义；`ElfieContextSource` 仍在 Elfie 根部，并在读取上下文时隐式修改会话和兼容记忆。 | 上下文组装迁入 Brain，无隐式写入地读取版本化所有者快照，区分事实/推测/未知，并记录一个 Turn 使用的全部快照 cutoff。 |
| BRN-003 | P0 | open | `CorticalWorker` 只完成一次模型生成和解码，缺少有界多步 Model/Skill/Tool Observation 循环、验证/完成判断、明确认知预算和长短 Run 中断契约。 | `ReasoningRun` 支持有界认知步骤和真实 Tool Observation；预算、超时、取消、陈旧结果测试均在不伪造成功的情况下终止；独立紧急 Turn 不污染现有 Run。 |
| BRN-004 | P0 | open | `DecisionPlan` 是可混合 speech、message、motion 和占位内部操作的多意图 DAG；`OutputRouter` 实际承担决策/执行边界，但未强制已接受的单域 Turn/响应矩阵，也没有跨回合活动请求。 | 一个 `TurnDecision` 根据来源、响应、执行 Scope 确定性校验；至多一个外部域提交；内部状态候选单独结算；陈旧能力/身体 generation 和重复提交被拒绝。 |
| BRN-005 | P0 | open | `DefaultInternalIntentSink` 直接把 `REMEMBER`、`SCHEDULE`、`REFLECT` 标记完成；没有持久跨回合活动所有者、Preflight/Commit 分离、类型化唤醒、Checkpoint 或回执对账。 | 已校验 Activity 跨 Turn/重启存续；不完整请求在原始 Turn 澄清；到期只发 Internal 事件；通信/身体 Step 分离；重启不丢失或重复副作用。 |
| BRN-006 | P0 | open | 情绪、能量、记忆已有部分所有者，Orientation 与 Selfhood 尚无权威系统；Profile 仍拥有宽泛人格/能力/限制映射，心智状态也没有统一候选—校验—提交与恢复协议。 | 版本化 Orientation、Selfhood、Emotion、Energy、Memory 状态一致恢复；Profile 保持不可变；单条消息或短期情绪不能改写人格；陈旧候选不能覆盖新状态。 |
| BRN-007 | P1 | open | 能量已推进疲劳/能量和当前 Turn 时间，但还未拥有完整认知模式策略、正常/紧急预算预留、长思考准入和降级响应行为。 | 确定性测试覆盖普通、有界长思考、降级和紧急模式；紧急储备禁止长思考/后台认知，同时保留最小响应和恢复。 |
| BRN-008 | P1 | open | 自主 deadline/内部信号仍是占位，不是具备压力、满足、饱和、冷却、重复抑制和 Activity 限制的固定驱力 Motivation。 | BRN-005 关闭后，一个低风险固定驱力只能产生有界注意/Goal/Internal Trigger 候选，不能自唤醒风暴、刷屏、创建 Activity 或直接执行。 |
| BRN-009 | P1 | open | 当前 Memory consolidation 只是记忆 Helper，不是具备独立预算、Checkpoint 和无外部副作用 Scope 的可中断心智整理生命周期。 | 睡眠/空闲 Run 可从 Checkpoint 恢复，只提交已校验记忆/关系/Selfhood 候选或未来 Internal Trigger，不能发消息、移动、创建 Activity 或扩权。 |
| BRN-010 | P0 | open | Workspace、Turn、决定、输出和回执已有部分持久化/指标，但 Brain 尚无覆盖心智状态、Run、Activity 的统一持久 Journal/State/Checkpoint/因果 Trace/对账契约。 | 重启只恢复已提交状态，按因果/幂等身份对账未完成 Directive 和 Activity，拒绝旧身体 generation，暴露可追溯失败，且认知基础设施不成为决策所有者。 |

## 实现顺序约束

详细执行计划是另行批准的独立产物。它可以把这些差距拆成更小垂直切片，但必须遵守：

1. BRN-001 与 BRN-004 的最小确定性部分先形成可见数字通信 Turn 闭环；
2. BRN-002、BRN-003 增加真实上下文和有界 Agent 思考，不增加新外部行动线路；
3. 具身闭环补齐 BRN-004 的身体侧，同时保持 Communication/Embodied Turn 隔离；
4. BRN-006、BRN-007 先建立连续状态和恢复，自治行为才可以依赖它们；
5. BRN-005 及所需 BRN-010 持久能力必须先关闭，BRN-008 才能产生主动工作候选；
6. BRN-009 最后启用，并永远不能直接产生外部副作用。

每个实施阶段必须提供一个可观察结果、一个边界攻击、一个失败或重启检查以及明确非目标。
只有产品行为和聚焦测试才能关闭条目；契约文字本身不是实现证据。
