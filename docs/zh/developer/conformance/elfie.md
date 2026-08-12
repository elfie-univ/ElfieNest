# Elfie 内部架构一致性

> [Elfie 内部架构契约](../contracts/elfie)的临时迁移台账。它记录当前实现缺口，不降低
> 目标。ELF-001 至 ELF-009 记录已经完成的 Ports/Adapters 迁移；ELF-010 之后记录
> 2.0 契约采用的生命系统目标。

## 当前缺口

| ID | 严重度 | 状态 | 当前偏差 | 关闭条件 |
| --- | --- | --- | --- | --- |
| ELF-001 | P1 | closed | App 编排与接口生产调用方只使用受控的 `elfie.public`/`nest.public` 表面，深层领域导入已由机器门禁保护。 | `Elfie`/`ElfieFactory` 成为唯一生产聚合入口，只暴露批准的类型化能力，并删除和拦截深层调用方导入。 |
| ELF-002 | P0 | closed | Skills 已由 Brain 在 `elfie/brain/reasoning/skills/` 拥有；旧根包及其 Runtime 代理已删除。 | Brain 声明、内存策略和语义工具 key 授权有聚焦测试；已废弃的 Skill 包不再包含 Runtime Adapter、Store、路径或工具执行实现。 |
| ELF-003 | P0 | closed | Brain 已分别暴露强类型 `FoodPort`、`ModelPort`、`ToolPort`；Runtime 模型执行通过 Bootstrap 注入限定作用域的 Tool Adapter。 | `ToolRequest`/`ToolResult` 是封闭不可变契约，Adapter 保留全局与每只精灵的安全否决，结构化与普通路径都使用注入 Port，历史宽 Runtime 桥已移除。 |
| ELF-004 | P0 | closed | `elfie/brain/memory/` 已移除 SQLite/Schema/Record 映射；语义算法依赖 `MemoryStorePort` 与已校验的 `MemoryMetadata`。 | Brain Memory 测试使用内存 Fake，持久化测试位于 Infrastructure，系统技术 import 精确基线清零，最终知识库重新打开行为仍有覆盖。 |
| ELF-005 | P0 | closed | Profile 加载和路径解析由 Infrastructure/Bootstrap 拥有；`assemble_profile` 与 `ElfieFactory` 只接收类型化档案/依赖。 | `ProfileStorePort` 仍是领域边界，打包默认值来自资源，Elfie 初始化和 Factory API 不再接收存储路径或具体 Profile Repository。 |
| ELF-006 | P0 | closed | 身体语义、Registry 和 Binding 留在 Elfie，Godot/设备/产品托管实现位于领域外；剩余 Headless/native 身体是确定性、无 I/O 的参考实现。 | 多身体身份/绑定与类型化事件/回执测试通过；Body 实现不导入传输、凭据、进程所有权或 Nest 世界事实。 |
| ELF-007 | P0 | closed | `elfie/communication/` 只拥有标准 Envelope、策略、Hub/Router、有界 Inbox/Outbox 与注入的渠道 Port；微信/Telegram 和消息投递传输位于 `infrastructure/communication/`，版本化且认证的 App 会话/WebSocket 路由在进入投递 Facade 前解析成员与目标。 | 保持通信 Port/Adapter 方向、认证入站、身份/去重和投递顺序测试通过。 |
| ELF-008 | P1 | closed | `ElfieFactory` 已成为围绕不可变 `ElfieAssembly` 的类型化领域 Builder；存储路径、Godot API 和分阶段 Runtime 配置在调用前解析。 | Factory create/restore 测试通过，返回的聚合完整但未启动，生产组合根仍由 Bootstrap 拥有。 |
| ELF-009 | P1 | closed | Profile、Body、Communication、Nest Session、Runtime observation 及 Infrastructure Port 模型的公开边界均使用命名不可变模型或受限 JSON 值。永久 Port 棘轮拒绝 `Any`、`object` 和具体对等 Adapter 签名；身体/通信/Bootstrap 证据已有机器门禁。 | 保持严格 Port 棘轮和证据通过；内部算法局部映射不属于公开边界契约。 |
| ELF-010 | P0 | open | `ElfieProfile` 仍保存 `personality`、`capabilities`、`system_limits`；`elfie/profile/defaults/` 仍把自我认知、身体能力、能量/运行默认值与不可变外貌事实混在一起。 | 先建立接收它们的 Brain/Body/NervousSystem 所有者，再在一个获批切片中迁移全部生产调用方和持久字段，最后删除三个宽泛 Profile 映射及混合默认资源，不保留 fallback read 或双 authority。 |
| ELF-011 | P0 | closed | 私有认知协调与上下文组装已经归 Brain；Communication、Embodied、Internal 输入形成类型化单域 Turn，宿主强制响应范围，旧根认知文件已删除。 | Brain 生命周期、Lane、Scope 和决策边界聚焦测试通过；Elfie Lab 展示通信闭环的来源域、Scope、决定与投递回执。后续 Brain 能力扩展必须保持这一边界门禁。 |
| ELF-012 | P0 | closed | Body Registry/Binding 现在为当前身体分配 authority generation；NervousSystem 只接收当前身体代际，输出执行器拒绝切换后的旧回执，中断也回到原身体；失败切换保留旧身体。 | 阶段三 Headless/真实 Godot 验收通过；身体切换、旧事件拒绝、旧回执拒绝、连接失败回滚以及唯一当前身体均有聚焦测试和真实 `world_ready`/`intent_terminal` 证据。 |
| ELF-013 | P1 | open | `elfie/initialization.py` 只装配 Profile 与 Anatomy，尚无 `genesis/` 所有者承载经过校验的临时创建 Bundle、Brain 种子和有界人生补全。 | Genesis 生成并校验类型化创建产物，每项只提交一次给最终所有者，不保留重复生命状态，完成后退出普通运行期。 |
| ELF-014 | P0 | closed | Brain 现在拥有 Persistent Activity 语义 Port 和输出边界；Lab 为每只 Elfie 注入独立 SQLite Adapter。已校验 Draft 幂等提交，等待任务通过类型化 Internal 事件唤醒，通信/具身子回执结算 Activity 进度，重启后不重复投递。 | Activity、持久化和 Lab 聚焦测试覆盖跨回合状态、唤醒、Scope 校验、回执终态、重启恢复和无重复投递。 |
| ELF-015 | P1 | closed | 首个有界恢复 Motivation 驱力和首个有界 Cognitive Consolidation 切片现在都有 Brain 所有者与 Lab 证据。整理工作仅处理睡眠窗口中的 Episodic 记忆，不能产生外部副作用；更多主动驱力与成长仍是独立范围。 | Motivation 以冷却/满足状态控制候选；Cognitive Consolidation 以 Checkpoint 候选和固定经历预算进入内部回合，并且只有内部回执完成后才提交 Memory。Brain/Lab 聚焦测试与 Web build 通过；夜间路径不创建消息、身体动作或 Activity。 |
| ELF-016 | P0 | closed | Brain 已拥有单个 Turn 内有界的 `ReasoningRun`：模型、认知 Tool、真实 Observation、验证和完成/失败收束均在 Brain 内部完成，外部行动仍只能由结算后的决定进入既有边界。 | 26 项聚焦 Brain/Lab 测试通过；真实 Elfie Lab 展示 Tool→Observation，虚假外部执行声明不产生外部回执，模型不可用进入明确 `failed/no_op`，紧急事件形成独立新 Turn。纯文本 Provider 的 `owner_message_fallback` 被记录为降级而非成功事实。 |
| ELF-017 | P0 | closed | Orientation 与 Selfhood 已成为独立 authority；Emotion、Energy、Memory、Orientation、Selfhood、Motivation 与 Cognitive Consolidation 进入统一连续状态 Checkpoint。自我定位从当前 Body generation、会话、地点与 Activity 生成候选，并在 Turn Settlement 中提交。 | 聚焦状态、结算和跨模块恢复测试覆盖明确所有者、来源/版本规则、跨 Turn 恢复、陈旧 Checkpoint 拒绝，以及单轮消息不能改写人格/规范。 |

