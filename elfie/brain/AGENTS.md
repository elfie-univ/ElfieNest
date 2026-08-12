# Elfie Brain 执行规则

本目录受上级 `elfie/AGENTS.md`、Elfie 内部架构契约与 Brain 内部架构契约约束。Brain 拥有一只 Elfie 的
事件工作区、自我定位、自我认知、情绪、能量、动机、记忆、思考中枢、跨回合活动、
心智整理和 Skills。

- 十系统是概念所有者，不等于十个进程、数据库或必须预建的目录；只有出现真实状态、
  契约或行为时才建立对应包，禁止建立空架构目录。
- 通信、具身和内部触发分别进入有界 Lane；Brain 必须确定性形成单一 `SourceDomain`
  的 Turn，并在宿主边界校验 `ResponseScope`。模型输出不能扩大响应域。
- Model、Skill、Tool 调用发生在同一 Turn 的思考循环内部，不是外部执行线路；最终外部
  决定只允许通信指令、神经系统指令、跨回合活动请求或 No-op。
- Motivation 只能产生注意、Goal 或内部触发候选，不能直接创建 Activity 或执行动作；
  Cognitive Consolidation 默认没有外部副作用权限。
- 权威状态变更采用候选—校验—提交；模型文本、Tool Observation、后台整理和 Worker
  都不得直接改写 Profile、Selfhood、Memory、Activity 或执行成功事实。
- 一个 Turn 只能结算一个 `TurnDecision`，且至多提交 Communication 或 NervousSystem
  一个外部域；长短 Run 即使并行计算，也必须经过唯一串行提交边界。
- Persistent Activity 必须先无副作用 Preflight、再在 Turn 结算后 Commit；到期只产生
  Internal Event。Activity 可靠存续前不得开放 Motivation 主动创建工作。

- Brain 只依赖自身定义的强类型 `FoodPort`、`ModelPort`、`ToolPort`、记忆 Port 及
  Elfie 内部语义 Port；不得导入 Provider SDK、工具实现、App、Nest 或具体
  Infrastructure。
- Skills 的目标位置是 `elfie/brain/skills/`，只负责目录、策略和语义工具授权；不得
  包装 Runtime、执行工具或接收任意工作区路径。
- Brain 授权是工具调用的必要但非充分条件；`ToolPort` Adapter 仍必须执行全局可用性与
  逐次技术安全校验，可以拒绝但不能扩大 Brain 已授权能力。语义请求只传资源标识，不传
  任意文件系统 Root。
- 随源码发布的不可变 Skill 与内存策略不建立持久化 Port；可变 Skill 安装或持久状态
  在单独契约获批前保持禁用，Brain 不得先写文件制造事实源。
- `ElfieCognitiveRuntime` 或后继协调器只能是聚合内部实现，不得成为 App Runtime、
  composition root 或公开产品入口。
- 新边界使用命名不可变模型，禁止新增 `Any`、裸 `dict`、SDK 对象或协议帧；已退役的
  `CorticalRuntimePort` 不得恢复。
- Brain 单元测试使用 Fake Port；模型、工具、数据库、网络和 Godot 不得成为认知算法
  测试的前置条件。
