# Elfie 内部架构一致性

> [Elfie 内部架构契约](../contracts/elfie)的临时迁移台账。它记录当前实现缺口，不降低
> 目标。所有条目关闭后删除本页。

## 当前缺口

| ID | 严重度 | 状态 | 当前偏差 | 关闭条件 |
| --- | --- | --- | --- | --- |
| ELF-001 | P1 | open | 根 Facade 已较小，但生产调用方仍可直接访问深层协调器和可变子模块，完整类型化入站清单尚未冻结。 | `Elfie`/`ElfieFactory` 成为唯一生产聚合入口，只暴露批准的类型化能力，并删除和拦截深层调用方导入。 |
| ELF-002 | P0 | open | Skills 位于根 `elfie/skills/`，面向 Runtime 的 Skill Adapter 把授权与历史执行 Runtime 耦合。 | Skills 移到 `elfie/brain/skills/`，只引用语义工具 key/能力，授权由注入 `ToolPort` 执行的请求；随源码发布的声明/内存策略不使用 Store，Skill 修改和持久状态保持禁用；删除旧包和 Runtime Adapter。 |
| ELF-003 | P0 | open | Brain 已拥有强类型 `FoodPort`，但模型访问和工具执行仍依赖宽泛历史 `CorticalRuntimePort`；最终 `ModelPort` 与 `ToolPort` 尚未建立。 | Brain 分别拥有强类型 `FoodPort`、`ModelPort`、`ToolPort`；Food 保留命名角色/单 Fallback/Emergency 行为，限定作用域的 Tool Adapter 保留技术安全否决权；Bootstrap 注入 Infrastructure View；迁移全部调用方并删除宽 Runtime 桥。 |
| ELF-004 | P0 | open | Brain Memory 包含 SQLite 连接、Schema 和具体图存储，部分记忆边界仍暴露宽松字典。 | `elfie/brain/memory/` 只保留语义算法与 `MemoryStorePort`；SQLite/Schema/Record 映射移到 Infrastructure；模型收紧且领域测试使用 Fake。 |
| ELF-005 | P0 | open | Profile Repository/Resolver 知道 YAML 和路径，Factory 接收具体配置路径。 | Profile 拥有 `ProfileStorePort`；用户可变持久化与路径解析移到 Infrastructure/Bootstrap；随源码发布的不可变默认资源保留；Factory 接收类型化依赖。 |
| ELF-006 | P0 | open | 已有 `BodyPort`、类型化事件、回执、Registry 和 Binding，但 Godot Transport 及 External/Native 实现仍在 `elfie/body/`；Headless 尚未区分为纯参考/测试支持还是产品托管。 | Elfie 保留身体身份、能力、命令、事件、回执和绑定语义；Godot/设备/产品托管实现移到 Infrastructure；只有确定性、无 I/O 的参考身体或测试 Fake 可以保留；BodyPort 不承载 Nest World Fact；多身体身份/路由有聚焦测试。 |
| ELF-007 | P0 | open | 通信领域已有标准 Envelope 和渠道 Protocol，但微信/Telegram 实现及部分投递执行仍在 `elfie/communication/`，最终经过认证的 App 入站路径尚未冻结。 | 平台 SDK、凭据、Webhook 和传输/重试实现移到 Infrastructure；App 在 Facade 入站前解析 Principal、成员、目标与授权并拥有产品会话事实；Elfie 保留语义 Hub/Router/Policy、有界临时 Inbox/Outbox 与注入渠道 Port，并有多渠道、身份和去重测试。 |
| ELF-008 | P1 | open | `ElfieFactory` 仍知道 `config_dir`、`memory_db_path`、宽松 Godot API 和分阶段认知配置。 | Factory 只作为领域 Builder，从不可变强类型装配记录创建完整、未启动的聚合；Bootstrap 构造限定作用域的具体 Adapter View，Lifecycle Orchestration 拥有系统 start/stop/restart，生产环境不存在部分配置的 Elfie。 |
| ELF-009 | P1 | open | 若干公开边界仍使用 `Any`、原始字典或实现形状模型，装配/Fake 证据尚不能证明全部最终 Port。 | 公开 Facade 与 Port 使用命名不可变领域模型；Core 测试使用 Fake；Adapter 测试覆盖转换；Bootstrap 接线和每类已完成身体/渠道的一条真实链路证明最终边界。 |

## 机器覆盖

系统层扫描器已经禁止反向根导入，并精确收紧 Elfie 的直接技术导入。聚焦 Elfie 认知
测试保护当前公开身体/通信契约、严格 Pydantic 边界、Facade 规模与依赖方向；对于当前
已经合规的实现，它也保护本次明确的 Port 所有权和公开聚合面。

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