## 机器覆盖

系统层扫描器禁止反向根导入并精确棘轮 Elfie 直接技术 import；Elfie 技术 import 精确
基线现已清零。聚焦认知测试保护身体/通信公开契约、严格 Pydantic 边界、Facade 大小、
依赖方向和 Brain 所有的 ToolPort 面；Memory Fake 测试、Infrastructure 持久化测试以及
模型/工具端到端路径为已关闭切片提供证据。

Ports/Adapters 条目已有迁移后的生产调用链、聚焦行为证据和永久机器棘轮，均已关闭。
2.0 契约复用这些边界和既有 Baseline，不创建第二套历史债务 Baseline。开放的生命系统
条目是目标差距，不授权降低契约，也不能把只有设计的能力冒充成已实现。

## 已完成的 Ports/Adapters 顺序

1. 盘点并冻结 `Elfie`/`ElfieFactory` 公开面；
2. 把 Skills 移入 Brain，分离授权与执行；
3. 以 Food、模型、工具 Port 替换宽 Runtime 桥；
4. 提取 Memory 与 Profile 持久化 Adapter；
5. 在保留稳定 Body Port 的前提下提取身体技术 Adapter；
6. 在保留标准 Envelope 与渠道路由的前提下提取通信平台 Adapter；
7. 完成 Factory/Bootstrap 装配并删除生产深层导入；
8. 关闭严格模型、Fake、Adapter 与端到端证据缺口。

每一步都是独立获批的垂直切片：定义或冻结使用方 Port，实现并注入一个 Adapter，迁移
全部调用方，删除旧路径，再只关闭对应条目。

## 生命系统实现顺序

1. Brain Kernel 与通信生命闭环关闭 ELF-011 的单域 Turn 和根认知所有权部分；
2. 思考中枢通过有界 Model/Skill/Tool Observation 关闭 ELF-016，不增加新的外部行动线路；
3. 虚拟具身闭环为第一具生产身体关闭 ELF-012 的唯一当前身体 authority；
4. 连续生命状态关闭 ELF-017，建立 Selfhood/Energy/Orientation 所有者，并在无 Profile 双字段的前提下关闭 ELF-010；
5. 跨回合活动在 Motivation 可以创建主动工作之前关闭 ELF-014；
6. 有界 Motivation 与 Cognitive Consolidation 关闭 ELF-015；
7. 只有最终 Profile 与 Brain 种子所有者存在后，Genesis 才关闭 ELF-013。

详细执行计划是独立实施产物。它可以把这些条目拆成更小验收切片，但不能把 Motivation
提前到 Activity 之前，不能移除单一身体 authority、增加兼容存储，或重新定义契约固定
的所有者。
