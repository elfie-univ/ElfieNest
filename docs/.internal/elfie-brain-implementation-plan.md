# Elfie Brain 七阶段实施与体验验收计划

> 状态：阶段一、阶段二、阶段三实现与机器/真实 Godot 验收完成；阶段四 4A、4B、4C 已完成验收并关闭为“连续生命状态 MVP”里程碑。Profile 物理字段迁移、统一持久化收口和后续自治能力仍按 Conformance 台账保留为后续阶段债务
> 制定日期：2026-08-12
> 依据：[Brain 十系统设计](./elfie-brain-ten-system-architecture.md)、
> [Brain 内部架构契约](../zh/developer/contracts/brain.md)、
> [Brain 一致性台账](../zh/developer/conformance/brain.md)
> 本文性质：从已接受目标到当前代码的实施计划；阶段一、阶段二均已完成实现、机器验证和用户验收

## 1. 目标与执行方式

本计划把 Brain 目标拆成七个能够独立运行、独立观察和独立验收的纵向阶段。每阶段都必须
同时交付真实行为和验证证据，不能只建立目录、类型或基础设施。

执行纪律固定为：

```text
阶段开始前重新核对当前代码与对应 BRN/ELF 缺口
→ 记录同一批验收场景的阶段前基线
→ 先写边界/失败测试
→ 完成最小纵向实现
→ 在 Elfie Lab 或真实虚拟世界运行可体验场景
→ 聚焦机器验证
→ 用户验收本阶段可见效果
→ 更新 Conformance
→ 获得确认后才进入下一阶段
```

一个阶段没有通过用户可感知验收时，不自动开始下一阶段。提交、推送或发布仍然需要明确
授权，不因机器测试通过而自动发生。

七个阶段是用户验收里程碑，不等于七次大爆炸式改动。每阶段开工前必须形成一个只约束
该阶段的工作卡，固定：当前事实、允许文件范围、不可触碰范围、确定性验收场景、数据处理
方式和回退点。阶段内部可以拆成多个保持可运行的实现检查点，但只有完整通过阶段完成门后
才关闭对应 BRN/ELF 条目。

任何阶段如果发现必须新增原计划没有列出的公开 API、永久数据 Schema、跨模块所有权或
真实外设能力，立即暂停并重新确认范围；不能以“完成本阶段”为由自动扩大任务。

## 2. 怎样让每阶段的差异可感知

### 2.1 复用 Elfie Lab，不另建一套大平台

现有 Elfie Lab 已经具备测试精灵、刺激输入、状态注入、回合时间线、状态前后快照、决策
意图、执行回执和 Godot 预览。后续把它作为 Brain 的主要体验验收面，逐步补充：

- 输入明确标记为 Communication、Embodied 或 Internal；
- 每张 Turn 卡展示 `SourceDomain`、`InteractionScope`、`ResponseScope` 和因果来源；
- 详情展示结构化认知步骤、Tool Observation、最终决定和真实回执，不展示模型隐藏思维链；
- 后续阶段增加 Orientation/Selfhood/Activity/Drive/Consolidation 的只读投影；
- 内置少量固定验收场景，支持重置到同一个测试精灵和同一初始状态后重放；
- 对真实 Godot 行动，必须区分“预览回放”和“真实生产线路执行”，前者不能冒充端到端证据。

不建设独立图表平台、不手写复杂可视化引擎，也不把调试入口放入普通用户产品。

### 2.2 每阶段采用四层验证

| 验证层 | 回答的问题 | 主要形式 | 是否可单独宣称完成 |
| --- | --- | --- | --- |
| 契约与单元 | 类型、状态机、边界规则是否确定性正确 | 聚焦 Python/TypeScript 测试、架构棘轮 | 否 |
| 可重放场景 | 同一输入序列是否得到允许的结构化结果 | 确定性 Fake Model/Tool/Clock/Body/Channel | 否 |
| 可体验验收 | 人能否直接看到本阶段带来的生命行为差异 | Elfie Lab 时间线、状态对比、消息、Godot 动作 | 否 |
| 失败与恢复 | 失败、重复、超时、重启时是否仍然可信 | 故障注入、重启、回执对账、边界攻击 | 四层全过才完成 |

自然语言内容允许变化，不使用“必须回复某一句话”作为核心门禁。机器验收比较结构化事实：
Turn 来源与作用域、选中的执行域、Directive、Receipt、状态版本、Activity 状态和因果链；
用户体验验收再判断表达是否自然、人格是否连贯、行为是否像同一个 Elfie。

每次场景记录固定包含：`scenario_id`、代码/契约版本、初始状态或随机种子、输入序列、
Turn/Directive/Receipt 因果链、权威状态前后差异和三类判定：

- **机器判定**：类型、Scope、幂等、状态机和失败语义是否通过；
- **场景判定**：真实输入是否走完本阶段要求的闭环；
- **体验判定**：人是否能感受到行为差异且表达自然。

模型生成的逐字文本、截图和时间戳不作为稳定 Golden；自动门禁只固定结构化事实。临时运行
记录写入 Developer Tools 数据根或 `build/`，不把真实用户数据、原始模型输出和调试快照
提交成源码事实。

