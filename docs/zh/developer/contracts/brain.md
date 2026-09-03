# Elfie Brain 内部架构契约

**契约版本：** 1.7
**采用日期：** 2026-08-12
**修订日期：** 2026-09-03
**适用范围：** `elfie/brain/` 和单只 Elfie 的私有认知协调

> **规范性目标。** 本契约定义同一只持续存在的 Elfie 如何接纳事件、维护心智状态、
> 思考、提交决定和恢复跨回合工作。更早的 Brain 迁移继续由永久架构测试守护；已接受的
> Selfhood/固定头部差距继续记录在聚焦的
> [Selfhood 一致性台账](../conformance/elfie-selfhood)中；已完成的 Reasoning Context
> Workspace P0 边界由永久聚焦测试守护。版本 1.5 冻结了一次性 Genesis 与最终所有者隔离
> 规则；版本 1.6 进一步冻结 ADR-0033 接受的三个来源域、具身终态和动态能力路由；版本 1.7
> 记录已接受 Brain 设计层级的稳定链接。尚未
> 落地的差距继续记录在各自聚焦的一致性台账中。

[Elfie 内部架构契约](./elfie)仍然是 Profile、Brain、NervousSystem、Body、
Communication 和 Genesis 所有权的上位权威。本契约只细化 Brain 内部，不增加第三条
对外线路、第二人格或第二套系统 Runtime。

## 目标与明确不做的事

Brain 服务的是一只持续、自主、具身的智慧体，而不是一次请求结束就消失的助手。它拥有
当前认知、缓慢变化的心智状态、跨 Turn 存续的工作，以及无外部副作用的心智整理。数字
通信生活和具身生活共享同一 Selfhood 与 Memory，但各自的 Turn 和输出 authority 隔离。

本契约固定语义所有者、生命周期边界和确定性守卫；它同时固定在线 Elfie 模型 Prompt
四段前缀及其来源 authority，但不固定随版本发布的具体文案、模型供应商、存储编码、
可调数值系数或进程拓扑。Emotion 保存六通道并消费正负语义评价属于固定语义；
各通道 Gain、半衰期和展示阈值仍由配置调整。十个系统是概念所有者，不代表必须建立十个
进程、数据库或空包。

## 十个概念系统

| 编号 | 系统 | 拥有 | 产生 | 绝对不能做 |
| --- | --- | --- | --- | --- |
| 1 | 事件工作区 | 有界 Communication、Embodied、Activity Lane；准入、保序、去重、背压、显著性和单域成帧 | 一个不可变 `TurnFrame`，或明确延后/拒绝结果 | 把多个来源域合成一个 Turn、理解复杂内容或执行行动 |
| 2 | 自我定位 | 带来源的当前身体、地点、时间、附近人物、会话、Activity、Affordance 和不确定性 | 版本化 `OrientationSnapshot` | 复制世界 authority、保存完整历史或定义人格 |
| 3 | 自我认知 | 一份原子状态：创建后冻结的 `identity_core` 与缓慢的 `adaptive_self`；确定性强类型/模型投影 | 版本化 Selfhood 快照、两个模型头部段，以及仅在后续设计获批后的 Memory 证据更新 | 运行时读取 Profile/Canon、接受 Turn/模型/当前状态直接更新、持久化最终 Prompt 或扩大能力 |
| 4 | 情绪 | 进程内情感、刺激评估、叠加、衰减和恢复 | `EmotionSnapshot` 及对注意、回忆和表达的有界影响 | 创建 Goal、消息或身体动作，或持久化实时存量 |
| 5 | 能量 | 稳态、昼夜状态、认知/行动预算、紧急储备和降级模式 | `EnergySnapshot`、预算预留和认知模式约束 | 选择语义 Goal 或取代 NervousSystem 安全反射 |
| 6 | 动机 | 固定驱力、压力、满足、竞争、饱和、冷却和重复抑制 | `AttentionBias`、`GoalCandidate` 或 `ActivityTriggerCandidate` | 创建 Activity 或直接对外行动 |
| 7 | 记忆 | 持久主观情景、知识、人物、关系、来源、检索、巩固和遗忘 | 有界检索结果和已校验持久记忆提交 | 拥有短期会话/上下文状态、当前 Orientation、Run 状态或 Activity 状态 |
| 8 | 思考中枢 | `Reasoning Context Workspace`、上下文组装、有界 Model/Skill/Tool 循环、Observation、验证、抑制、完成判断和一个 `TurnDecision` | 一个已结算决定及内部状态候选 | 跨 Turn 等待、让其他系统拥有其短期上下文、宣称执行成功或绕过确定性策略 |
| 9 | 跨回合活动 | 经过校验且跨当前 Turn 存续的 Goal 和工作；Step、条件、调度、暂停/恢复/取消、重试、幂等和回执 | Preflight 结果、状态事件和有界 Activity Trigger | 成为第二个 Brain 或直接执行开放式外部行动 |
| 10 | 心智整理 | 在无外部副作用 Scope 中可中断地整理睡眠/空闲期记忆、Activity、情绪轨迹和结果 | 已校验状态候选或未来 Activity Trigger | 直接发消息、移动、创建 Activity、扩权或改写权威状态 |

