# Elfie Memory 一致性

> 状态：source-first Memory、类型化生产调用方、策略驱动生命周期和代表性耐久性证据均已完成。退役旧栈在产品/运行时根目录中已无引用；兼容组件仅保留给语义 Fake 和 Lab 显式回退。生产数据切换和 OPT-004 仍单独治理。<br>
> 基线：2026-08-30<br>
> 目标：[Elfie Memory 设计](../designs/elfie-memory-architecture)

这是临时迁移台账，记录当前实现相对于 Memory 设计的精确缺口以及关闭所需的证据。它不重定义 Memory 模型，不授权修改数据库，也不是开发过程日志。

## 实施台账

| ID | 严重度 | 状态 | 当前差距 | 目标与关闭门槛 | 证据 / 参考 | 残余 |
| --- | --- | --- | --- | --- | --- | --- |
| MEM-001 | P0 | closed | 目标 Adapter 已用审查后的 Episode、节点、Assertion 和 Evidence 表替代旧实体/子类型及嵌入边布局。 | 目标表、约束、所有权和可重建词法投影已实现，不存在第二套边事实源。 | target=设计第 9.1–9.2 节；inventory=`infrastructure/persistence/memory/{schema.py,sqlite_memory_store.py,node_store.py,sqlite_episode_store.py,sqlite_graph_store.py,sqlite_retrieval_store.py}`；references=持久化扫描；verification=目标 schema/往返/重开测试、299 项 Memory/Brain/Genesis/领养受影响测试、21 项架构测试、Ruff、pycompile 和 `git diff --check`；residuals=已有线上旧库仍需下方的显式导入/切换。 | 开发目标无残余。 |
| MEM-002 | P0 | closed | 闭合 Episode 具备完整内容、来源 ID、完整来源哈希、幂等和重启安全写入；已完成互动候选和 Genesis 种子都走先保存来源的路径。未知时间、发生时间精度、归因、隐私和投影来源均显式保留。 | 一个经过校验的 Episode 是详细历史来源；Memory 不负责合并原始回合。 | target=设计第 3、9.1/9.4 节；inventory=`sqlite_episode_store.py`、`memory_system.py`、`genesis/initializer.py`；references=Episode 和 E1 垂直切片测试；verification=重复提交、内容哈希、未知时间、低强度候选、Genesis 来源链和重开测试；residuals=上游事件边界仍负责闭合事件；旧 `record_episode` 仅作兼容接口。 | 目标路径无残余。 |
| MEM-003 | P0 | closed | 节点、别名、描述、提及、带类型字面量的限定 Assertion、Evidence 和多对多关联已持久化；身份合并会重定向历史并保留冲突。 | 独立重要性、可信度、极性、视角、时间、类型化值和反驳关系不会被裸三元组覆盖。 | target=设计第 4、9.1–9.3 节；inventory=`sqlite_graph_store.py`、`schema.py`、`predicates.py`；references=source-first 图测试；verification=跨 Episode 别名/身份解析、合并重定向、带来源断言、谓词拒绝、冲突/证据和投影诊断测试；residuals=旧数据库已经覆盖的历史版本不能自动恢复。 | 旧数据可能存在不可恢复冲突。 |
| MEM-004 | P0 | closed | 有界 Worker 领取 Episode，校验有来源模型提案或使用保守确定性抽取，再以可重试的有来源投影在单事务中提交；版本化谓词注册表、来源哈希/修订校验和有界拒绝诊断已强制执行。 | 规范身份、证据绑定、相容合并和冲突保留是确定性的；来源 Episode 在失败时不丢失。 | target=设计第 5、9.3–9.4 节；inventory=`elfie/brain/memory/consolidation.py`、`predicates.py`、`sqlite_graph_store.py`；references=source-first Worker 测试；verification=模型来源校验、全局语义 ID、租约恢复、谓词/版本拒绝、投影修订和来源保留测试；residuals=Provider 与调度仍是注入/运维选择。 | 写事务不会等待无界模型调用。 |
| MEM-005 | P0 | closed | `RecallRequest` 已执行确定性的 Basic/Text 候选检索，再做有界 Local Graph 遍历、来源获取、关系/时间/facet/隐私过滤和限制控制。active、superseded 及冲突声明保留状态和证据；常见词候选预过滤和图谱两端查询均有界且可走索引。 | 文本覆盖罕见/未解析表述；图遍历覆盖明确关系；来源和冲突保持可见。 | target=设计第 6、9.4 节；inventory=`sqlite_retrieval_store.py`、`node_store.py`、`sqlite_graph_store.py`、`schema.py`；references=source-first 检索测试和 `build/evaluations/stage1-chat/opt003-current/report.json`；verification=罕见词/别名、人物关系网、知识对象、种子、时间窗口、正向 AND/OR facet、未知时间、隐私、跳数/限制和 10k/50k/200k 代表性延迟检查；residuals=Global/社区和向量检索仍是后续投影。 | 词法投影仍可重建，不构成第二事实源。 |
| MEM-006 | P0 | closed | `RecallBundle` 及确定性渲染器已实现；Reasoning Memory reader 消费独立的带真实来源 ID 的类型化项目。 | 上层通过语义契约取得有界节点、Assertion、路径、Episode、Evidence 和冲突，不读取原始 SQL。 | target=设计第 6、9.5 节；inventory=`memory_records.py`、`recall_renderer.py`、`reasoning/memory_context.py`；references=推理和渲染测试；verification=稳定渲染、字符硬上限、来源和类型节点不合成虚假来源测试；residuals=最终自然语言叙述仍由 Reasoning 负责。 | Memory 边界无残余。 |
| MEM-007 | P0 | 开发已关闭 | 已实现新库导入器、只读源保护、数量/摘要/哈希对账、租约恢复和保留操作。无来源旧边和未核验链接会生成确定性警告并跳过，不会成为 active 事实。 | 导入按 Episode 优先、可审计且可回退；不修改旧库，不引入长期双写。 | target=设计第 9.6 节；inventory=`migration.py`、`sqlite_memory_store.py`；references=ADR-0018 和持久化规则；verification=旧库导入、带表族前缀的 ID 映射、可迁移 Episode 哈希匹配、无来源边跳过、证据映射、重开和归档/遗忘测试；residuals=生产数据切换未执行，需单独明确批准。 | 未接触线上用户库。 |
| MEM-008 | P0 | closed | 确定性结构门、完整真实 Ark 门和负责人体验复核均已完成，第一阶段已通过。 | 可重放脱敏报告必须在 Stage 1 晋级前证明结构门、来源锚定、关系/冲突、重启和延迟。 | target=设计第 9.7 节及 `docs/.internal/elfie-stage1-memory-backed-chat-execution-plan.md`；inventory=`devtools/evals/stage1_chat_ark.py`、场景集和聚焦测试；references=`build/evaluations/stage1-chat/e1-ark-real-final/report.json`；verification=最终候选报告记录确定性 E1 86 项测试、33/33 个重复机器场景、33 次结构化 Ark 裁判调用，各适用维度最差分数均不低于 4，持久化扫描退出码 0，负责人已确认匿名样本；1 次 provider 空响应由既有有界失败路径恢复；residuals=生产数据迁移/切换仍是需单独批准的 MEM-007 操作。 | Ark 鉴权和结构化裁判返回均通过，报告未写入密钥。 |
| MEM-009 | P0 | closed（生产调用方；保留兼容层） | Brain、Reasoning 和 Lab 的生产路径均消费类型化 `RecallBundle`/Memory inspection 和唯一的 `Memory Maintenance` 入口；退役 Encoder/Retriever/Formatter 栈在产品/运行时根目录中已无导入。 | 保持唯一 source-first Memory authority；剩余旧面只在单独批准的兼容测试迁移后删除。 | target=设计第 4.3–4.4、6、9.5 节；inventory=`memory_system.py`、`reasoning/memory_context.py`、`elfie/brain_wiring.py`、`devtools/elfie_lab/memory_projection.py`、`devtools/evals/opt003_memory_endurance.py`；references=生产引用扫描和类型化 inspection 回归；verification=`legacy_production_references() == ()`，耐久性/Genesis/维护回归，受影响 Memory/Brain/Genesis、架构、Ruff 和持久化扫描；residuals=旧模块及其算法测试只为语义 Fake 和 Lab 显式回退保留。 | 生产调用方不构造或导入旧检索/格式化对象。 |
| MEM-010 | P0 | closed（维护正确性） | Maintenance 共用有界预算，先 Consolidation 后 Lifecycle；强化后会调度 Node/Assertion；失败保留原检查点；可恢复过期租约并按 owner/attempt 隔离旧 Worker。 | 重试或竞争 Worker 不得跳过、重复或覆盖目标；投影失败时来源 Episode 必须可重试。 | target=设计第 4.3、9.2、9.6 节；inventory=`memory_system.py`、`sqlite_lifecycle_store.py`、`sqlite_graph_store.py`；references=维护强化回归；verification=单预算、仅生命周期唤醒、检查点重试、租约恢复、旧 Worker 隔离和来源保留测试；residuals=维护正确性无残余。 | 写事务不会等待模型/网络。 |
| MEM-011 | P0 | closed（开发目标） | Lifecycle 通过唯一版本化策略直接衰减 `importance`，并将已投影 Episode 按 `full → compressed → digest → archived` 推进；只有归档、依赖安全且低重要性的 Episode 才能遗忘，同时保留摘要存根。没有待投影 Episode 但存在历史到期记录时，维护仍会唤醒。 | 自动遗忘必须受策略控制、来源/Evidence 安全、可重试且可观察，不能删除最后可审计来源。 | target=设计第 6.1–6.3、9.2 节；inventory=`score_policy.py`、`sqlite_lifecycle_store.py`、`memory_system.py`；references=维护回归和 `build/evaluations/stage1-chat/opt003-current/report.json`；verification=历史到期扫描、未投影来源保护、四步生命周期重放、摘要保留、只衰减 importance 和重启检查；residuals=生产数据切换仍单独治理。 | Episode 遗忘不隐式删除 Node、Assertion 或其 Evidence。 |