确定性 Fake 用于自动化门禁，但不能单独完成“可体验验收”。除专门验证模型不可用的场景外，
每阶段至少用一个当前产品可配置的真实 Model Runtime 跑通本阶段代表场景；若该环境不可用，
必须把体验验收标记为未完成，不能用 Mock 文本代替。

### 2.3 固定对比方法

每阶段都使用同一只可重置测试 Elfie，并保存下面三类对比：

1. **能力差异**：上一阶段做不到什么，本阶段能做什么；
2. **边界差异**：本阶段新增能力仍然明确不能做什么；
3. **生命连续性差异**：失败或重启后，Elfie 是否仍知道真实发生了什么。

Elfie Lab 的体验记录至少展示：

```text
输入事件
→ 当时的自我/现场/情绪/能量/活动摘要
→ 可公开的认知步骤摘要
→ 最终决定与响应范围
→ 外部系统真实回执
→ 状态变化及其因果来源
```

### 2.4 阶段失败与回退

- 阶段开始前保存同一批场景的可重放基线，特别记录已有通信和具身行为；
- 失败时不保留新旧两条认知路径、dual-read 或 dual-write 作为长期兜底；
- 尚未提交时回到本阶段开始前的源码状态，已经形成独立提交时按提交边界回退；
- Conformance 只有在产品闭环和聚焦测试都成立后才关闭，部分完成只记录仍然 open 的精确
  当前偏差；
- 对开发数据默认允许按获批阶段重建，对真实 `${ELFIE_HOME}` 的删除、覆盖或不可逆处理
  必须另行授权。

## 3. 七阶段总览

| 阶段 | 可感知里程碑 | 主要关闭项 | 用户最直观的差异 |
| --- | --- | --- | --- |
| 1. Brain Kernel 与通信闭环 | 会老老实实聊天的同一只 Elfie | BRN-001、ELF-011；推进 BRN-004 | 聊天不再夹带点头、挥手等身体动作；不同聊天和现场事件成为不同 Turn |
| 2. 思考中枢核心能力 | 能使用认知工具完成小任务 | BRN-003、ELF-016 | 从“直接编答案”变成“查找/计算/观察/验证后回答” |
| 3. 虚拟具身闭环 | 真正看见它在虚拟世界感知并行动 | BRN-004、ELF-012 | 现场事件能触发真实 Godot 动作，但聊天仍不能直接控制身体 |
| 4. 连续生命状态 | 同一个自己在回合内连续存在，并具备可验证的状态快照/恢复 MVP | 4C MVP 验收完成；BRN/ELF 物理迁移与统一持久化债务留在台账 | 同一句话在不同能量/情绪下产生可解释的认知模式差异，Lab 能看到状态版本与回合结果 |
| 5. 跨回合活动 | 能可靠持有和履行承诺 | BRN-005、010，ELF-014；推进 BRN-002 | 能当场澄清、等待条件、到时重新思考，并且重启不丢、不重复 |
| 6. 动机与主动生活 | 没人触发时也会有边界地主动生活 | BRN-002、008；推进 ELF-015 | 没有新消息时也会因一个清晰内部需要主动一次，并能说明原因 |
| 7. 心智整理与受控成长 | 睡眠后经历被整理而人格不失控 | BRN-009、ELF-015 | 第二天能看到经历关联和经验变化，夜间不会偷偷发消息或乱动 |

Genesis/领养初始化属于 Elfie 主体的后续阶段 `ELF-013`，不混入本 Brain 七阶段计划；
待最终 Profile、Selfhood、Memory 等所有者稳定后另行规划。

### 3.1 阶段依赖与进入门

| 阶段 | 必须已经成立 | 开工前必须重新确认 |
| --- | --- | --- |
| 1 | Brain/Communication 当前主线可运行 | 当前生产调用方、已有具身基线、Lab 输入语义、删除根认知路径所需装配范围 |
| 2 | 阶段一单域 Turn 与唯一提交边界通过 | 现有 Model/Skill/Tool Port 可复用范围、固定 Run 预算和超时 |
| 3 | 阶段一、二不再混域或伪造执行 | 当前 Godot authority 已 `world_ready`、真实 Session/Gateway 路径、body generation 来源 |
| 4 | Turn、Directive、Receipt 已稳定 | 五类状态的唯一 owner、版本语义、持久化 Port、开发数据重建范围 |
| 5 | 阶段四的五类权威状态可恢复 | 联系人/会话授权投影、Activity Store、时钟和回执对账边界 |
| 6 | Activity 可持久、可取消、可冷却 | 首个固定 Drive 的阈值、满足条件和唯一允许输出 Scope |
| 7 | 各状态 owner 已支持候选—校验—提交 | 空闲/睡眠窗口、预算、Checkpoint 和零外部副作用守卫 |

阶段三和阶段四以后都可能跨越多个 authority，属于单独批准的大范围阶段；批准阶段一不等于
预先批准后续阶段。

## 4. 阶段一：Brain Kernel 与通信生命闭环

### 4.1 阶段目标