上下文组装、Turn 结算、决策治理、路由、Journal、Checkpoint 和回执对账是服务这些
所有者的必需机制，不是额外平级心智系统。

## 情绪状态与评价

[Elfie 情绪系统设计](../designs/elfie/brain/elfie-emotion-system)是本节已经接受的详细解释；当前效果
差距记录在[情绪一致性台账](../conformance/elfie-emotion)。

1. Emotion 拥有 Elfie 自己的进程内情绪，不拥有被观察对象的情绪。他人的感受只是证据；
   只有“对 Elfie 的直接影响”评价，或由宿主解析并按关系加权的间接评价，才能改变 Elfie。
2. 首版只保存 `happiness`、`sadness`、`anger`、`fear`、`surprise`、`disgust` 六个
   `[0, 1]` 存量，多个通道可以共存。主情绪、次情绪、活跃标签和趋势都是派生投影；
   VAD、Episode 列表和固定互动矩阵不能成为平行情绪事实源。
3. 快速评价和模型评价只输出绑定宿主可信 Scope 的稀疏正负语义证据。省略通道保持不变。
   模型只返回方向、语义强度和置信度，不能返回存量增量或最终值；所有数值更新由确定性的
   Emotion Owner 计算。
4. 同方向证据的合并不能让弱信号稀释强信号。正 Drive 饱和趋近上限，负 Drive 消耗现有
   存量，没有 Drive 时按指数回归各自的人格基线。大五人格可以有界影响基线、Gain 和
   半衰期，但不能成为第二个状态源。
5. Emotion 应用 Event Workspace 已准入的每个事件，不再重复去重。重复准入观察可以刷新
   持续状态，饱和增长负责限制上界。
6. 每个 Frame 先捕获快速反应前的稳定 Anchor。快速评价可以提交临时候选，但模型只能
   收到快速反应前的稳定情绪投影和宿主可信候选 Scope。有效结构化慢反馈必须从同一 Anchor
   重新计算并原子替换快速候选；显式空反馈撤销本 Frame 快速效果，缺失、无效或失败反馈
   保留快速结果。
7. 宿主成帧必须独立于快速关键词是否命中，为合资格自我相关事件提供慢层候选 Scope；
   模型不能发明或扩大 Scope。绑定同一持续因果身份的有界纠正可以作用于后续同因观察，
   不能影响无关事件。
8. 实时存量、Frame 事务和持续原因指导都不持久化。睡眠或进程重启恢复人格基线并清空临时
   指导。Emotion 不拥有数据库、Checkpoint 或历史变化事件账本；有界近期来源 ID 只用于
   诊断来源，不是第二套历史。
9. 首版评价社交文本、物理触碰、执行结果和显式内部/模型证据。感知边界可以保留类型化
   音频和图像/视觉传输，但其情绪评价暂缓。未来 Detector 必须通过同一 Scope 边界输出
   观察证据，不能直接修改 Emotion，也不能在无检测结果时伪造 calm。

## Selfhood 与在线模型固定头部

[Selfhood 与固定模型头部设计](../designs/elfie/brain/elfie-selfhood-and-fixed-model-header)是本节已经
接受的详细解释；当前实现差距记录在
[Selfhood 一致性台账](../conformance/elfie-selfhood)。

### Selfhood authority 与状态

