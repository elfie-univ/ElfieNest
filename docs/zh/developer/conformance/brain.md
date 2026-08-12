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
| BRN-001 | P0 | closed | Brain 现在把 Communication、Embodied、Internal 输入分别准入为带权威 `SourceDomain`、`InteractionScope`、`ResponseScope` 的类型化 `TurnFrame`，并拒绝混域 Frame。 | 域、Scope、排序、去重和边界攻击聚焦测试通过；不同会话、身体 generation 和内部原因保持独立 Turn；要求移动的 Communication Turn 不能提交身体指令；Elfie Lab 展示对应 Scope 与回执。 |
| BRN-002 | P0 | open | `BrainContext` 已接入带来源、版本、未知字段和当前回合 cutoff 的 Orientation、Selfhood、不可变 Profile 锚点、版本化 Memory 状态及版本化 Motivation 快照。Activity 已由 Brain 自有 Store 持有并在 Lab 投影中可见，但尚未进入统一 BrainContext 快照；既有 owner-memory 兼容写入仍未完成。 | 上下文组装无隐式写入地读取全部版本化所有者快照，区分事实/推测/未知，并记录一个 Turn 使用的全部快照 cutoff。 |
| BRN-003 | P0 | closed | `ReasoningRun` 已接管单个 Turn 内的有界 Model/Skill/Tool/Observation 循环，并以预算、截止时间、取消和完成状态收束；模型与认知工具仍在 Brain 内部，不增加外部行动线路。 | `test/elfie/brain/test_reasoning.py`、`test_coordinator.py`、`test_coordinator_terminal.py` 和 `test/devtools/elfie_lab/test_session.py` 共 26 项通过；真实 Elfie Lab 展示本地文件 Tool Observation、虚假外部执行声明不产生外部回执、模型不可用进入 `failed/no_op`，以及紧急事件形成独立新 Turn。纯文本 Provider 的 `owner_message_fallback` 只记录能力降级，不改变边界事实。 |
| BRN-004 | P0 | closed | `TurnDecision`/`OutputRouter` 已按来源域、响应 Scope 和当前能力确定性校验；具身决定携带身体 ID/generation，Communication 决定不能产生身体指令。跨回合 Activity 仍由 BRN-005 单独负责。 | 阶段三 Headless 与真实 Godot 路径通过；陈旧身体 generation、错误响应域、重复提交和身体执行失败均有聚焦证据；已接受决定至多进入一个外部执行域。 |
| BRN-005 | P0 | closed | Brain 现在拥有类型化跨回合活动（Persistent Activity）Port 和输出执行边界。Activity Draft 先做无副作用 Preflight，再幂等 Commit；持久等待/运行状态通过 `ACTIVITY` Internal 事件唤醒；真实子回执以 revision 和进度结算当前 Step。SQLite 与 Lab Adapter 仍在 Brain 外部。 | Activity/持久化/Lab 聚焦测试覆盖校验、幂等、唤醒、通信 Scope、回执终态、重启恢复和无重复投递。 |
| BRN-006 | P0 | open | Orientation 与 Selfhood 已有权威内存快照及候选—校验—提交/恢复保护；Emotion、Energy、Memory 现在提供版本化快照/Checkpoint 和 Brain 连续状态恢复门面，但 Profile 仍拥有等待物理迁移的人格/能力/限制宽映射。 | 版本化 Orientation、Selfhood、Emotion、Energy、Memory 状态一致恢复；Profile 保持不可变；单条消息或短期情绪不能改写人格；陈旧候选不能覆盖新状态。 |
| BRN-007 | P1 | open | 能量现在产生 `long`/`normal`/`degraded`/`emergency` 认知投影，并把每回合 token、模型、工具、步骤预算传给大脑皮层 Worker；持久紧急储备记账和用户可见的降级响应策略仍未完成。 | 确定性测试覆盖普通、有界长思考、降级和紧急模式；紧急储备禁止长思考/后台认知，同时保留最小响应和恢复。 |
| BRN-008 | P1 | closed | Brain 现在拥有一个有界的恢复 Motivation 驱力。低能量/高疲劳时只能产生带稳定因果 ID 的 `RecoveryDriveCandidate` 和 `InternalSignal.MOTIVATION`；压力、阻塞、冷却、满足状态、重复抑制和 Checkpoint 恢复共同防止自唤醒风暴。候选必须进入一次 Internal Turn，不能直接创建 Activity 或执行外部动作。 | Motivation、Coordinator 与 Elfie Lab 聚焦测试覆盖阈值、抑制、有界 Internal Turn、安全 No-op 结算和 Checkpoint 恢复。多驱力、社交主动和直接创建 Activity 保留为范围外。 |
| BRN-009 | P1 | closed | Brain 现在拥有有界的 Offline Cognition 生命周期：睡眠时最多接纳固定数量的待整理 Episodic 记忆，把带 Checkpoint 的候选送入一次 Internal Turn，并且只有内部回执完成后才提交已有 Memory 巩固器。 | `test_offline_cognition.py` 与 Elfie Lab 离线整理场景覆盖睡眠门控、阻塞/重复抑制、Checkpoint 恢复、有界巩固和回执后提交。候选没有外部响应 Scope，因此不能发消息、移动、创建 Activity 或扩权；更广的 Activity/情绪/Selfhood 夜间整理仍是后续范围。 |
| BRN-010 | P0 | open | Activity 现在具备持久 revision 状态、因果/幂等身份和回执对账，但 Brain 仍没有覆盖心智状态、Run、Directive 与 Activity 的统一持久 Journal/State/Checkpoint/因果 Trace 契约。 | 重启只恢复已提交状态，按因果/幂等身份对账未完成 Directive 和 Activity，拒绝旧身体 generation，暴露可追溯失败，且认知基础设施不成为决策所有者。 |

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