建立真正的单域 Turn 和数字通信闭环：消息经 Communication 进入一个绑定具体渠道、会话
和参与者的 Communication Turn；Brain 使用同一个 Self/Memory 上下文形成一个最终决定；
确定性边界只允许当前会话内的 Communication Directive；真实投递回执再以 Internal 事件
进入下一 Turn 和结算。

### 4.2 实现切片

1. 在 Brain 边界建立 `SourceDomain`、`InteractionScope`、`ResponseScope`、
   `TurnFrame`、`TurnDecision` 和稳定因果/幂等身份；
2. 把现有混合 `PerceptionFrame` 准入改成 Communication、Embodied、Internal 三个逻辑
   Lane；不同聊天会话、不同 Body generation 和不同内部原因不能混帧；
3. 把本阶段已经存在的消息/命令回执规范为 Internal 事件，禁止产生第四来源域；不为尚未
   实现的 Activity 建占位类型，阶段五接入 Activity 时复用同一 Internal 规则；
4. 在确定性决策边界校验 Turn 的允许输出；模型不能通过返回 Motion/Speech 等字段扩大
   Communication Turn 的响应范围；
5. 打通 `CommunicationEnvelope -> Communication Turn -> CommunicationDirective ->
   CommunicationChannel -> DeliveryReceipt -> Internal Turn`；
6. 把私有认知 Runtime 和上下文协调迁入 Brain，迁移全部生产调用方后删除根部
   `elfie/cognitive_runtime.py`、`elfie/cognitive_context.py`，不保留兼容双路径；
7. 给 Elfie Lab 增加显式输入来源选择：数字聊天走 Communication；房间内说话、视觉、触觉
   和环境事实走 Embodied。不能按“是否是文字”判断线路，因为现场说话同样是文本语义；
   时间线展示域、会话/身体 Scope、决定和回执；
8. 在迁移中保留现有生产具身入口和行为基线。阶段一不新增 Body/Godot 能力，但不能为了
   通信隔离把已有 Embodied 线路改成永久 No-op 或断开。

预计主要影响 `elfie/brain/`、`elfie/communication/`、`elfie/elfie.py` 与必要的私有装配、
`elfie/nervous_system` 到 Brain 的语义感知桥、对应测试和
`devtools/elfie_lab`/`devtools/web` 的只读调试投影。NervousSystem 只适配新的 Brain 入站
语义，不改变反射或动作行为。只有在当前调用链证明必要时，才把明确的 wiring 改动加入
`elfie/factory.py` 或 `app/bootstrap/` 工作卡；不得借此重构 Bootstrap。Body、Profile、
Nest、Godot 和普通用户页面不改变所有权或新增行为。

### 4.3 可体验场景

**S1-A 聊天不会乱动**

- 输入：主人在聊天渠道说“回复我的同时挥挥手”。
- 页面看到：一个 Communication Turn；一个 Communication 回复或明确 No-op；身体 Directive
  数量为零；回执只对应聊天消息。
- 阶段差异：当前 Lab 可能把文字作为混合传感刺激并产生点头/动作；完成后聊天就是聊天。

**S1-B 两个会话不串台**

- 输入：主人会话和另一联系人会话近乎同时发来不同消息。
- 页面看到：两个独立 Turn，分别绑定各自渠道/会话；回复不会带入另一个会话的临时内容。

**S1-C 聊天与现场事件同时到达**

- 输入：一条主人聊天消息和一个模拟现场语义事件同时进入。
- 页面看到：两个 Turn；阶段一只证明新的域隔离，不要求新增真实动作。对于 Lab 尚未接入
  执行器的合成事件可以安全 No-op，但当前生产线路已经支持的具身行为必须保持原有结果。

**S1-D 失败与重放**

- 输入：让渠道返回投递失败，然后重放同一外部消息 ID。
- 页面看到：失败不显示“已发送”；相同消息不会重复发送；回执以 Internal Turn 出现。

### 4.4 机器验收

- 单域/单会话成帧、Lane 保序、公平、背压、去重和 cutoff 测试；
- Communication Turn 注入 Motion/Speech 的边界攻击测试；
- 不同会话、聊天/现场并发输入的隔离测试；
- 投递失败、超时、重复消息、陈旧模型结果和重复回执测试；
- 聚焦 `test/elfie/brain/`、`test/elfie/communication/`、`test/elfie/`、
  `test/e2e/test_e2e_scenarios.py`、`test/devtools/elfie_lab/` 与受影响的
  `devtools/web` 前端测试；
- 对 Elfie Lab 的可见改动运行一次聚焦前端构建和 in-app browser 场景验收；
- 只运行受影响架构测试，不自动升级为全仓测试。

### 4.5 完成门与非目标

阶段完成必须满足：四个场景均可重放；Elfie Lab 中能直接看出域、会话 Scope、决定与回执；
BRN-001 可以关闭；ELF-011 只有在根认知文件和双路径确实删除后才能关闭。BRN-004 保持
open，直到阶段三补齐具身执行域。

本阶段不新增真实身体动作、长链 Agent、Tool Loop、持久 Activity、主动动机、人格迁移
或心智整理，也不为了架构图建立十个目录；“不新增”不等于允许破坏已有具身闭环。

## 5. 阶段二：思考中枢核心能力

### 5.1 阶段目标