1. Selfhood 拥有一份原子、强类型状态，只有一个 Schema 版本、一个 Selfhood revision，
   语义上严格分两层。`identity_core` 保存创建时冻结、每只 Elfie 必需的最低身份事实；
   `adaptive_self` 保存有界人格特征、个人价值/规范 ID，以及互动、应对和表达倾向。
2. 该状态不得含 Profile revision、Canon 或资料包版本/路径/引用、问卷答案、生成 Seed/
   策略轨迹、最终 Prompt 段落、模型自由生成的自传、详细世界知识、传记、关系状态、当前
   Emotion/Energy/Orientation/Activity、能力、权限或全应用规则。
3. Genesis 之后 `identity_core` 永久不可变。第一阶段不暴露已装配的 `adaptive_self` 更新
   路径。后续获批成长设计最多允许 Memory 整理生成强类型 proposal，其中必须有基础
   Selfhood revision、稳定 proposal/幂等 identity 和持久 Memory 证据。Memory 拥有
   proposal 与证据；Consolidation 可以调度推导，模型最多是该有界 Memory 流程内部的
   不可信助手，两者都不能直接调用 Selfhood。只有 Selfhood 可以校验、提交，proposal
   绝不能修改 `identity_core`。
4. Selfhood 可以向已签约 Brain owner 提供不可变强类型 snapshot 或更窄 trait 投影。
   Reasoning 只能收到确定、有界、无副作用的 `SelfhoodPromptProjection`，其中仅含
   `identity_core_text`、`adaptive_self_text` 和非 Prompt revision 元数据。投影不持久化、
   不读 Profile/Canon/Memory、不调用模型、不输出大五原始值或内部 ID，也不能编造传记、
   关系、知识、当前状态、权限或行动。
5. 用户可控名字与每个有界文本槽都必须按数据编码。控制字符、保留固定头标签和能破坏
   分隔符的序列必须在投影前拒绝或转义。任意领养故事、Memory 内容与模型文本不能进入
   固定段。

### Genesis 与运行时输入

6. Genesis 是唯一 Selfhood 初始化者。它可以读取已发布强类型资料包、仅创建期存在的已接受
   领养输入和受审的确定性映射，并把 Profile、完整 Selfhood、Genesis Memory 作为同一已
   校验创建 Bundle 的并列输出。普通启动时 Selfhood 不从已持久 Profile 派生；不完整或冲突
   创建必须拒绝准入。Selfhood 自有契约不得定义外部 Profile/Canon Observer 投影；这类投影
   归拥有它的 Profile/App View。
7. Profile 仍是外层不可变档案。资料包只在提交前作为世界/物种输入和 Genesis Memory 来源。
   已接受答案、`LifeContext`、`PersonalGenesisPlan`、资料包绑定和生成 Seed 不得持久化到
   Selfhood 或普通 Brain 状态，并在创建事务结束后删除。普通 Brain 运行、Reasoning 上下文
   与 Selfhood 投影不得读取、接收、刷新或同步 Profile、Canon 或任何创建资料。既有 Elfie
   不绑定 Canon 版本；后续源资料改动不能改变它的 Selfhood 或 Memory。
8. Selfhood 缺失、无效、版本不支持或无法渲染时，必须在调用 `ModelPort` 前让 Brain/
   resident 认知失败并输出安全诊断。不得 fallback 到 `Elfie`、通用 persona、全 0.5 traits、
   Profile、Canon、Memory 自我叙事或模型生成修补。

### 四段固定前缀

9. 在线 Elfie `ReasoningRun` 内的每个模型请求都必须严格以一次下列固定前缀开头：

   ```text
   [APPLICATION_FRAME]
   {application_frame_text}

   [IDENTITY_CORE]
   {identity_core_text}

   [ADAPTIVE_SELF]
   {adaptive_self_text}

   [OPERATING_CONTRACT]
   {operating_contract_text}
   ```

   Reasoning 拥有标签、顺序与请求组装；Selfhood 拥有并渲染第二、第三段。一份 required、
   人工编写、同版本、bundled-only 的 `ReasoningConstitution` 拥有第一、第四段；
   Infrastructure 只校验/加载，Bootstrap 注入。用户、Genesis、Canon、模型、Provider 与
   单只 Elfie 数据都不能生成、覆盖、热更新或按条件分支该 Constitution。
