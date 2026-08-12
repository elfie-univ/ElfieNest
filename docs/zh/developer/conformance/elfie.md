# Elfie 内部架构一致性

> [Elfie 内部架构契约](../contracts/elfie)的临时迁移台账。它记录当前实现缺口，不降低
> 目标。ELF-001 至 ELF-009 记录已经完成的 Ports/Adapters 迁移；ELF-010 之后记录
> 2.0 契约采用的生命系统目标。

## 当前缺口

| ID | 严重度 | 状态 | 当前偏差 | 关闭条件 |
| --- | --- | --- | --- | --- |
| ELF-001 | P1 | closed | App 编排与接口生产调用方只使用受控的 `elfie.public`/`nest.public` 表面，深层领域导入已由机器门禁保护。 | `Elfie`/`ElfieFactory` 成为唯一生产聚合入口，只暴露批准的类型化能力，并删除和拦截深层调用方导入。 |
| ELF-002 | P0 | closed | Skills 已由 Brain 在 `elfie/brain/skills/` 拥有；旧根包及其 Runtime 代理已删除。 | Brain 声明、内存策略和语义工具 key 授权有聚焦测试；已废弃的 Skill 包不再包含 Runtime Adapter、Store、路径或工具执行实现。 |
| ELF-003 | P0 | closed | Brain 已分别暴露强类型 `FoodPort`、`ModelPort`、`ToolPort`；Runtime 模型执行通过 Bootstrap 注入限定作用域的 Tool Adapter。 | `ToolRequest`/`ToolResult` 是封闭不可变契约，Adapter 保留全局与每只精灵的安全否决，结构化与普通路径都使用注入 Port，历史宽 Runtime 桥已移除。 |
| ELF-004 | P0 | closed | `elfie/brain/memory/` 已移除 SQLite/Schema/Record 映射；语义算法依赖 `MemoryStorePort` 与已校验的 `MemoryMetadata`。 | Brain Memory 测试使用内存 Fake，持久化测试位于 Infrastructure，系统技术 import 精确基线清零，最终知识库重新打开行为仍有覆盖。 |
| ELF-005 | P0 | closed | Profile 加载和路径解析由 Infrastructure/Bootstrap 拥有；`assemble_profile` 与 `ElfieFactory` 只接收类型化档案/依赖。 | `ProfileStorePort` 仍是领域边界，打包默认值来自资源，Elfie 初始化和 Factory API 不再接收存储路径或具体 Profile Repository。 |
| ELF-006 | P0 | closed | 身体语义、Registry 和 Binding 留在 Elfie，Godot/设备/产品托管实现位于领域外；剩余 Headless/native 身体是确定性、无 I/O 的参考实现。 | 多身体身份/绑定与类型化事件/回执测试通过；Body 实现不导入传输、凭据、进程所有权或 Nest 世界事实。 |
| ELF-007 | P0 | closed | `elfie/communication/` 只拥有标准 Envelope、策略、Hub/Router、有界 Inbox/Outbox 与注入的渠道 Port；微信/Telegram 和消息投递传输位于 `infrastructure/communication/`，版本化且认证的 App 会话/WebSocket 路由在进入投递 Facade 前解析成员与目标。 | 保持通信 Port/Adapter 方向、认证入站、身份/去重和投递顺序测试通过。 |
| ELF-008 | P1 | closed | `ElfieFactory` 已成为围绕不可变 `ElfieAssembly` 的类型化领域 Builder；存储路径、Godot API 和分阶段 Runtime 配置在调用前解析。 | Factory create/restore 测试通过，返回的聚合完整但未启动，生产组合根仍由 Bootstrap 拥有。 |
| ELF-009 | P1 | closed | Profile、Body、Communication、Nest Session、Runtime observation 及 Infrastructure Port 模型的公开边界均使用命名不可变模型或受限 JSON 值。永久 Port 棘轮拒绝 `Any`、`object` 和具体对等 Adapter 签名；身体/通信/Bootstrap 证据已有机器门禁。 | 保持严格 Port 棘轮和证据通过；内部算法局部映射不属于公开边界契约。 |
| ELF-010 | P0 | open | `ElfieProfile` 仍保存 `personality`、`capabilities`、`system_limits`；`elfie/profile/defaults/` 仍把自我认知、身体能力、能量/运行默认值与不可变外貌事实混在一起。 | 先建立接收它们的 Brain/Body/NervousSystem 所有者，再在一个获批切片中迁移全部生产调用方和持久字段，最后删除三个宽泛 Profile 映射及混合默认资源，不保留 fallback read 或双 authority。 |
| ELF-011 | P0 | closed | 私有认知协调与上下文组装已经归 Brain；Communication、Embodied、Internal 输入形成类型化单域 Turn，宿主强制响应范围，旧根认知文件已删除。 | Brain 生命周期、Lane、Scope 和决策边界聚焦测试通过；Elfie Lab 展示通信闭环的来源域、Scope、决定与投递回执。后续 Brain 能力扩展必须保持这一边界门禁。 |
| ELF-012 | P0 | open | Body Registry/Binding 已选择当前命令身体，但尚未实现完整的虚拟/实体互斥切换、authority generation、旧回执拒绝、回滚和重启恢复契约。 | 一个明确切换状态机始终保持唯一选中传感/动作 authority，拒绝旧 generation，并在失败或重启后确定性恢复或回滚。 |
| ELF-013 | P1 | open | `elfie/initialization.py` 只装配 Profile 与 Anatomy，尚无 `genesis/` 所有者承载经过校验的临时创建 Bundle、Brain 种子和有界人生补全。 | Genesis 生成并校验类型化创建产物，每项只提交一次给最终所有者，不保留重复生命状态，完成后退出普通运行期。 |
| ELF-014 | P0 | open | 当前认知已有 Workspace、Model Worker、DecisionPlan 和内部占位操作，但缺少已接受的 Persistent Activity 所有者、确定性 Preflight/Commit 分离、持久内部唤醒和回执对账。 | 已校验 Activity 跨 Turn/重启存续，只通过类型化内部事件唤醒，保持通信/具身 Step 分离，并以真实回执达到无重复副作用的终态。 |
| ELF-015 | P1 | open | Motivation 和 Cognitive Consolidation 仍只有设计，主动自治与离线成长尚无有界运行所有者。 | 只在 Activity 稳定后实现：固定驱力带冷却地产生有界候选；无副作用整理在独立预算内只产生已校验状态候选或后续内部触发。 |
| ELF-016 | P0 | open | 当前 Cortex 路径能够调用模型并解码 `DecisionPlan`，但 Brain 尚未拥有已接受的有界多步 Model/Skill/Tool Observation 循环、验证、抑制和完成判断。 | 一个 Reasoning Run 可以执行有界认知步骤和真实 Tool Observation，但只有结算后的 `TurnDecision` 能进入外部决策边界；超时、预算耗尽和虚假执行声明必须以无伪造成功的方式终止。 |
| ELF-017 | P0 | open | 情绪、能量和记忆已有实现，但 Orientation 与 Selfhood 尚未成为独立 authority，完整连续生命状态也未在跨 Turn、身体切换和进程重启后统一恢复。 | 类型化 Orientation/Selfhood/Emotion/Energy/Memory Snapshot 具有明确所有者、来源/版本规则和最小持久恢复；Profile 保持不可变，短期情绪不能直接改写人格。 |

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