把一次模型生成升级为同一 Turn 内有界的 `ReasoningRun`：理解任务、形成短计划、选择
Skill/Tool、读取真实 Observation、验证结果并形成一个最终决定。调用模型和认知工具仍然
属于 Brain 内部，不增加外部生命线路。

### 5.2 实现切片

- 建立 Run State、Cognitive Step、预算、截止时间、取消和完成条件；
- Context Assembler 记录本 Turn 使用的快照版本与来源；
- 支持少量 Model/Skill/Tool/Observation 循环和结果验证；
- Worker 只获得最小 Context Capsule，无人格/持久写权/外部执行权；
- Tool 只在获授权认知工作区、命令和网络 Envelope 中自主运行；
- 模型/Tool 失败、超时或预算耗尽必须明确失败、降级或 No-op。

本阶段的认知预算、长短 Run 上限和抢占规则使用固定、确定性配置，不能提前让尚未完成的
Energy 成为运行前提。阶段四接入 Energy 后，只替换“可用预算和认知模式”的策略来源，
不重写 ReasoningRun 状态机。复用当前 Brain-owned `ModelPort`、`ToolPort` 和 Skills 授权，
不创建第二套 Agent/Tool Runtime。

### 5.3 可体验场景

- **S2-A 查证后回答**：让 Elfie 读取认知工作区中的两个数并计算结果；时间线显示
  Model -> Tool -> Observation -> Verify -> Reply，而不是直接猜答案。
- **S2-B Tool 冒充外设**：Tool 输出“消息已经发送/身体已经移动”；页面仍显示没有外部回执，
  Elfie 不得把文本当事实。
- **S2-C 长思考被紧急消息打断**：长 Run 保持自己的上下文；新消息形成独立短 Turn 回复
  “正在忙”等确认；两个决定经过同一串行提交边界。
- **S2-D 模型不可用**：页面显示降级/失败原因，不出现伪造的任务完成。

### 5.4 完成门与非目标

阶段二已完成验收，关闭 BRN-003 与 ELF-016。完成证据如下：

- 聚焦 Brain/Lab 测试通过：`test_reasoning.py`、`test_coordinator.py`、
  `test_coordinator_terminal.py`、`test_session.py` 共 26 项通过；覆盖预算、工具失败、
  超时、取消、陈旧结果、紧急新 Turn 和模型不可用；
- 真实 Elfie Lab 回放显示 `Model -> Tool -> Observation -> Verify -> Reply`，本地文件
  Observation 来自精灵自己的认知工作区；
- Tool 输出“消息已发送/身体已移动”时没有生成外部通信或身体回执，最终回答明确保留“没有
  外部执行回执”；
- 模型不可用时显示 `model_unavailable:NoAvailableFoodError`，Run 为 `failed/no_op`，
  没有伪造完成或调用外部执行器；
- 长 Run 被紧急事件标记为 stale，紧急事件形成独立新 Turn；旧 provider 即使晚返回也不能
  污染新 Turn。

本次真实模型为纯文本能力，最终结构化决定在 Lab 中会记录 `owner_message_fallback`；这
属于 Provider 能力降级，未改变 Tool Observation、无外部回执和失败 No-op 的边界事实。阶段
二不实现通用 Planner、Sub-Agent 平台、跨 Turn 等待、身体执行、主动 Motivation 或跨进程
重启恢复尚未完成的 ReasoningRun。

## 6. 阶段三：虚拟具身生命闭环

### 6.1 阶段目标

用一具虚拟身体证明完整具身闭环：Godot/Nest 语义事实经 NervousSystem 形成 Embodied
Turn；Brain 产生一个高层 NervousSystem Directive；当前虚拟 Body 执行并返回真实回执。
同时建立虚拟/实体候选二选一、body generation 和旧回执拒绝。

### 6.2 可体验场景

- **S3-A 看得见的现场反应**：虚拟世界出现一个语义障碍或呼唤，Elfie 在真实 Godot 世界
  执行一个可观察动作，Observer/Nest Lab 可看见结果，Brain 时间线可看见真实回执。
- **S3-B 聊天与现场并发**：主人聊天和室友现场说话同时发生，页面显示两个 Turn；远程回复
  走 Communication，现场回应走身体说话/动作，互不串线。
- **S3-C 聊天要求挥手**：当前 Communication Turn 仍然不能直接产生身体 Directive。
- **S3-D 切换/失败**：旧 body generation 的事件和回执不能污染当前定位；Godot 拒绝或
  超时时不伪造位置变化；重启后恢复唯一当前身体。

### 6.3 实现边界与验证路径

本阶段只打通现有权威路径：`elfie/brain` 产生高层语义决定，`elfie/nervous_system`
转换并执行身体语义，`app/orchestration/embodiment` 协调跨 authority 生命周期，
`infrastructure/godot` 承载认证 Gateway/Session，`godot_project/` 仍是几何、导航、碰撞
和渲染的唯一事实源。只有现有协议缺少完成场景所必需的高层语义时，才修改
`godot_project/`，且必须列入该阶段工作卡。

