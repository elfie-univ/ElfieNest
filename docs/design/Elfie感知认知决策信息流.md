# Elfie 感知、认知、决策与执行信息流

## 目标与边界

本文描述单只 Elfie 在进程内的正式信息流。核心原则是：外部采样节奏、物理
时钟、情绪与能量演化、模型推理和输出执行彼此解耦，但通过具名、不可变、可
校验的数据契约保持因果关系。

`elfie/` 只实现一只完整精灵。`app/orchestration/` 负责把 Elfie、Nest 和
AI Runtime 装配到同一产品进程；Nest 不持有 Elfie 实例；Godot 和第三方平台
的原始协议不能进入 Brain。

## 模块拓扑

```text
外部物理世界
  -> Body -> BodySensorEvent
  -> NervousSystem -> PerceptionEvent / PerceptionStateUpdate / PerceptionMediaSample
                         |
数字通信平台              |
  -> CommunicationEnvelope -> CommunicationPerceptionAdapter
                         |
执行回执 -----------------+
                         v
                  PerceptualWorkspace
                         |
                  BrainCoordinator
                         |
                     BrainContext
                         |
                   CorticalRuntimePort
                         |
                     DecisionPlan
                         |
                     OutputRouter
                    /      |       \
          NervousSystem  Communication  Internal
               |             |             |
              Body        Channel       Brain-owned action
                    \      |       /
                     ExecutionReceipt
                            |
                  PerceptualWorkspace
```

`PerceptualWorkspace` 位于 `elfie/brain/` 根层，是 Brain 的输入边界设施，不是
第四个脑功能层，因此禁止新增 `brain/perception/` 子包。

## 稳定数据契约

跨模块对象使用 Pydantic v2 不可变模型，拒绝未知字段，进程内直接传对象；只有
Godot、第三方平台、配置文件等边缘适配器负责 JSON 或字典解析。

| 边界 | 输入 | 输出 |
| --- | --- | --- |
| Body | `BodyCommand` | `BodySensorEvent`、`CommandReceipt`、`BodySnapshot` |
| NervousSystem 到 Brain | `BodySensorEvent` | `PerceptionWrite`、`IngestReceipt` |
| Communication | `CommunicationEnvelope` | `DeliveryReceipt`、`SocialPayload` |
| Brain 输入 | `PerceptionWrite`、`BrainClockPulse` | `PerceptionFrame` |
| 上下文编译 | `PerceptionFrame` 与各模块快照 | `BrainContext`、`ModelGenerationRequest` |
| 皮层决策 | `ModelGenerationRequest` | `DecisionPlan` |
| 输出执行 | `DecisionPlan` | `ExecutionBatch`、`ExecutionReceipt` |
| 轮回观察 | frame、plan、receipts | 最小 `TurnOutcome` |

公共契约的版本化 JSON Schema 位于 `docs/contracts/elfie/v1/`，由
`scripts/export_elfie_contract_schemas.py` 生成，禁止手工修改。

## 上行感知流程

### Body 与 NervousSystem

Body 只负责连接设备、采集完整事件和执行命令。语音以一句完成的
`UtteranceFinal` 上报；视觉可以上报外部媒体引用或变化摘要；触觉、环境和本体
感觉各自使用闭合 payload。原始视频帧和 PCM 不进入事件日志。

NervousSystem 对每个 `BodySensorEvent` 依次执行身份保留、反射判断、过滤和规范
化。达到危险阈值的触觉事件会立即向当前 Body 发出急停或反射命令，同时仍把
事实写入 Workspace，并提高 urgent revision。普通事件只进入认知候选，不直接
调用模型。

### Communication

数字消息不经过 NervousSystem。平台适配器先把一条完整消息解析为
`CommunicationEnvelope`，CommunicationHub 执行通道校验、策略、外部 ID 去重和
收件箱记录，再由 `CommunicationPerceptionAdapter` 发布 `SocialPayload`。

Godot 的 owner 数字消息也只走 Communication。房间内真实听见的声音才走
Body/NervousSystem，从而避免同一消息同时作为“听见”和“收到聊天”重复进入。

### Workspace 与背压

Workspace 是多生产者、单消费者结构。Body adapter、Communication adapter 和
输出执行器都只能通过 `PerceptionSink.publish()` 写入；只有 BrainCoordinator
可以 seal、claim、commit 或 release frame。

