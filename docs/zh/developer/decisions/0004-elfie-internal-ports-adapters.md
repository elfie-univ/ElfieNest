# ADR-0004：Elfie 内部 Ports and Adapters

- **状态：** 已接受
- **日期：** 2026-08-11
- **范围：** 一只 Elfie 的内部架构及对齐后的模型/工具边界

## 背景

系统契约已经把 `elfie/` 放在领域核心，并要求 Infrastructure 实现其出站 Port，但它
没有定义一只 Elfie 内部的所有权边界。当前包已有较成熟的强类型身体与通信契约，同时
仍把技术持久化、Godot/设备身体、平台渠道、根级 Skills 和宽泛 Runtime 边界放在领域
行为旁边。如果没有更细的契约，渐进迁移可能保留错误所有权，或产生重复抽象。

身体与通信也确实存在多实现需求。一只 Elfie 可以寄居于 Godot Actor、一具或多具实体
玩具及 Headless 测试身体；也可以同时通过网页聊天、ElfieNest App 和第三方平台通信。
这些变化需要稳定语义 Port，但不能让传输技术进入 Elfie 认知。

## 决策

采用 [Elfie 内部架构契约](../contracts/elfie) 作为 `elfie/` 的规范性目标：

- 一只 Elfie 是一个聚合和内部生命周期边界，不是系统 Runtime authority，只通过稳定的
  `Elfie`、`ElfieFactory` Facade 进入；
- Profile、Brain、NervousSystem、Body 和 Communication 分别拥有清晰语义，私有聚合
  协调把它们连接起来，但不成为产品 Runtime；
- Skills 移入 Brain，负责授权语义工具请求，不包装 Runtime，也不执行工具；
- 出站 Port 定义在使用方旁：Brain 拥有 Food/模型/工具与记忆 Port，Profile 拥有存储
  Port，Body 拥有供 NervousSystem/聚合路由使用的 `BodyPort`，Communication 拥有渠道
  Port；
- 根部可以有面向 Bootstrap 的精简重导出，但不得重复定义 Port 模型或成为 Service
  Locator；
- 每具身体实现同一个 `BodyPort`；稳定身份、能力、Registry 与显式 Binding 支持多身体
  及未来并发身体；
- 每个平台渠道实现同一个通信渠道 Port；标准 Envelope 和类型化回执支持多渠道并存；
- 外部通信只有在 App 解析账户、会话成员、目标和授权后才能进入 Elfie；Infrastructure
  不得选择或授权目标 Elfie；
- Elfie Facade 是身体与通信事件的入站边界；没有真实隔离需求时不添加对称入站
  Protocol；
- 技术存储、Provider、工具、Godot、设备和平台渠道 Adapter 下移到根
  Infrastructure，由 App Bootstrap 构造；
- Bootstrap 拥有构造和容器生命周期，只有 Lifecycle Orchestration 决定系统 Runtime
  的 start/stop/restart，Elfie 生命周期只覆盖内部聚合；
- Brain Skill 授权不能绕过 Tool Adapter 的全局与逐次安全交集；工作区作用域注入限定
  Adapter View，而不是以文件系统路径跨越 `ToolPort`；
- 随源码发布的不可变 Skill 与内存策略不需要持久化 Port；可变 Skill 安装或持久状态在
  单独契约获批前保持禁用；
- 每次只迁移一条完整边界，在同一切片删除旧路径，并关闭明确的一致性缺口；
- 中英文契约索引只是导航而非版本化契约；治理门仍要求两份索引同时更新。

此决策是对既有系统架构的内部细化，不改变根模块、authority 所有者、依赖方向、生产
组合或系统级 Port 语义，因此系统契约 1.3 保持不变。未来若改变任一宏观属性，仍必须
单独建立系统 ADR 并升级系统契约版本。

模型、Food 与工具行为契约同步升级到 1.5 以对齐这些边界。已接受的 Food 行为仍是命名
角色、一个可选 Fallback 和 Emergency，并非任意有序 Fallback 列表。工具可用性和工作区
限制也保持原行为，只澄清所有权和边界表达。

## 后果

Elfie 领域测试可以使用类型化 Fake，技术集成则接受聚焦的 Adapter 与 Bootstrap 测试。
身体和渠道可以增量扩展而不修改认知，公开聚合面会收紧，Factory 最终只接收强类型
依赖。

当前包会暂时不完全合规。Skills、记忆/档案持久化、技术身体、平台渠道及宽 Runtime
桥接需要各自的迁移切片。本 ADR 只授权目标与治理门，不授权一次性搬迁源码或增加兼容
层。

明确拒绝扁平互相导入的 Elfie 包、万能 `ElfiePort`、每个 helper 一个 Protocol、把技术
Adapter 留在领域子模块、按产品调用方复制身体/渠道类、通用 Runtime 代理、由 App
Orchestration 代理普通认知，以及一次性全量迁移。
