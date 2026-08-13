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
| BRN-002 | P0 | closed | `BrainContextProvider` 只组合独立所有者的有界投影；Conversation、Memory 和 Activity 分别有专用 Reader/Store。Memory 与 Orientation 更新成为显式候选，并只在 `TurnSettlement` 中提交，不再由上下文读取隐式写入。Orientation 同时纳入当前 Body、地点、会话与 Activity。 | 上下文、Activity、Orientation 与 Turn Settlement 聚焦测试证明 cutoff/未知/过期语义、读取不写入、版本提交和重复提交去重。 |
| BRN-003 | P0 | closed | `ReasoningRun` 已接管单个 Turn 内的有界 Model/Skill/Tool/Observation 循环，并以预算、截止时间、取消和完成状态收束；模型与认知工具仍在 Brain 内部，不增加外部行动线路。 | `test/elfie/brain/reasoning/` 和 `test/devtools/elfie_lab/test_session.py` 的聚焦场景通过；真实 Elfie Lab 展示本地文件 Tool Observation、虚假外部执行声明不产生外部回执、模型不可用进入 `failed/no_op`，以及紧急事件形成独立新 Turn。纯文本 Provider 的 `owner_message_fallback` 只记录能力降级，不改变边界事实。 |
| BRN-004 | P0 | closed | `TurnDecision`/`OutputRouter` 已按来源域、响应 Scope 和当前能力确定性校验；具身决定携带身体 ID/generation，Communication 决定不能产生身体指令。跨回合 Activity 仍由 BRN-005 单独负责。 | 阶段三 Headless 与真实 Godot 路径通过；陈旧身体 generation、错误响应域、重复提交和身体执行失败均有聚焦证据；已接受决定至多进入一个外部执行域。 |
| BRN-005 | P0 | closed | Brain 现在拥有类型化跨回合活动 Port 和输出执行边界。`ActivityDraft` 在原始 `ReasoningRun` 内完成无副作用 Preflight；它校验已解析人物/渠道、能力 revision、`ExecutionScope`、预算、截止时间和允许操作。只有宿主本轮签发的同一证据可在收敛后幂等 Commit；缺信息会作为 Observation 回到本轮澄清。 | Activity、Reasoning、持久化与 Lab 聚焦测试覆盖同轮澄清、伪造证据拒绝、幂等、唤醒、Scope、回执终态、重启恢复和无重复投递。 |
| BRN-006 | P0 | closed | Orientation 与 Selfhood 是独立权威所有者；Selfhood 由不可变 Profile revision 锚定，单次提交具备多来源证据和人格变化幅度上限。Emotion、Energy、Memory、Orientation、Selfhood、Motivation 与 Cognitive Consolidation 均进入连续状态 Checkpoint/恢复门面；Profile 宽字段的物理迁移由 ELF-010 单独跟踪。 | 状态与跨模块恢复测试覆盖版本化恢复、旧 Checkpoint/错误 Profile 拒绝、单消息人格/规范重写拒绝、Orientation 的 Activity/身体定位以及陈旧候选保护。 |
| BRN-007 | P1 | closed | Energy 现在同时管理普通认知预算、持久紧急储备和回合级预算预留/结算，并产生 `long`/`normal`/`degraded`/`emergency` 认知投影。紧急模式只签发最小响应预算，禁止长思考、工具和后台 Activity；普通 Activity 不能消耗紧急储备。Lab 明确展示普通预算、紧急储备和在途预留。 | Energy、Coordinator、Activity 与 Lab 聚焦测试覆盖普通预留、完成/失败释放、持久恢复、低能量降级、紧急最小响应和后台认知抑制。 |
| BRN-008 | P1 | closed | Brain 现在拥有一个有界的恢复 Motivation 驱力。低能量/高疲劳时只能产生带稳定因果 ID 的 `RecoveryDriveCandidate` 和 `InternalSignal.MOTIVATION`；压力、阻塞、冷却、满足状态、重复抑制和 Checkpoint 恢复共同防止自唤醒风暴。候选必须进入一次 Internal Turn，不能直接创建 Activity 或执行外部动作。 | Motivation、Coordinator 与 Elfie Lab 聚焦测试覆盖阈值、抑制、有界 Internal Turn、安全 No-op 结算和 Checkpoint 恢复。多驱力、社交主动和直接创建 Activity 保留为范围外。 |
| BRN-009 | P1 | closed | Brain 现在拥有有界的 Cognitive Consolidation 生命周期：睡眠时最多接纳固定数量的待整理 Episodic 记忆，把带 Checkpoint 的候选送入一次 Internal Turn，并且只有内部回执完成后才提交已有 Memory 巩固器。 | Consolidation 与 Elfie Lab 场景覆盖睡眠门控、阻塞/重复抑制、Checkpoint 恢复、有界巩固和回执后提交。候选没有外部响应 Scope，因此不能发消息、移动、创建 Activity 或扩权；更广的 Activity/情绪/Selfhood 夜间整理仍是后续范围。 |
| BRN-010 | P0 | closed | 生产与 Lab 的每只 Elfie 现在都会注入独立 SQLite 认知持久化 Adapter。追加式 Journal 记录 Run 开始/终态、Directive 接受/拒绝、执行回执和 Activity revision；最新 Checkpoint 持久覆盖 Emotion、Energy、Memory、Orientation、Selfhood、Motivation 与 Cognitive Consolidation。工作区把未提交输入、原始顺序、最近事件幂等窗口以及合并/丢弃证据作为同一原子状态持久化。重启恢复 Checkpoint 和认知时钟，把未完成 Run/Directive 转换为无响应 Scope 的不确定事实，并暂停运行中的 Activity，不自动重放外部副作用。 | Journal、SQLite、Workspace、Router、生命周期和重启聚焦测试证明追加顺序、幂等冲突拒绝、Run/Directive/回执关联、提交前输入恢复、跨重启去重、可观察丢弃、持久 Checkpoint 恢复、Activity 暂停对账及不自动重复执行。Journal 与 Checkpoint 仍是认知基础设施，不是第十一个决策所有者。 |

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