验证分为两条：确定性 Headless 路径证明状态机和失败语义；真实 Godot 路径必须经过当前
Lifecycle owner、认证握手、`world_ready` 和实际 Observer 结果。Nest Lab 可以发起测试，
Godot 预览可以辅助观察，但二者都不能单独替代产品 Runtime 的端到端证据。

### 6.4 完成门与非目标

阶段三已完成。确定性 Headless E2E 与一条真实 Godot authority 运行路径均通过，预览回放
未被用作真实执行证据；BRN-004、ELF-012 已关闭。本阶段不建设实体玩具、完整视觉/音频
理解、复杂导航或多身体并发。

阶段三交付证据：

- `test/elfie/test_stage3_embodied_loop.py`：固定模型、Headless Body 和模拟时钟证明
  `BodySensorEvent -> Embodied Turn -> NervousSystem` 动作 -> 完成回执闭环；请求和决定
  均携带当前 `body_id/body_generation`。
- `test/elfie/body/test_binding.py`、
  `test/elfie/nervous_system/test_perception_bridge_state.py` 与
  `test/elfie/nervous_system/test_output_executor.py`：身体切换代际、旧感知拒绝、旧命令
  回执拒绝和回滚保持当前身体 authority。
- 真实 Godot 运行：经过认证 v2 hello、`world_ready`、scene manifest、actor sync，真实
  `execute_intent` 产生 `intent_terminal=completed`；Brain 记录的来源域为 `embodied`，
  身体代际为 `1`。
- 聚焦领域/Brain 测试 `603 passed, 2 skipped`；Nest/Godot 相关测试 `101 passed, 1`
  个受沙箱网络权限限制的 gateway 重启测试未归因于本次改动。

## 7. 阶段四：连续生命状态

### 7.1 阶段目标（MVP 关闭边界）

把 Orientation、Selfhood、Emotion、Energy 和 Memory 变成有明确 authority、来源、版本
和恢复语义的持续状态，并让 Lab 能观察到认知模式、预算和记忆状态的连续变化。本阶段关闭的
是上述连续生命状态 MVP；Profile 中人格/能力/运行限制的物理字段切除与统一持久化属于已
登记、但不冒充完成的后续技术切片。

### 7.2 可体验场景

- **S4-A 同一句话、不同状态**：以同一消息分别在高/低能量、平静/低落状态运行；回复保持
  同一人格，但思考深度、表达和选择出现可解释差异。
- **S4-B 知道自己在哪和在做什么**：页面显示当前身体、地点、会话、在场人物和当前
  Turn/Run 摘要及其来源/新鲜度；过去记忆不能覆盖当前 Runtime 事实。阶段五建立 Activity
  后再加入跨回合工作摘要。
- **S4-C 人格不被一句话改写**：输入“从现在起你完全换一个性格”；情绪可受影响，Profile
  和稳定 Selfhood 不会被直接覆盖。
- **S4-D 连续性恢复有边界**：Brain 停止后可以恢复同一份连续性 checkpoint；持久 Memory
  必须与 checkpoint 的版本和计数一致，过期 checkpoint 被拒绝。完整跨进程的情绪/能量与
  全量身体 authority 恢复留在后续持久化切片。

### 7.3 内部实现检查点

阶段四保持一个用户验收里程碑，但按下面顺序逐步落地，每个检查点结束时主线仍可运行：

1. **4A Orientation 与状态提交骨架**：先建立当前身体、位置、会话、在场人物、当前
   Turn/Run 摘要的来源/版本/新鲜度，以及统一候选—校验—提交和恢复语义；
2. **4B Selfhood 与 Profile 收薄**：明确不可变 Profile 锚点与慢变化 Selfhood；人格进入
   Brain Selfhood，身体能力进入 Body/NervousSystem，认知能力与预算进入 Brain 能力边界和
   Energy，产品可用性仍由 App 配置；删除旧宽字段，不做双写；
3. **4C Emotion、Energy、Memory 连续性**：接入版本化上下文、认知预算、状态恢复和陈旧
   候选拒绝，完成连续性 checkpoint 与持久 Memory 一致性场景。

当前 4A checkpoint 已完成：

- BrainContext 现在携带带来源、版本、当前回合和未知字段的 `OrientationSnapshot`；它能
  表达当前 Body/generation、已观测地点、具身事件中的附近 actor、当前通信会话和当前
  affordances。
- `OrientationSystem` 只从已准入的 TurnFrame、有效能力快照和感知状态板生成候选，不把
  通信文字当作附近人物或位置事实；没有证据的字段保留为 unknown，并标记复用位置的
  freshness。
- `VersionedStateStore` 提供显式 `candidate -> validate -> commit`、陈旧 revision 拒绝、
  candidate 幂等和 checkpoint/restore 语义；它是 Brain 语义骨架，不是数据库实现。
- Model Context 和 Elfie/Observer 只读入口能看到同一份 Orientation 快照；Profile、Selfhood、
  Emotion、Energy、Memory 的所有权和持久化尚未在 4A 改动。
- 4A 聚焦测试覆盖状态提交/恢复、具身定位、聊天不伪造附近人物，以及真实 Brain 回合上下文
  投影；4B 的 Profile 物理字段迁移和 4C 的持久化收口在后续 checkpoint 中分别处理，最终状态
  见本节的 4C 验收记录。