10. `APPLICATION_FRAME` 只含最低限度共同 ElfieNest 应用与故事前提；
    `OPERATING_CONTRACT` 只含稳定身份、知识边界、上下文信任、执行事实与 Scope 规则。
    详细 Canon、个体事实和随 Turn 变化的 Schema/能力指令不得进入两段。
11. 可信 `TURN_PROTOCOL` 与当前 Brain 状态跟在固定前缀之后。检索 Memory、Activity、
    观察、对话历史和当前消息仍是后续上下文数据，不能形成第五个固定段，也不能替代任何
    固定来源。
12. 规范封装统一使用 LF 换行，第一段之前没有文本，段间严格一个空行，与后续
    `[TURN_PROTOCOL]` 之间也严格一个空行。校验后的段落正文没有首尾空行，也不能含保留
    头部标签。
13. 同一在线 Run 的初始生成、Tool Observation 续跑与结构化输出修复，必须保持完全相同的
    固定前缀字节和绑定来源 revision。Genesis、Memory 整理、Provider 探测、评价 Judge 与
    无身份后台 Worker 不得收到这个 Elfie 头。所有在线 system 指令，包括 Skill/Tool 指令，
    都由 Reasoning 放在固定前缀后的 `TURN_PROTOCOL`。Provider/模型 Adapter 与通用 Prompt
    Injector 不得新增 system 指令，也不得改变请求消息顺序或内容。
14. 动态上下文裁剪前先为固定前缀保留预算。调用前同时校验其字节上限和 Provider 完整
    context window。固定段不能为适配预算被删除、截断或重排；无效请求必须明确失败。
15. `OPERATING_CONTRACT` 是模型指导，不是安全 authority。确定性宿主能力、响应/执行
    Scope、隐私、预算、串行提交与回执门禁仍为必需，并高于冲突的个人规范或模型输出。

### 持久化与冲突规则

16. 第一阶段每只 Elfie 的 Selfhood 文档是唯一持久 Selfhood authority。通用 Brain
    continuity checkpoint 不得包含或恢复 Selfhood。未来 adaptive 更新只有在专用、原子、
    revision 校验且幂等的持久提交边界建立后才能启用。
17. Memory 不得持久化或注入第二套权威 identity/relation/world/tendency 自我叙事。身份
    冲突以 `identity_core` 为准，Memory 回忆只是可错证据；当前 Emotion/Orientation 可以
    暂时调制表达，不能改写 `adaptive_self`。创建时 Profile/Selfhood 冲突就创建失败，
    普通运行不能回读 Profile 修补。
18. 应用升级可以为所有 Elfie 统一替换同版本 Constitution，但不能改变 `identity_core`、
    把 Selfhood 绑定到新 Canon，或静默改写既有 `adaptive_self` 数据。

## 守恒规则

1. Brain 只接收 `Communication`、`Embodied`、`Activity` 三类事件来源域。身体动作结果
   是外部 `Embodied` 事实；消息投递结果是 `Communication` 事实；Activity 状态事件以
   `Activity` 事件重新进入。每个外部结果保留自己的来源域和原始因果身份；回执不形成
   第四个来源域。
2. 一个 `TurnFrame` 只有一个 `SourceDomain`、一个 `InteractionScope` 和一个有界
   `ResponseScope`；模型输出不能扩大任一范围。
3. 同时到达的通信与具身事件必须形成不同 Turn。它们可以读取共享的已提交心智状态，
   但不能共享 Frame、临时推理状态或输出 authority。
   同一具身因果窗口内兼容的事实（例如一个动作的终态、位置、姿态、到达和触觉）可以
   合并到同一个 Embodied Frame；动作回执没有独立的 Brain 触发规则。
4. 跨域后果必须成为经过校验的跨回合活动请求，或者未来 Activity 事件和新 Turn。
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

三个 Lane 同时接受 Brain 触发的结果和外部主动输入。身体传感器、Godot/设备感知以及
Nest 定向语义结果都可以主动进入 Body 输入边界，不要求先有 Brain Turn。单个输入事件不
等于一次模型 Turn；准入会在 cutoff 内批量合并兼容事件，并执行显著性、去抖和背压。