## 当前基线后的优化台账

下面记录基线之后的当前开发优先级；它们不是对 `MEM-001`–`MEM-008` 已关闭/暂缓状态的改写。

| ID | 优先级 | 状态 | 当前差距 | 下一验收门 | 证据 / 参考 |
| --- | --- | --- | --- | --- | --- |
| OPT-001 | P0 | closed | 有界切片现已让冻结的 E1 fixture 走类型化 Elfaria World Canon/Genesis 路径，移除推理提示中与 Profile/Canon 重复的身份事实，覆盖跨文件发布失败时的清理，并通过确定性 E2/E3 门。 | OPT-001 无后续实现门。 | target=OPT-001；inventory=`config/world/elfaria.yaml`、类型化 Genesis 和领养模块；references=OPT-001 开工文档与 E1/E2/E3 场景集；verification=类型化 fixture、受影响 Memory/Reasoning 测试、确定性 E2/E3、Ruff 和持久化扫描通过；residuals=生产回填按计划未执行。 |
| OPT-002 | P0 | closed | WorkingContext 已能闭合有界话题 Episode，在推理前先落盘来源，抽取带归因的主人/人物事实，保留别名并支持显式纠正链。 | 确定性持续学习回归的八类 source-first 场景全部通过。 | target=OPT-002；inventory=`conversation_context.py`、`settlement.py`、`consolidation.py` 和 SQLite Memory Adapter；references=OPT-002 开工文档与 Memory 设计第 9.4–9.5 节；verification=八类持续学习场景、受影响测试、Ruff 和持久化扫描通过；residuals=生产切换仍由 MEM-007 单独治理。 |
| OPT-003 | P1 | closed (development) | Lifecycle/Memory Maintenance 已采用经过审查的策略驱动遗忘/归档路径；耐久性评测覆盖代表性增长、来源锚定、重启、重试、锁等待以及 Basic/Local 延迟。 | 无人值守维护继续受同一套有界 Worker/租约控制；存储或排序契约变化时重新运行评测。 | target=设计第 6、8.5、9.2 和 9.6 节；inventory=`sqlite_lifecycle_store.py`、`score_policy.py`、`sqlite_graph_store.py`、`node_store.py`、`devtools/evals/opt003_memory_endurance.py`；references=`build/evaluations/stage1-chat/opt003-current/report.json`；verification=10,000 Episode、50,000 Node、200,000 Assertion；全部 Assertion 有来源；Basic p95 14.082ms、Local p95 21.037ms；幂等重试、重启一致、锁等待完成以及 full→compressed→digest→archived→forgotten 全部通过；residuals=生产数据切换不属于本开发门。 |
| OPT-004 | P1/P2 | deferred | 真实精灵巢观测、活动和多精灵互动尚未进入当前聊天闭环。 | 第二阶段真实巢场景接入后，再验证具身记忆和世界事件来源。 | — |