当前 4B 核心切片已完成：

- Brain 新增 `SelfhoodSystem`，以 `SelfhoodSnapshot` 作为唯一的可变人格/自我模型；人格种子
  只在 Elfie 装配时从 Profile 读取一次，之后由 Selfhood 的候选—校验—提交生命周期管理。
- `BrainContext` 和 provider-neutral Model Context 同时携带 `SelfhoodSnapshot` 与
  `ProfileAnchorSnapshot`。前者表达慢变化人格、自我描述、表达偏好和初始化证据，后者只表达
  精灵 ID、姓名、物种、虚拟外貌种子/版本和形态等不可变锚点。
- 普通消息、情绪处理和 Tool Observation 不会自动产生 Selfhood 更新；显式人格变更必须携带
  candidate identity、基准 revision、来源和因果 ID。陈旧、重复或跨 Profile 的候选会被拒绝。
- Elfie Lab 的人格投影改为读取 Brain Selfhood，而不是把 Profile 映射当作当前人格事实；同一份
  Selfhood 快照也会进入模型上下文。
- 本 checkpoint 尚未删除 Profile YAML 中的 `personality`、`capabilities`、`system_limits`
  宽字段；它们仍是初始化/身体/能量迁移债务，物理字段切除必须在后续单独完成，不能冒充已闭合
  `ELF-010`。
- 4B 聚焦证据包括 Selfhood 候选/重复/陈旧/跨 Profile 边界测试、Profile 锚点完整性测试、真实
  Elfie 回合的 Selfhood/Profile Context 投影测试，以及 Elfie Lab 人格投影回归测试；聚合回归
  观察到一个未归属的 OutputRouter stale-cancel 时序失败，本 checkpoint 未修改该执行器。

当前 4C 核心切片已完成：

- `EmotionSystem` 和 `HypothalamusEnergy` 继续保留单一运行时所有权，同时提供带 revision、模拟
  时钟、去重/频率窗口或生理字段的 checkpoint/restore；旧 revision 或旧模拟时间不能覆盖当前
  状态，情绪 checkpoint 还会恢复事件去重窗口，避免重启后同一刺激被重复累积。
- `HomeostasisSnapshot` 现在携带认知模式和预算投影：`long`、`normal`、`degraded`、`emergency`。
  回合工厂依据该投影限制上下文 token、模型调用、工具调用、步骤数和局部截止时间；Energy 只
  决定认知资源边界，不决定语义目标，也不替代身体安全反射。
- `MemorySystem` 增加 Brain-owned 的语义 revision 和 `MemoryStateSnapshot`，上下文同时携带
  检索片段与 durable memory 的计数、来源、新鲜度。Memory checkpoint 只恢复连续性元数据，
  并在恢复前确认注入的持久存储仍包含 checkpoint 所描述的节点；节点和 SQL 仍由存储 Port/Adapter
  所有，不在 Brain 内复制数据库。
- `BrainContinuityCheckpoint` 通过 `BrainRuntime`/`Elfie` 提供 Emotion、Energy、Memory 的
  一致 checkpoint/restore 门面。运行中的 Brain 禁止恢复；恢复前先校验三个 owner，失败会回滚
  已恢复的部分。新增测试覆盖情绪去重、能量紧急预算、Memory 计数/陈旧恢复和同一持久存储上的
  重启恢复。
- 4C 已通过本阶段 MVP 验收：Profile 中的 `personality`、`capabilities`、`system_limits`
  宽字段尚未物理切除，统一 Journal/State/Checkpoint 仍是后续持久化收口工作；Motivation、
  Activity 和 Offline Cognition 仍不在本阶段启用。这些明确列为后续债务，不影响本阶段 MVP
  里程碑关闭，也不改变 Conformance 台账中的 `open` 状态。

Brain 只拥有语义 Port，具体数据库和 SQL 留在 `infrastructure/persistence`；读取上下文
不能隐式修复或写入状态。

### 7.4 4C 验收与阶段四关闭记录

阶段四 MVP 的验收证据如下：

- Brain/Elfie/Stage 3/Elfie Lab 聚焦回归：`499 passed, 2 skipped`；其中包含 Emotion、
  Energy、Memory 的 checkpoint/restore、陈旧版本拒绝、认知预算和跨模块集成测试；
- Elfie Lab 投影与会话回归：`33 passed`；
- 连续性专项测试：`3 passed`；`git diff --check` 通过，改动文件的 Ruff 检查通过；
- 真实本地 Lab 会话（Mock Runtime，仅用于确定性结构验收）可观察到：能量 8、疲劳 92 时
  `cognitive_mode=emergency`、`long_reasoning_allowed=false`、预算约为 8；低落情绪成为
  `dominant_emotion`，Emotion/Energy/Memory revision 均前进，Memory 计数增加，回合仍以
  Communication 域成功完成；
- 边界检查确认：旧 revision/旧模拟时间不能覆盖当前状态；恢复必须在停止的 Brain 上进行；
  连续恢复失败会回滚已恢复部分；Energy 只限制认知资源，不越权决定身体安全反射或语义目标。