准入生成不可变单域 `TurnFrame`，其中包含稳定 Turn ID、来源域、交互 Scope、触发事件、
cutoff、截止时间和响应范围。Communication Scope 绑定渠道、会话和相关参与者，不同会话
必须形成不同 Turn；Embodied Scope 绑定当前 Body ID/generation 和一个连贯现场窗口；
Activity Scope 绑定一个 Trigger 或 Activity 因果链。因此一个 Frame 可以聚合多个兼容
事件，但不能混合独立会话、身体 generation 或 Activity 原因。cutoff 之外的事件留给后续
Turn。无法准入必须产生可观察的延后、拒绝或背压结果，不能静默丢失。

### 上下文与思考

[Reasoning Core 单 Turn Agent 详细设计](../designs/elfie/brain/elfie-reasoning-core)是本节的已接受
解释；已完成的 P0 主人聊天边界由聚焦的架构、上下文、Memory、Runtime、Receipt 与
重启测试守护。

Event Workspace 与 Reasoning Context Workspace 完全不同。Event Workspace 拥有事件 Lane、
准入和不可变单域成帧；Reasoning 内部 Context Workspace 拥有有界最近交替对话、活跃话题、
带来源的上下文摘要、本 Run Observation、待确认 Memory handoff 和自己的有界恢复
checkpoint。它不是平级心智系统；Memory 不拥有短期 conversation tail、context summary、
Run 草稿状态或通用上下文缓冲。

思考中枢只组装本 Turn 需要的上下文。上下文快照记录 Constitution 与 Selfhood revision，
以及自我定位、情绪、能量、动机、记忆、Activity 和有效能力的版本与采集时间；这些 owner
投影在 Run 内只读且保持冻结。Snapshot 不含 Profile 或 Canon 运行时投影，并区分事实、
推测和未知。

每个 Turn 都可以执行基础 Memory Recall。需要解析人物、指代、冲突或缺失事实时，认知步骤
可以通过 Reasoning 自有 Memory Bridge 请求额外有界 Recall。同一 Run 使用的全部 Recall
必须绑定一个明确 Memory revision；除非完整 Run context 整体 rebase，否则禁止混合 revision。
Reasoning 拥有查询意图、时机和上下文放置，Memory 拥有检索语义、来源、冲突处理、校验和
持久提交；模型不能直接读写 Memory。

每次模型调用前，Reasoning 都从冻结快照和当前 Context Workspace 重建一份
provider-neutral model context。它先预留回复 headroom，优先保留当前 Frame、可信 Scope、
未解决事项和完整 Action/Observation 配对，再裁剪低相关材料。Prompt 压力下的压缩生成
Reasoning 自有、带来源的 `ContextSummary`；持久捕获是另一条完整、带来源
`ClosedEpisode` 与类型化候选交给 Memory 的线路，有损摘要不是持久事实。只有收到 Memory
Receipt 后才能删除 pending handoff。

`DIRECT` 与 `DELIBERATE` 是根据上游提示、任务复杂度/风险、Energy、截止时间和可用模型能力
选择的 Reasoning 深度；它们不改变 Memory 可用性或硬权限。Food 只选择请求模型角色和回退
路线，不定义认知模式，也不携带另一套模式 allow-list。Skill、Tool 和 Worker 是彼此独立的
阶段能力门。

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

Memory、Emotion、Orientation、Energy 或 Motivation 候选属于 Turn 结算材料，不是第四类
行动。这里刻意没有 Selfhood：第一阶段没有更新路线；未来更新也只能走上文定义的
Memory-owned 整理 proposal，不能成为普通 Turn 输出。结算把每个获准候选或回执交给真实
所有者；所有者根据当前版本和因果身份校验后提交。陈旧或重复结果必须拒绝或对账，不能
只通过下一轮 Prompt 假设状态已经修正。

具身决定从当前 Body 和其他已授权所有者提供的只读能力目录中选择一个或多个能力，形成有限计划。
每个结构化调用包含大类、动态 `capability_id`、类型化参数、call/cause 身份、截止时间和当前主体。
`go_to`、`turn`、`speak` 等具体名称是能力目录条目，不是 Brain 固定的决定联合类型。同一外部域内的
调用可以有序执行或并发执行。调用由 NervousSystem 校验并通过当前 BodyBinding 路由；Brain 不选择
Adapter、Transport 或 Gateway。