OPT-001 与 OPT-002 曾使用各自功能分支和独立评测并行开发，组合回归已通过。OPT-003 已对开发目标关闭；OPT-004 仍暂缓。

OPT-001 第一版证据（2026-08-28）：target=OPT-001 计划第 3–5 节；inventory=`config/world/elfaria.yaml`、
配置 registry/schema、`elfie/genesis/{contracts.py,initializer.py}`、
`infrastructure/persistence/elfie_workspace/adoption_profiles.py`；references=Elfaria 世界 Canon/物种卡与类型化
Genesis 测试；verification=类型化 fixture 编译测试、15 项聚焦领养/评测测试、受影响的 Memory/Reasoning 测试、
Ruff、`git diff --check` 及既有持久化扫描；Canon 共 42 条事实，每个已发布物种的领养按资格选择 40 条知识 seed，
并生成 5 段 Episode、13 个私有关系对象；注入发布失败测试覆盖物料化清理，推理提示不再重复 Profile/Canon 已提供的
Selfhood 身份事实。未做生产回填；OPT-002 和 OPT-003 已对开发目标关闭，OPT-004 仍暂缓。
类型化 `stage1-e1.v2` fixture 已通过确定性门，并完成一次真实 Ark 单重复运行（26 次 provider 调用；机器门和裁判门均通过），
报告位于 `/private/tmp/elfie-e1-real-20260828-final2/report.md`。
OPT-001 的确定性 E2/E3 门也已通过：2 个 published 物种、每物种 96 条合资格知识问法、240 条 unknown 边界问法，
以及 24 个传记组合（每物种 4 个 life stage × 3 个 seed），报告位于 `build/evaluations/stage1-chat/opt001-e2e3-final/report.json`。
负责人已确认第一阶段体验；未做生产回填；OPT-002 和 OPT-003 已对开发目标关闭，OPT-004 仍暂缓。