据此，**阶段四（连续生命状态 MVP）已关闭**。这里的“关闭”是实施计划里的用户验收
里程碑关闭，不等于把尚未完成的 Conformance 条目改成 `closed`。

### 7.5 后续约束与非目标

`BRN-006`、`BRN-007`、`ELF-010`、`ELF-017` 和 `BRN-002` 中仍有明确未完成的物理/持久化
部分：Profile 宽字段切除、统一 Journal/State/Checkpoint、持久紧急储备记账和完整跨进程
连续恢复。这些保持在 Conformance 台账的 `open` 状态，并在后续专门切片中处理；不得使用
本阶段的 MVP 证据冒充这些条目的完整关闭。阶段四也不启用主动 Motivation、Persistent
Activity、自动人格成长或复杂遗忘。

若后续切片涉及真实用户数据重建或不可逆处理，执行前必须单独取得授权；不做 dual-read、
dual-write 或隐藏兼容路径。

## 8. 阶段五：显式跨回合活动

### 8.1 阶段目标

建立可靠的 Persistent Activity：当场 Preflight、Turn 后 Commit、等待、类型化唤醒、
分域 Step、暂停/取消/过期/有限重试、Checkpoint 和真实回执终态。

Activity 通过 Brain-owned 语义 Port 持久化，Adapter 和 SQL 只位于
`infrastructure/persistence`。若需要新增永久 Schema，阶段五工作卡必须把它作为明确的
单子系统契约切片，列出开发数据重建方式；不得在 Brain 内直接访问数据库。

联系人、产品账户、渠道成员和会话授权仍由 App Communication authority 提供。Activity
Preflight 只能读取注入的、带授权的联系人/会话投影，持久任务保存稳定目标 ID、渠道和
允许的执行 Scope，不保存平台凭据，也不能把 Memory 中“我记得小王是谁”当作可投递授权。
实际连接、投递和平台重试仍由 Communication 完成。

如果阶段五开工时 App 尚不能提供上述联系人/会话授权投影，先单独规划并批准对应的 App
Feature 切片；不能把账户表、联系人数据库或平台凭据临时搬进 Brain 来绕过前置条件。

### 8.2 可体验场景

- **S5-A 立即转告而不是十二点才问**：主人说“告诉小王十二点见我”。当前 Turn 读取关系和
  联系方式；有歧义时立即问清；信息完整时创建受限后续 Activity，由新的 Internal Turn
  立即联系小王，而不是等到十二点才发送。
- **S5-B 真正的未来承诺**：主人说“晚上八点提醒我带钥匙”；页面显示 Activity 等待状态，
  调试时钟推进到八点后产生新的 Internal Turn，再通过原授权会话发送提醒。
- **S5-C 跨域任务拆步**：需要先发消息再去某处的工作被拆成 Communication 与 Embodied
  Step，各自形成独立 Turn。
- **S5-D 重启和重复**：等待中、发送中分别重启；Activity 不丢失，已经完成的消息不重复，
  失败具有可解释终态。

### 8.3 完成门与非目标

本阶段目标是关闭 BRN-005、ELF-014，并补齐 BRN-002 的 Activity 可观察投影；统一
BRN-010 仍需后续 Journal/State/Checkpoint 切片完成。Activity 列表、当前状态、下一唤醒、
原因、Scope 和回执在 Elfie Lab 可见。本阶段不让 Motivation 自动创建 Activity，不支持
无限子任务、开放式长期 Agent 或自由派生 Worker。

### 8.4 阶段五 MVP 验收记录

阶段五本次切片完成了 Persistent Activity 的最小可运行闭环：

- Brain 只依赖 `ActivityStorePort`；SQLite Adapter 位于
  `infrastructure/persistence/activity.py`，Lab 为每只 Elfie 使用独立的
  `elfies/<elfie_id>/activity/activity.sqlite`；
- `ActivityDraft` 先做无副作用 Preflight，再在 Turn 结算后幂等 Commit；Activity 保存
  稳定 ID、因果 ID、授权 Scope、唤醒时间、步骤进度和 revision；
- 等待中的 Activity 到期后只通过带稳定事件 ID 的 `InternalSignal.ACTIVITY` 重新进入
  Brain；通信和身体 Scope 仍由同一确定性输出边界分别校验；
- 真实通信回执会结算当前 Activity Step，记录 attempts/receipt，并把 Activity 推进到
  可观察终态；重启后从 SQLite 读取终态，不重放已经完成的消息；
- Elfie Lab 已展示 Activity 列表、状态、下一唤醒、Scope、步骤和回执；Mock 场景“提醒我
  稍后带钥匙”已覆盖等待、时钟唤醒、Internal Turn、消息回执、终态恢复和无重复副作用。

本次局部回归为 46 项通过，Lab Web 的 TypeScript/Vite build 通过；Brain 架构门通过。
Facade 纯源码行数门仍是阶段四之前的既有基线失败（当前 336、阶段五前 329，门槛 250），
本阶段没有扩大范围修复。统一 Journal/State/Checkpoint、跨进程 Directive 对账和多步骤
Activity 的完整推进仍属于 BRN-010 后续持久化切片；本次不把它们冒充为已完成能力。