具身动作账本记录 `ACCEPTED`、`STARTED` 供对账，但它们不是发给 Brain 的事件。Brain 只
接收一个终态：`COMPLETED`、`REJECTED`、`FAILED`、`INTERRUPTED` 或 `TIMED_OUT`。
取消统一表示为带原因的 `INTERRUPTED`。Watchdog 将逾期动作转为 `TIMED_OUT`，请求
stop/cancel；迟到的终态按幂等规则对账，不能重新打开动作。第一版允许隔离执行 Worker
等待终态，但 Gateway 接收器和传感入口必须保持工作；完全非阻塞的 BodyPort 提交/回执流
延后到第二版。

## 响应范围

- Communication Turn 可以产生 Communication 指令、已校验跨回合活动请求或 `No-op`，
  不能产生 NervousSystem 指令。直接回复必须留在被接纳的渠道/会话；联系另一个人或
  会话必须形成经过校验的后续 Scope。
- Embodied Turn 可以产生 NervousSystem 指令、已校验跨回合活动请求或 `No-op`，不能
  产生数字消息指令。
- Activity Turn 可以在自身 `ExecutionScope` 允许范围内选择至多一个外部域，可以创建或
  更新已校验 Activity，也可以选择 `No-op`。
- 澄清必须使用当前来源域。目标身份、联系方式、能力、时间语义或成功条件缺失时，应尽量
  在原始 Turn 当场确认，不能拖到 Activity 到期时才发现。

## 跨回合活动生命周期

跨回合活动拥有 `Goal -> Activity -> ActivityStep -> ActivityRun` 语义，但不拥有第二人格
或第二套推理引擎。Turn 提交持久 Activity 前，思考中枢可以把无副作用的 `ActivityDraft`
同步交给 Preflight。Preflight 检查目标身份、联系方式、能力、预算、时间语义、依赖、
成功条件和执行 Scope，并返回 `VALIDATED`、`NEEDS_CLARIFICATION` 或 `REJECTED`；它不
产生持久化或外部副作用。

只有已校验 Draft 可以在 Turn 结算后正式提交。到期时间、条件或重试产生类型化 Activity
事件；外部身体或消息回执保留在自己的外部来源域，不能变成 Activity 事件。这些事件都
不能直接执行开放行动。通信与具身后果必须是不同 Activity Step 和不同 Turn。稳定因果 ID、
幂等键、Checkpoint 和回执保证中断或重启后不丢承诺、不重复副作用。

动机和心智整理不能直接创建 Activity，只能产生重新进入事件工作区的 Activity Turn 候选。
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

`MemoryState`、`SelfhoodState`、`ReasoningContextWorkspaceState`、
`ReasoningRunState` 和 `ActivityState` 必须分离。Reasoning Context Workspace 的有界
checkpoint 只服务崩溃恢复，不是持久 Memory。持久认知基础设施按各 owner 需要提供状态、
Event Journal、Run/Activity Checkpoint、预算账本、因果 Trace、幂等记录和回执对账；这不代表
每个心智 owner 都进入一个通用 checkpoint，也不会形成第十一个心智系统。

重启后，Brain 从各自唯一 authority 加载持久 owner，对账未完成 Directive 和 Activity，拒绝旧身体
generation，只恢复 Scope 和截止时间仍然有效的工作。Emotion 是明确例外：进入睡眠
或进程重启时，当前六通道存量和临时指导回到人格基线。模型服务缺失只会延后或降级开放
认知，不能擦除身份、记忆、承诺或基本反射能力。

## 依赖与目录规则

Brain 只依赖自身定义的强类型使用方 Port 和 Elfie 语义契约；普通 Brain 运行期也不依赖
Profile、Canon、Genesis 资料包或领养输入。Brain 不导入 App、Nest、具体
Infrastructure、Provider SDK、平台 Payload、设备传输、文件系统 Root 或数据库 Record。
AI Runtime 实现留在 Brain 外部；Brain 拥有在 Run 中何时以及为什么调用它们。

规范包名是 `workspace/`、`orientation/`、`selfhood/`、`emotion/`、`energy/`、
`motivation/`、`memory/`、`reasoning/`、`activity/` 和 `consolidation/`。每个包必须拥有
真实状态、契约或行为；禁止恢复同义根级扁平模块，也禁止只有架构形状的空目录。

私有认知协调和上下文组装归 Brain。根 Elfie Facade 可以启动、停止和观察聚合，但不能
拥有 Turn 状态、模型循环或心智状态。产品实现只能通过一致性台账记录、另行批准的垂直
切片推进；本契约本身不授权迁移源码。