OPT-002 实现与评测证据（2026-08-28）：target=持续学习 source-first 流程与 WorkingContext 边界；inventory=`elfie/brain/reasoning/conversation_context.py`、`coordinator.py`、`settlement.py`、`elfie/brain/memory/consolidation.py`、`infrastructure/persistence/memory/{schema.py,sqlite_memory_store.py,sqlite_graph_store.py}`；references=OPT-002 开工文档 §3–§7 与 Memory 设计 §9.4–§9.5；verification=`devtools/evals/opt002_continuous_learning.py` 与 `test/devtools/evals/test_opt002_continuous_learning.py` 的八类场景全部通过：Episode 边界、实体/别名/歧义、主人纠正/重启、冲突、幂等重放、失败重试、投递失败边界、精灵隔离；组合受影响测试 36/36 通过，Ruff 和持久化扫描退出码 0，报告为 `build/evaluations/stage1-chat/opt002-final/report.json`；生产切换仍归 MEM-007。OPT-003 收口证据见上表。

## 验收后的后续工作

1. 如现有用户数据库需要切换，另行批准并执行生产数据切换；开发迁移已经完成。
2. 如果持久化 schema 或排序策略变化，重新运行 OPT-003 的有界增长和可恢复生命周期评测。
3. 第二阶段真实巢接入后，为 OPT-004 建立具身记忆评测。

要求的只读持久化盘点命令是：

```text
uv run --no-sync python scripts/governance/persistence/scan.py --project-root . --check
```

修改 schema 后必须再次运行。每一行只有在 target、inventory、references、verification 和 residuals 五类信息都记录完整后才能关闭。本轮 Memory 强化和 OPT-003 开发证据已收口；生产切换和具身世界评测仍单独治理。

**收口状态：** ready
