# Elfie 内部架构一致性

> [Elfie 内部架构契约](../contracts/elfie)的临时迁移台账。它记录当前实现缺口，不降低
> 目标。所有条目关闭后删除本页。

## 当前缺口

| ID | 严重度 | 状态 | 当前偏差 | 关闭条件 |
| --- | --- | --- | --- | --- |
| ELF-001 | P1 | open | 根 Facade 已较小，但生产调用方仍可直接访问深层协调器和可变子模块，完整类型化入站清单尚未冻结。 | `Elfie`/`ElfieFactory` 成为唯一生产聚合入口，只暴露批准的类型化能力，并删除和拦截深层调用方导入。 |
| ELF-002 | P0 | closed | Skills 已由 Brain 在 `elfie/brain/skills/` 拥有；旧根包及其 Runtime 代理已删除。 | Brain 声明、内存策略和语义工具 key 授权有聚焦测试；已废弃的 Skill 包不再包含 Runtime Adapter、Store、路径或工具执行实现。 |
| ELF-003 | P0 | closed | Brain 已分别暴露强类型 `FoodPort`、`ModelPort`、`ToolPort`；Runtime 模型执行通过 Bootstrap 注入限定作用域的 Tool Adapter。 | `ToolRequest`/`ToolResult` 是封闭不可变契约，Adapter 保留全局与每只精灵的安全否决，结构化与普通路径都使用注入 Port，历史宽 Runtime 桥已移除。 |
| ELF-004 | P0 | closed | `elfie/brain/memory/` 已移除 SQLite/Schema/Record 映射；语义算法依赖 `MemoryStorePort` 与已校验的 `MemoryMetadata`。 | Brain Memory 测试使用内存 Fake，持久化测试位于 Infrastructure，系统技术 import 精确基线清零，最终知识库重新打开行为仍有覆盖。 |
| ELF-005 | P0 | closed | Profile 加载和路径解析由 Infrastructure/Bootstrap 拥有；`assemble_profile` 与 `ElfieFactory` 只接收类型化档案/依赖。 | `ProfileStorePort` 仍是领域边界，打包默认值来自资源，Elfie 初始化和 Factory API 不再接收存储路径或具体 Profile Repository。 |
| ELF-006 | P0 | closed | 身体语义、Registry 和 Binding 留在 Elfie，Godot/设备/产品托管实现位于领域外；剩余 Headless/native 身体是确定性、无 I/O 的参考实现。 | 多身体身份/绑定与类型化事件/回执测试通过；Body 实现不导入传输、凭据、进程所有权或 Nest 世界事实。 |
| ELF-007 | P0 | open | 通信领域已有标准 Envelope 和渠道 Protocol，但微信/Telegram 实现及部分投递执行仍在 `elfie/communication/`，最终经过认证的 App 入站路径尚未冻结。 | 平台 SDK、凭据、Webhook 和传输/重试实现移到 Infrastructure；App 在 Facade 入站前解析 Principal、成员、目标与授权并拥有产品会话事实；Elfie 保留语义 Hub/Router/Policy、有界临时 Inbox/Outbox 与注入渠道 Port，并有多渠道、身份和去重测试。 |
| ELF-008 | P1 | closed | `ElfieFactory` 已成为围绕不可变 `ElfieAssembly` 的类型化领域 Builder；存储路径、Godot API 和分阶段 Runtime 配置在调用前解析。 | Factory create/restore 测试通过，返回的聚合完整但未启动，生产组合根仍由 Bootstrap 拥有。 |
| ELF-009 | P1 | in progress | 已完成的 Port 切片使用命名不可变模型并有 Fake/Adapter 证据，但旧 Profile/Body capability projection 与少数公开 snapshot 仍含无约束映射。 | 完成剩余强类型边界清单，补齐身体/渠道/Bootstrap 证据；不得新增 `Any` 或裸边界字典。 |

## 机器覆盖

系统层扫描器禁止反向根导入并精确棘轮 Elfie 直接技术 import；Elfie 技术 import 精确
基线现已清零。聚焦认知测试保护身体/通信公开契约、严格 Pydantic 边界、Facade 大小、
依赖方向和 Brain 所有的 ToolPort 面；Memory Fake 测试、Infrastructure 持久化测试以及
模型/工具端到端路径为已关闭切片提供证据。

其余条目必须有已经迁移的生产调用链和聚焦行为证据；静态测试通过不能单独关闭条目。
本契约复用系统扫描器和既有 Baseline，不创建第二套历史债务 Baseline。

## 迁移顺序

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
