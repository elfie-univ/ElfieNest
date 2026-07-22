# Elfie 架构说明

本文原先描述的同步 `SensorData -> BrainDecision` 链路已经删除，不再作为当前实现
依据。

当前权威文档如下：

- `docs/design/Elfie感知认知决策信息流.md`：单精灵上下行信息流、数据契约、时钟、
  frame、认知轮回、输出路由和并发所有权。
- `elfie/README.md`：`elfie/` 目录职责和公共 API。
- `docs/design/ElfieNest目录架构.md`：仓库模块边界和依赖方向。

旧的 `SensorData`、`BrainDecision`、`perceive_and_respond()`、
`respond_to_body_events()`、`brain/cognition/` 和 `elfie/state/` 不得恢复。

当前 `elfie/` 是单精灵内核：Body 的物理感知经 `NervousSystem` 写入
`PerceptualWorkspace`，数字消息经 `CommunicationHub` 写入同一个工作区；
`BrainCoordinator` 按自己的节奏读取 frame、情绪、能量、记忆和能力，生成
`DecisionPlan`，再由 `OutputRouter` 分发到 NervousSystem、Communication 或内部
intent。

旧的 `SensorData`、`BrainDecision`、`perceive_and_respond()`、
`respond_to_body_events()`、`brain/cognition/` 和 `elfie/state/` 不得恢复。Godot
虚拟房间内的说话以语义文本广播为准，不恢复自动 TTS 音频管线。
