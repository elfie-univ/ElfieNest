# Elfie Brain 执行规则

本目录受上级 `elfie/AGENTS.md` 与 Elfie 内部架构契约约束。Brain 拥有一只 Elfie 的
感知工作区、上下文、评估、认知、决策、情绪、能量、记忆语义、输出路由和 Skills。

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
- 新边界使用命名不可变模型，禁止新增 `Any`、裸 `dict`、SDK 对象或协议帧。历史
  `CorticalRuntimePort` 是 `ELF-003` 迁移路径，不得扩展其职责。
- Brain 单元测试使用 Fake Port；模型、工具、数据库、网络和 Godot 不得成为认知算法
  测试的前置条件。