可靠事件容量不足时返回可重试的 `BACKPRESSURED`，producer 保留事件并重试，
禁止静默丢弃。状态更新可按 key 合并，媒体采样可按 stream 取代表样本，但合并
和丢弃数量必须进入统计。frame 只有在 plan 被 Router 原子接受后才 commit；失败
或取消会 release，以便重放。

## 时钟、frame 与认知轮回

物理 tick 只推进 Nest，并向每只活跃 Elfie 发布 `BrainClockPulse`、泵 Body 事件
和通信重试，不等待模型、语音合成、动作或平台发送。

BrainCoordinator 是单写者线程。它根据显式仿真时间推进 Emotion 与
Homeostasis，不为二者另开衰减线程。事件刺激在 Brain owner 线程应用；每次构建
上下文时生成不可变 `EmotionSnapshot` 和 `HomeostasisSnapshot`。因此即使模型
推理很慢，物理时间和新感知仍能继续进入下一 frame。

认知轮回不是“每条消息一次”，而由 `TurnTriggerPolicy` 决定：

- 紧急事件立即触发；
- 同一会话等待短暂 quiet window，同时受 hard max 限制；
- 高显著度、容量或最老事件阈值可以触发；
- 没有外部输入时可由 autonomous deadline 触发。

一只 Elfie 同时最多有一个 in-flight cortical turn。seal 时的 `cutoff_seq` 固定
本轮 frame；推理期间到达的事件不会混入旧 frame，只进入下一轮。

## 上下文与模型决策

BrainCoordinator 封口后读取当前情绪、能量、Body/Channel 有效能力、短期对话和
Memory 检索结果，由 `ThalamusContextBuilder` 形成 `BrainContext`，再由
`ModelContextCompiler` 编译成 provider-neutral 请求。所有外部文字都标记为数据，
不能覆盖 system policy；ActorRef、event ID、channel、conversation 和因果 ID 始终
保留。

模型必须返回 `DecisionPlan`。一个 plan 可以同时包含多条 `MessageIntent`、
`SpeechIntent`、`MotionIntent`、`ExpressionIntent`、`InternalIntent` 或
`NoOpIntent`，并声明依赖、截止时间和取消策略。

Runtime 根据模型能力选择一次主要结构化生成。结构校验失败时最多修复一次；仍
失败时只能把同一原始文本降级为安全 `SpeechIntent`，没有安全文本则生成
`NoOpIntent`。小模型不会因为不支持复杂结构而伪造动作。

## 下行输出与取消

OutputRouter 是唯一输出入口。它先对整个 plan 校验目标、能力版本、依赖 DAG、
截止时间和幂等 ID，再原子接受：

- speech、motion、expression 经 NervousSystem 转成 `BodyCommand`；
- message 直接交给 CommunicationHub 和对应 channel；
- internal 只交给 Brain-owned executor；
- noop 只产生审计结果。

每个 intent 产生 accepted、started 和终态 `ExecutionReceipt`，回写 Workspace，
成为下一轮可感知事实。危险输入会使旧 plan stale：尚未开始的输出按取消策略
取消；可中断的运行中动作收到急停；已经完成的外发消息保持真实完成状态，不
伪造撤回。

## 生命周期与并发所有权

每只 Elfie 独立拥有 Workspace、BrainCoordinator、CorticalWorker 和
OutputRouter worker。启动顺序是 Router 后 Coordinator；停止时先阻止新输入，
再停止 Coordinator、Router 和 worker，并 join 所有线程。Emotion、Energy 和
Memory 只能由 Brain owner 修改；producer 不能直接写这些对象。

`elfie/state/` 已删除。Profile 是稳定档案；情绪、能量、运行时间和身体绑定只在
对应模块内存中存在，重启后从默认值开始。调试观察使用 `TurnOutcome` 和 receipts，
不恢复聚合动态状态。

## 后续阶段

以下内容尚未在本阶段交付：

1. D1：来源正确的多角色记忆、关系建模和完整 `CognitiveTurnTrace`，并将调试台
   的临时同步适配器迁移为正式 trace/debug command。
2. D2：根据 scene、realm 和 device availability 控制手机 App、精灵内在通信等
   能力；当前只根据已连接 channel 和当前 Body 形成 `EffectiveCapabilities`。
3. D3：跨多只 Elfie 的公平推理准入和 urgent reserved capacity；当前每只 Elfie
   只有独立单 worker，共享 Runtime 仅保证调用串行安全。

这三项不属于当前核心闭环的完成声明。