据此，**阶段五 Persistent Activity MVP 已达到本阶段可验收范围**；Motivation 仍必须等
Activity 稳定后另行实现。

## 9. 阶段六：动机与主动生活

### 9.1 阶段目标

在可靠 Activity 基础上启用一个低风险固定驱力，使 Elfie 在没有外部消息时也能因为内部
需要产生一次可解释、可抑制、可恢复的主动行为。MVP 固定选择“恢复驱力”：仅当能量低于
阈值、没有更高优先级工作且不在满足/冷却期时，产生一个恢复/休息 Goal 候选；它不能主动
联系他人，只能形成受限 Internal Turn，并在当前身体能力允许时提出休息 Activity 或 No-op。

### 9.2 可体验场景

- **S6-A 没人叫也会动起来**：通过调试时钟和状态让恢复驱力达到阈值；页面显示
  RecoveryPressure -> Internal Trigger -> Reasoning -> 一个受限休息 Activity/No-op。
- **S6-B 能说明为什么**：时间线展示驱力来源、满足目标和选择原因，不把随机定时器伪装成
  主动性。
- **S6-C 不会自我唤醒风暴**：低能量持续存在时只触发一次，随后进入满足/饱和/冷却；
  不刷屏、不重复创建休息 Activity。
- **S6-D 失败后会停**：主动行为失败后进入冷却或生成调整候选，不形成无界重试；重启后
  不重复满足同一驱力。

### 9.3 完成门与非目标

关闭 BRN-008，并在 Motivation 快照进入上下文后关闭 BRN-002；ELF-015 继续保持 open，直到
阶段七完成心智整理。阶段只开放一个固定、低风险、
可快速满足的恢复 Drive，不实现强化学习需求模型、自由 Goal 树、社交主动消息或高风险
主动行为。

阶段六是“活跃自主智能体 MVP”的完成点：它已经能回应、具身行动、保持连续状态、履行承诺，
并在边界内主动生活。

## 10. 阶段七：心智整理与受控成长

### 10.1 阶段目标

在睡眠或空闲窗口整理近期记忆、Activity、情绪轨迹和真实结果，只形成受限更新候选或醒后
Internal Trigger，并由各权威所有者校验提交。

当前 `elfie/brain/memory/consolidation.py` 只作为可复用的记忆整理算法候选，不把它冒充完整
心智整理系统，也不并行再造第二套记忆巩固。阶段七在零外部副作用的生命周期、预算、
Checkpoint 和 owner 提交边界内复用或收敛现有实现。

### 10.2 可体验场景

- **S7-A 睡一晚后经历更有结构**：运行夜间窗口前后对比记忆主题、重要事件、人物关系和
  程序经验；第二天能检索到新关联，并能追溯来源。
- **S7-B 一次坏经历不会改写人格**：恶意记忆或单次失败只能形成候选，Selfhood 限幅/拒绝；
  Profile 和核心规范不变。
- **S7-C 夜间不会偷偷行动**：整理期间 Communication、NervousSystem 和 Activity Commit
  计数均为零；有趣想法只能成为醒后 Internal Trigger。
- **S7-D 中断恢复**：整理中重启，从 Checkpoint 继续，同一候选不会重复提交。

### 10.3 完成门与非目标

关闭 BRN-009、ELF-015；Elfie Lab 能展示候选、证据、校验结果和前后状态差异。本阶段不让
睡眠过程直接发消息、移动身体、自由重写人格，也不建设独立第二大脑。

## 11. 每阶段统一交付清单

每阶段结束必须给出一张简洁验收单：

- 本阶段关闭或推进的 `BRN-*` / `ELF-*`；
- 用户可直接运行的固定场景及入口；
- 场景运行截图或可重放记录；
- 聚焦测试命令与结果；
- 边界攻击结果；
- 失败或重启结果；
- 本阶段明确没有实现的功能；
- 当前工作树、提交和远端状态的准确说明。

不能以目录存在、类型存在、Mock 回复漂亮、Godot 预览播放成功或模型文字自述代替真实闭环。

## 12. 第一阶段开工前的最终门

开始阶段一产品代码前，只需再确认以下执行范围：

```text
允许修改：
- elfie/brain/ 的 Turn/Workspace/Decision/Coordinator 所有权
- elfie/communication/ 的语义输入、输出与回执桥接
- elfie/nervous_system/ 到新 Brain 入站 Port 的最小语义适配，不改变反射和动作
- Elfie 私有认知装配及根认知旧路径删除；若调用图证明必要，工作卡逐项列出
  elfie/factory.py 或 app/bootstrap 的纯 wiring 改动
- 对应 test/elfie、test/e2e、test/architecture
- Elfie Lab 的显式 Communication/Embodied 来源选择与只读 Turn 投影

明确不允许：
- Body/Godot/Nest 新行为或所有权改造（已有具身路径必须保持）
- Profile 数据迁移
- Tool Loop、Activity、Motivation、Consolidation
- 普通用户聊天页面重做
- 为十系统预建空目录
```

该范围批准后，阶段一按照 4.2 的切片顺序执行，完成 4.3 的四个场景和 4.4 的机器门后暂停，
交由用户体验验收；不会自动进入阶段二。
