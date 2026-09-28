# Elfie Memory 一致性

> 状态：source-first Memory 基线、类型化生产调用方、全新库边界和兼容清理已完成。MEM-013 已对五组本体、全局扩展注册表、schema v1 新库边界、六个图谱切片以及由注册表驱动的 Debug Workspace 类型筛选关闭。MEM-018 仅保留通用 Node 身份/生命周期拆分和普遍 Episode 来源约束；Claim 是普通注册叶类型，没有专属载荷模型。MEM-012 保持 open，因为当前 `memory.v3` 的反馈强化和综合评分超出目标；新目标暂缓这些能力。MEM-014 对历史 `memory.predicates.v2` 方向/对称语义关闭。MEM-015 仍追踪 Episode 边界/大小准入。MEM-016 对类型属性和 Inspector 投影关闭。MEM-017 仅因实时摘要生成保持 open。将 Memory 自我模型结果应用于 Selfhood/Orientation、Pattern 生成/应用和生产数据迁移均不属于本次实现。<br>
> 实现验证基线：2026-09-26<br>
> 目标：[Elfie Memory 设计](../designs/elfie/brain/elfie-memory-architecture)

这是临时一致性台账，记录当前实现相对于 Memory 设计的精确缺口以及关闭所需的证据。它不重定义 Memory 模型，不授权修改数据库，也不是开发过程日志。

> Recall 实现更新（2026-09-26）：已按批准范围完成首版原地切片：类型化 Query/Sense/Filters 与直接亲属查询、单一可重建 FTS5 语料库、Query 优先的 Sense 排序、按来源组装及受限 Bridge/Reasoning 调用。MEM-019、MEM-022 对首版支持范围关闭；MEM-020、MEM-021、MEM-023 仅保留明确列出的性能、平台及真实数据门槛。此前 Recall 行描述的是旧基线。

## 实施台账

| ID | 严重度 | 状态 | 当前差距 | 目标与关闭门槛 | 证据 / 参考 | 残余 |
| --- | --- | --- | --- | --- | --- | --- |
| MEM-001 | P0 | closed | 目标 Adapter 已用审查后的 Episode、节点、Assertion 和 Evidence 表替代旧实体/子类型及嵌入边布局。 | 目标表、约束、所有权和可重建词法投影已实现，不存在第二套边事实源。 | target=设计第 9.1–9.2 节；inventory=`infrastructure/persistence/memory/{schema.py,sqlite_memory_store.py,sqlite_episode_store.py,sqlite_graph_store.py,sqlite_retrieval_store.py}`；references=持久化扫描；verification=目标 schema/往返/重开测试、受影响 Memory/Brain/Genesis/领养测试、架构测试、Ruff、pycompile 和 `git diff --check`；residuals=已有旧库按策略不支持，需显式备份/重建。 | 当前目标无残余。 |
| MEM-002 | P0 | closed | 闭合 Episode 具备完整内容、来源 ID、完整来源哈希、幂等和重启安全写入；已完成互动候选和 Genesis 种子都走先保存来源的路径。未知时间、发生时间精度、归因、隐私和投影来源均显式保留。 | 一个经过校验的 Episode 是详细历史来源；Memory 不负责合并原始回合。 | target=设计第 3、9.1/9.4 节；inventory=`sqlite_episode_store.py`、`memory_system.py`、`genesis/initializer.py`；references=Episode 和 E1 垂直切片测试；verification=重复提交、内容哈希、未知时间、低强度候选、Genesis 来源链和重开测试；residuals=上游事件边界仍负责闭合事件。 | 目标路径无残余。 |
| MEM-003 | P0 | closed | 节点、别名、描述、提及、带类型字面量的限定 Assertion、Evidence 和多对多关联已持久化；身份合并会重定向历史并保留冲突。 | 独立重要性、可信度、极性、视角、时间、类型化值和反驳关系不会被裸三元组覆盖。 | target=设计第 4、9.1–9.3 节；inventory=`sqlite_graph_store.py`、`schema.py`、`predicates.py`；references=source-first 图测试；verification=跨 Episode 别名/身份解析、合并重定向、带来源断言、谓词拒绝、冲突/证据和投影诊断测试；residuals=旧数据库已经覆盖的历史版本不能自动恢复。 | 旧数据可能存在不可恢复冲突。 |
| MEM-004 | P0 | closed | 有界 Worker 领取 Episode，校验有来源模型提案或使用保守确定性抽取，再以可重试的有来源投影在单事务中提交；版本化谓词注册表、来源哈希/修订校验和有界拒绝诊断已强制执行。 | 规范身份、证据绑定、相容合并和冲突保留是确定性的；来源 Episode 在失败时不丢失。 | target=设计第 5、9.3–9.4 节；inventory=`elfie/brain/memory/consolidation.py`、`predicates.py`、`sqlite_graph_store.py`；references=source-first Worker 测试；verification=模型来源校验、全局语义 ID、租约恢复、谓词/版本拒绝、投影修订和来源保留测试；residuals=Provider 与调度仍是注入/运维选择。 | 写事务不会等待无界模型调用。 |
| MEM-005 | P0 | closed（历史基线） | `RecallRequest` 已执行确定性的 Basic/Text 候选检索，再做有界 Local Graph 遍历，并按需要获取 Episode/Evidence 作为语境和来源追踪，同时执行关系/时间/facet/隐私过滤和限制控制。active、superseded 及冲突声明保留状态和证据；常见词候选预过滤和图谱两端查询均有界且可走索引。 | 文本覆盖罕见/未解析表述和经过批准的面向用户 Node 属性；图遍历覆盖明确关系；图谱知识可以直接回答，Episode/Evidence 用于补充语境和来源追踪。 | target=设计第 6、9.4 节；inventory=`sqlite_retrieval_store.py`、`sqlite_graph_store.py`、`sqlite_memory_store.py`、`sqlite_utils.py`、`schema.py`；references=source-first 检索测试和最终 OPT-003 报告；verification=罕见词/别名、无规范名称的 Node 属性检索、人物关系网、知识对象、种子、时间窗口、正向 AND/OR facet、未知时间、隐私、跳数/限制和 10k/50k/200k 代表性延迟检查；residuals=结构化属性过滤、Global/社区和向量检索仍是后续投影。 | 词法投影仍可重建，不构成第二事实源。 |
| MEM-006 | P0 | closed | `RecallBundle` 及确定性渲染器已实现；Reasoning Memory reader 直接传递类型化 bundle，并由有界编译器把关系、路径、条件、Episode、Evidence 和冲突渲染为不可执行的模型上下文。 | 上层通过语义契约取得有界节点、Assertion、路径、Episode、Evidence 和冲突，不读取原始 SQL。 | target=设计第 6、9.5 节；inventory=`memory_records.py`、`recall_renderer.py`、`reasoning/{memory_context.py,memory_compiler.py}`；references=推理和渲染测试；verification=稳定渲染、字符硬上限、类型化 bundle 往返无损、结构化模型投影、来源和类型节点不合成虚假来源测试；residuals=最终自然语言叙述仍由 Reasoning 负责。 | Memory 边界无残余。 |
| MEM-007 | P0 | closed（全新库策略） | 导入器和旧来源路径已删除。Adapter 在任何业务写入前拒绝旧、混合或不支持版本的数据库，并提示操作者备份后显式重建。 | 在写入前拒绝旧/混合数据库，保持文件不变；仅在显式重建后创建当前 schema。 | target=设计第 6.4、9.5–9.6 节；inventory=`sqlite_memory_store.py`、`schema.py`；references=ADR-0018 和持久化规则；verification=旧/混合/v4 数据库无写入拒绝、全新 schema 创建/重开、导入器引用为零；residuals=开发目标无残余。 | 不触碰线上用户库。 |
| MEM-008 | P0 | closed | 确定性结构门、完整真实 Ark 门和负责人体验复核均已完成，第一阶段已通过。 | 可重放脱敏报告必须在 Stage 1 晋级前证明结构门、来源锚定、关系/冲突、重启和延迟。 | target=设计第 9.7 节及 `docs/.internal/drafts/elfie-stage1-memory-backed-chat-execution-plan.md`；inventory=`devtools/evals/stage1_chat_ark.py`、场景集和聚焦测试；references=`build/evaluations/stage1-chat/e1-ark-real-final/report.json`；verification=最终候选报告记录确定性 E1 86 项测试、33/33 个重复机器场景、33 次结构化 Ark 裁判调用，各适用维度最差分数均不低于 4，持久化扫描退出码 0，负责人已确认匿名样本；1 次 provider 空响应由既有有界失败路径恢复；residuals=0.5 之前不执行生产数据迁移，旧库按 MEM-007 备份/重建。 | Ark 鉴权和结构化裁判返回均通过，报告未写入密钥。 |
| MEM-009 | P0 | closed | Brain、Reasoning 和 Lab 生产路径已消费类型化 `RecallBundle`/Memory inspection 和唯一的 `Memory Maintenance` 入口。Lab 回退、旧 Memory 门面分支、旧算法、旧持久化 mixin 及其专门测试均已删除。 | 保持唯一 typed Memory 路径，并证明旧 API/类/模块引用为零。 | target=设计第 4.2、4.4–4.5、6、9.5 节；inventory=`memory_system.py`、`reasoning/memory_context.py`、`devtools/elfie_lab/memory_projection.py`、`devtools/evals/opt003_memory_endurance.py`、`infrastructure/persistence/memory`；references=退役模块扫描和类型化 inspection 回归；verification=旧 API/类/模块引用为零、Memory/Brain/Genesis/Lab/产品回归、架构测试、Ruff 和持久化扫描；residuals=当前目标无残余。 | 生产调用方不构造或导入退役检索/格式化对象。 |
| MEM-010 | P0 | closed（维护正确性） | Maintenance 共用有界预算，先 Consolidation 后 Lifecycle；强化后会调度 Node/Assertion；失败保留原检查点；可恢复过期租约并按 owner/attempt 隔离旧 Worker。 | 重试或竞争 Worker 不得跳过、重复或覆盖目标；投影失败时来源 Episode 必须可重试。 | target=设计第 4.4、9.2、9.6 节；inventory=`memory_system.py`、`sqlite_lifecycle_store.py`、`sqlite_graph_store.py`；references=维护强化回归；verification=单预算、仅生命周期唤醒、检查点重试、租约恢复、旧 Worker 隔离和来源保留测试；residuals=维护正确性无残余。 | 写事务不会等待模型/网络。 |
| MEM-011 | P0 | closed（v1 基线，已被替代） | v1 Lifecycle 已安全地将投影 Episode 按 `full → compressed → digest → archived` 推进，保护来源并扫描历史到期记录，但也会直接衰减 `importance`。 | 保留已经验证的租约、重启、来源安全和一次一阶段机制；其评分语义由 MEM-012 替换。 | target=历史 v1 基线；inventory=`score_policy.py`、`sqlite_lifecycle_store.py`、`memory_system.py`；references=维护回归和 `build/evaluations/stage1-chat/opt003-current/report.json`；verification=历史到期扫描、未投影来源保护、四步生命周期重放、摘要保留、只衰减 importance 和重启检查；residuals=当前设计符合性在 MEM-012 中保持 open。 | 本行只是实现历史，不能证明符合 `memory.v3`。 |
| MEM-012 | P0 | open | 当前代码有 Memory v3 retention profile、confidence/importance 评分及成功使用/结果强化。新设计已明确把反馈收据、强化、分数折叠和自适应/综合排序延期；因此现有实现超出了目标，即使其持久化与生命周期机制已经存在。 | 在另行批准的代码对齐范围内，移除或隔离反馈/强化与排序行为，同时保留约定的静态准入、生命周期和确定性 Recall 契约。不要让这些能力成为本体/Claim 工作的前置条件。改排序前重新核对 Brain 契约。 | target=Memory 设计第 2.3、3.3–3.4、4.3、6、9.2/9.4 节；inventory=`elfie/brain/memory/score_policy.py`、`memory_records.py`、`memory_system.py`、`infrastructure/persistence/memory/{schema.py,sqlite_graph_store.py,sqlite_lifecycle_store.py,sqlite_retrieval_store.py}`；references=Brain 契约中的关系显著性规则及当前设计；verification=先前 Retention v3/持久化与 OPT-003 证据属历史记录，不能证明符合本次延期目标；2026-09-25 只读检查代码，本次文档更新未运行产品测试；residuals=移除边界需独立代码计划和契约复核。 | 在该独立实现获批前保持 v3 行为不变；不隐含 migration/fallback/dual-write。 |

| MEM-013 | P0 | closed | 规范 Node 类型和关系词汇现由 `config/memory/ontology.yaml` 与不可变注入快照提供；产品数据根拥有共享的 `memory/ontology.sqlite` 扩展注册表。核心定义不可覆盖，candidate/deprecated 扩展不能用于新事实。 | 五组叶类型构成唯一 Node 分类；`type_group` 派生得到。Claim 是普通 `claim` 叶类型。自我模型是按边选取的切片，不是 Node 类型。Consolidation 生成五个节点优先类型组切片、一个边优先自我模型切片，再执行最终跨组关系提取。Debug Workspace 类型组选项由同一注册表驱动，只投影图节点/边。 | target=Memory 设计第 2.2.1–2.2.2.1、3.3.1、5.1、9.3 节；inventory=`config/memory/ontology.yaml`、`elfie/brain/memory/{ontology.py,ontology_registry.py,slices.py,consolidation.py,memory_system.py}`、`app/features/operations/memory_ontology.py`、`infrastructure/persistence/memory/{ontology_loader.py,sqlite_ontology_registry.py,schema.py}`、Bootstrap/data-root wiring、Genesis、release manifest 和 Developer Tools 投影；references=Brain 契约本体边界和 Debug Workspace 类型分类契约；verification=受影响 Python 选择首次运行 428 项中有 408 项通过、20 项 Lab 集成/投影失败；补齐注册的 `guided_by` 互逆谓词并迁移旧投影夹具后，20 个精确失败用例全部重放通过，`test_session_projection.py` 为 13 passed；本体、关系、六切片、注册表、旧版库拒绝和自我模型持久化测试通过；Web Vitest（13 个文件/114 项）、TypeScript、持久化扫描及隔离浏览器的组→叶选择、不兼容选择清除、叶→组联动和图计数检查通过。旧版库拒绝保留旧库内容，且未创建 `self_model` Node。修复后没有重跑完整 428 项集合。 | 通用 Node 身份/生命周期和普遍来源片段约束由 MEM-018 独立跟踪。Selfhood 应用、Pattern 生成/应用和生产数据迁移不在本范围。Recall 候选、排序、结果和 Lab 上下文均未改变。 |

| MEM-014 | P0 | closed | 关系语义已冻结为 `memory.predicates.v2`：亲属/社交/角色关系有明确类型，区分方向和对称性，允许粗粒度 `kin_of`，允许同一对端点并存多条关系，并把重要度与置信度分开。旧的通用 `relationship`、`family`、`friend`、`owner` 边界会归一化为规范谓词；共同出现不能推断关系。 | 保持注册表作为唯一可写关系词汇；保持对称关系只保存一条规范 Assertion、方向和反向语义可读、主人 `person` 与领养家庭 `group` 并存，以及有界重要度排序。 | target=Memory 设计第 2.2.2.1/2.3.1 节和 Memory Debug Workspace 关系显示契约；inventory=`predicates.py`、`memory_records.py`、`consolidation.py`、`genesis/initializer.py`、`devtools/elfie_lab/memory_projection.py`、`devtools/web/src/elfie/MemoryDebugWorkspacePage.tsx`；references=Brain 契约关系规则；verification=注册表、Consolidation、Genesis、持久化和 Lab 投影共 56 项 Python 聚焦测试通过；前端 `12 files / 94 tests` 和 TypeScript 通过；隔离全新 Lab 重放显示 `主人=person`、`领养家庭=group`，显式关系 Episode 为 `friend_of`/`neighbor_of`/`kin_of` 各一条、均为对称关系，`friend_of` 重要度 `0.94` 高于 `neighbor_of` `0.35`，仅共同出现的 Episode 没有社会关系边；`git diff --check` 通过。 | 自动推断父母/兄弟和 Pattern 生成仍不在本范围。 |

| MEM-015 | P0 | open | 冻结后的 Memory 模型只有两层语义：已经加工且按话题有边界的 `Episode`，以及基于 Episode 整理出的高层 `Node`/`Assertion` 笔记与图谱。Episode 没有独立标题字段；完整原文仍是来源/检索记录。非空的生成式 `summary_text` 是可选的简短概括，可以只读地作为展示标题；没有摘要时 UI 可用有界正文摘录兜底。它不会替代或截断原文。图谱知识可以直接返回；上游原始聊天/媒体不是默认 Recall 内容；不要求第三个语义 Segment 层。Genesis 把每条 `KnowledgeSeed` 和 `EpisodeSeed` 完整存成来源 Episode 并保持 pending；创建提交只保留有明确来源的身份/关系骨架 Node 与 Assertion；夜间整理只准入稀疏、可复用的 Node/Assertion，不为每条 Episode 凭空创建 event Node，并把 Evidence 回链到 Episode。 | 定义并测试 Episode 边界以及可配置的传输/准入上限（按话题边界拆分或让闭合保持 pending，绝不静默截断），收紧正式 Node/Assertion 准入，异常大 Episode 的内部切片只保留为实现细节。来源点击链和反向 Recall 的运行时回放已经在隔离 Lab 路径上完成。 | target=Memory 设计第 1.1、1.4、2.1、3.3–3.4、4.1–4.2 节和 Debug Workspace 第 3.1、11.3 节；inventory=`elfie/genesis/{serialization.py,initializer.py}`、`elfie/brain/memory/consolidation.py`、`elfie/brain/reasoning/conversation_context.py`、`elfie/brain/memory/memory_records.py`、`infrastructure/persistence/memory/sqlite_episode_store.py`、`sqlite_retrieval_store.py`；references=source-first Genesis 与夜间抽取回归、话题闭合/压缩、FTS 和 Recall 链路；verification=`test/elfie/genesis/test_initializer.py` 已证明知识 Episode 保留原文且整理前没有知识/事件 Node；反向 seed Recall、受影响 Genesis/Memory 测试、前端投影测试和 `git diff --check` 通过；隔离 Lab `elfie_id=61133816` 完成 sandbox Episode 预演：`episodes 107→108`、`nodes 25→27`、`assertions 13→16`、`evidence_for_visible_assertions 13→14`，且 `production_mutated=false`；浏览器打开了完整 Episode 正文、其来源 Evidence 和支撑 Assertion；residuals=最终 Episode 准入/大小契约仍 open。 | 本门禁不包含原始来源召回，也不包含第三个语义层。 |

| MEM-016 | P0 | closed | 类型化属性归属和紧凑 Inspector 投影已经冻结：稳定身份/结构分类值属于经过校验的 Node property；有来源的文字属于 Node description；随时间变化、多值、有冲突、需要独立证据或本身是关系的值属于 Attribute Assertion。Developer Tools 已提供带统一页首、主要内容、分组关联、来源和折叠技术详情的只读类型化 `NodeDetail`/`AssertionDetail`/`EpisodeDetail`/`EvidenceDetail` 投影。 | 已在不改变 Memory/Recall 或 SQLite 权威的前提下实现注册表驱动的展示投影；语义界面隐藏技术元数据；长 Episode 正文显式展开、关系方向/对称性可读、节点类型和属性可见。 | target=Memory 设计第 2.2.1.1 节和 Debug Workspace 第 2.2 节；inventory=`devtools/web/src/elfie/{contracts.ts,MemoryDebugWorkspacePage.tsx,MemoryVisualizations.tsx,inspectorProjection.ts}`、`devtools/elfie_lab/memory_projection.py`、`devtools/memory_audit.py`；references=Brain 契约属性规则和关系显示契约；verification=`pnpm exec vitest run`（13 个文件/99 项测试）、`pnpm exec tsc --noEmit`、`pnpm run build`、`.venv/bin/python3 -m pytest test/devtools/elfie_lab/test_app.py test/devtools/elfie_lab/test_session_projection.py`（33 passed）、`git diff --check`、隔离全新 Lab `elfie_id=61133816`（25 Node/13 Assertion/107 Episode/13 Evidence），以及浏览器中的搜索清除、类型化 Node 详情、可读的对称关系方向、可点击关系 Evidence、Episode 正文和 Evidence → 来源 Episode → 支撑 Assertion 链路；residuals=旧子类型重建、Pattern 生成/应用和未定义 unknown 字段继续由 MEM-013/MEM-015 跟踪。 | 这是 Developer Tools 读模型，不包含 schema migration 或上层 API 变化。 |

## 本体实现与通用 Node 残余

Brain 契约 v1.11 及 Memory/Debug Workspace 设计定义了当前类型体系和投影边界。实现使用五个注册类型组及普通 `claim` 叶类型；没有新增 Claim 专属载荷、表或 Evidence 模型。MEM-013 已关闭本体和注册表驱动投影门。下方 MEM-018 仅保留独立的通用 Node 身份/生命周期及来源片段残余；本次实现不声称解决它们。

| ID | 严重度 | 状态 | 当前差距 | 目标与关闭门槛 | 证据 / 参考 | 残余 |
| --- | --- | --- | --- | --- | --- | --- |
| MEM-018 | P0 | open | 当前 Node 身份/状态模型仍将 candidate/canonical 解析与 active/archived/forgotten 生命周期混在一起，且尚未对所有持久化 Node 和 Assertion 强制来源 Episode 片段。 | 在独立变更中定义互不混淆的 Node 身份与生命周期轴，保留提及解析语义，并对每个 Node 和 Assertion 强制持久 Episode 片段来源。Claim 遵循普通注册 Node 契约，不增加专属载荷或 Evidence 结构。 | target=Memory 设计第 2.2.1、3.1、9.2 节；inventory=`elfie/brain/memory/{memory_records.py,consolidation.py}`、`elfie/genesis/{contracts.py,compiler.py,initializer.py}`、`infrastructure/persistence/memory/{schema.py,sqlite_graph_store.py,sqlite_memory_store.py}` 与 Genesis wiring；references=Brain 契约中的事实来源和 Node 所有权边界；verification=身份/生命周期转换矩阵与普遍来源片段测试仍为后续门禁；当前 schema v1 与本体测试不关闭这些独立约束。 | 需另行批准 schema/契约实现。不隐含 Claim 专属 schema、迁移、fallback 或 dual-write。 |

## 经历卡片展示门

| ID | 优先级 | 状态 | 当前差距 | 目标与关闭门槛 | 证据 / 参考 | 残余 |
| --- | --- | --- | --- | --- | --- | --- |
| MEM-017 | P1 | open | Episode 卡片已经分开显示经历类型、来源和 Maintenance 进度，不再把 Memory 生命周期当成经历状态。Genesis 已在编译/初始化阶段为知识 Episode 生成并持久化来源内的 `summary_text`；当前仍未实现的是实时对话闭合路径的模型概括。旧行的 `summary_text` 可以为空，并回退展示原始正文。 | 卡片按证据显示发生/取得时间、只读 `summary_text`（缺失时回退原文的有界摘录）、本地化经历类型和可观测整理进度。来源或汇总阶段已提供有依据的简短概括时，保留并显示；允许缺失。悬停/键盘聚焦显示正文、时间精度、类型、来源归因、进度和内容细致级别；详情只加入有依据的人物/地点/话题/Node/Assertion/Evidence 关联。卡片不显示 Memory 生命周期。进度来自所属流程/检查点投影及其绑定来源版本的 Maintenance 回执；两者均属操作记录，不能写入 Episode。缺少证据时显示未知/未观测。 | target=Memory Architecture 第 2.1、3.3–3.4.4、4.1、5.1、9.1–9.4 节；Memory Debug Workspace 第 2.2–2.3、3 节；Genesis 第 6.5.8/6.5.10 节；inventory=`devtools/web/src/elfie/MemoryDebugWorkspacePage.tsx`、`devtools/memory_audit.py`、`elfie/brain/memory/memory_records.py`、`infrastructure/persistence/memory/schema.py`；references=来源版本绑定的 Maintenance 读模型和注册经历类型生产端；verification=Genesis/Recall 聚焦测试证明 `KnowledgeSeed.summary_text` 在编译、初始化、SQLite 读取和 Recall 中保持；前端投影测试证明摘要优先、旧行正文兜底。 | 实时对话闭合路径尚不生成模型概括。不得在卡片 UI 从原始对话推测概括；若要支持该路径，仍需明确归属的汇总阶段。 |

## Recall 首版实现与剩余门槛（Brain 1.15）

状态：首版已在本地实现；未读取、迁移或重建生产数据库。实现原地演进既有 Memory 路径，不新建服务、第二套 Recall 或通用图框架。MEM-005/MEM-006 的已关闭证据仅覆盖此前基线；下表记录本切片和剩余验收门。

### 当前起点与保留项

当前实现链路是可选的当前情绪准入或大模型选择的类型化 `RecallMemory` 请求 → `MemorySystem.recall` → FTS5 Query / Sense / 直接亲属并行检索 → 资格及调用方过滤 → 确定性合并/排序/限额 → 带主命中/支撑角色的类型化 `RecallBundle` → 有界 compiler/renderer。Query 不再从用户原话推断。FTS5 是可重建投影，SQLite 事实表仍是权威源。

必须保留：单只 Elfie 命名空间、Episode/Node/Assertion/Evidence 来源链、注册谓词方向/对称性、修订绑定、只读查询、稳定 ID、已有捕获/整理事务及新库策略。无关 Genesis、UI、本体及 Node 生命周期拆分工作不混入本切片。MEM-012 中仅检索排序偏差在本计划收敛，反馈/Retention 的其他残余继续 open；MEM-018 的通用身份/schema 工作仍独立。

| ID | 优先级 | 状态 | 当前差距 | 最小改动与关闭门槛 | 证据 / 参考 | 残余 |
| --- | --- | --- | --- | --- | --- | --- |
| MEM-019 | P1 | closed（首版契约） | 旧 `mode` 与纯文本调用方无法表达约定的请求。 | 类型化 Query、Sense、Filters、有界 limits、明确状态及支持的亲属请求；生产调用方不再使用旧 `mode`。 | target=Brain 1.15、设计 §3.4/4.2；inventory=memory records、Memory facade、Bridge、Reasoning action 与诊断；references=source-first/Reasoning 契约测试；verification=类型化 query/filter、去重、预算、revision、decoder 测试通过；residuals=不支持的通用图 plan 明确拒绝。 | 不增加通用图语言。 |
| MEM-020 | P1 | open（性能/平台） | 旧 LIKE 路径已由 FTS5 替换；相关性校准和支持平台覆盖尚未证明。 | 每精灵一个可重建 FTS5 投影，覆盖 Episode/Node/Assertion，按权威记录回读、过滤下推并限制候选池。 | target=设计 §3.4.3/5.2；inventory=schema v1、FTS row-ID 映射及 SQLite retrieval/write/rebuild 所有者；references=FTS5 source-first 测试及 OPT-003 重放；verification=60 项聚焦 schema/store 测试和持久化扫描通过；首次规模重放暴露 O(n²) 替换并在索引构建阶段停止；增加行号映射后，10k/50k/200k 重放已进入 Recall 测量，但在 FTS 候选检索处按 10 分钟开发检查预算停止，未生成报告或延迟结论；residuals=全量 Recall 延迟、发行平台和真实数据相关性仍 open。修改前冻结报告为评测器 v3，当前原地评测器为 v4，不能视为严格成对比较。 | 不接入向量，不静默回退 LIKE。 |
| MEM-021 | P1 | open（真实数据质量） | Demo Sense 联想已实现；没有可用的真实历史数据判断效果。 | 仅匹配有来源、`felt` 归因的规范情绪；仅在双方强度存在时比较强度；Query+Sense 不能放行不满足 Query 的候选。 | target=设计 §3.4.4–3.4.5；inventory=Episode 字段、retrieval、Bridge；references=情绪正反例及 stale snapshot 测试；verification=合成场景功能测试通过；residuals=真实情绪覆盖与阈值质量未知。 | 不补造值，不扩多维 Sense。 |
| MEM-022 | P1 | closed（直接亲属首版） | 通用邻居扩展没有表达受限的亲属查询意图。 | 一跳已注册父母/子女/兄弟姐妹查询保留方向、唯一名称解析、歧义、否定/冲突、来源路径与截断状态。 | target=设计 §3.4.3；inventory=类型化请求、本体注册表、retrieval/graph store；references=直接亲属测试；verification=父母谓词双方向、对称兄弟姐妹、重名/缺失锚点及负边测试通过；residuals=未记录边不能证明现实中无亲属。 | 不推导亲属，不增加多跳 schema。 |
| MEM-023 | P1 | open（端到端残余） | Bridge、确定性选择、输出角色及受限 DIRECT 按需 Recall 已实现；干净的集成运行和真实个体质量仍未证明。 | 保留主命中/支撑区分、来源、空/部分状态、重复请求身份、固定 revision 与 DIRECT/DELIBERATE 预算。 | target=设计 §3.4.5–3.4.6/8.3；inventory=Reasoning memory context/compiler/run/observation、renderer 和 retrieval；references=聚焦 Bridge/Reasoning/compiler 测试；verification=受影响契约通过，除下文记录的两个无关既有夹具失败；residuals=未声称完整 Runtime/Provider 或真实数据质量。 | 不重做推理模式、UI 或反馈清理。 |

### 已实现范围与验收依据

以下记录首版实现的取舍。Reasoning 只新增 Brain 1.15 的 DIRECT 有界 Recall 例外；既有深度选择算法和所有外部行动守卫保持不变。

| 范围 | 首版实现 | 证据 / 残余 |
| --- | --- | --- |
| Sense 准入与匹配（MEM-021） | Bridge 至多准入当前快照中最强的 active 规范情绪；历史候选要求有来源的自归因 `felt` 情绪。双方都有强度时才比较强度。 | 有来源情绪、缺失/过期快照及 Query+Sense 合成场景测试通过。真实历史覆盖和阈值质量未验证。 |
| 调用与请求身份（MEM-019/023） | 大模型按需选择类型化 Recall；不从原话/正则推导基线 Query。DIRECT 仅当预算能保留后续最终回答时暴露一次 Recall；完整请求/过滤/revision 身份用于去重。DELIBERATE 保留现有循环。 | 聚焦 Bridge、decoder、预算、去重和 Reasoning 测试通过。两个无关的工作区夹具失败见下文；未调用付费 Provider，未声称完整 Runtime 验收。 |
| 确定性检索与输出（MEM-020/023） | Episode/Node/Assertion 共用 FTS5 语料；精确身份档位、有效词覆盖率 ≥0.34、有界候选池、BM25/稳定顺序；Sense 只在固定 Query 候选池内决胜；类型化过滤、主命中/支撑角色和有界渲染。 | source-first、亲属和 compiler 功能测试通过；schema/store 聚焦集为 60/60。规模、相关性和发行平台门仍 open。 |
| 规模/生命周期（MEM-020/023、OPT-003） | 复用 1 万 Episode / 5 万 Node / 20 万 Assertion 的现有评测器。首次同规模运行暴露元数据未索引导致的 FTS 替换 O(n²)；schema v1 已增加行号 B-tree 映射，聚焦替换/重建测试通过。 | 修复后的重放已到 FTS Recall 测量阶段，随后按 10 分钟开发检查预算停止，未产生报告，因此不声称前后延迟；冻结基线为评测器 v3，当前原地评测器为 v4。全规模与发行平台门继续 open。 |

受影响的聚焦测试包结果为 177 passed、2 项失败，均不在 Recall 改动内。Brain 1.15 架构契约测试已通过，并保留原有语义断言。剩余两项为 `test_committed_resident_starts_without_genesis_source`（测试 monkeypatch helper 不接收当前 `ontology` 参数）和 `test_memory_maintenance_exposes_ordered_consolidation_counts`（整理夹具提交 `entity` 时缺少必需的 `entity_level`）。它们作为工作区既有的范围外残余保留，本次未修改。

批准的实施顺序已在现有模块内完成：确认 FTS5 能力与冻结规模档，统一类型化请求和调用方，实现 Query/Sense 检索、直接亲属、确定性选择/组装及 Bridge/Reasoning 集成，再运行聚焦回归和现有规模评测器。上表区分已关闭范围与仍 open 的门。没有迁移或回填生产数据库，没有调用付费 Provider，也不声称已覆盖所有发行平台。

### 待后续补齐的设计差距（本轮未实现）

上面的首版实现证据不代表实现已符合完整 Recall 设计。以下六项差距保持 open，留待后续单独确定范围并处理；本记录不代表已实现或修改设计。

| ID | 相对 Recall 设计仍存在的差距 | 后续关闭所需证据 |
| --- | --- | --- |
| RECALL-GAP-01 | Query + Sense 尚未作为两条独立候选链路实现：Sense 目前只在固定的 Query 候选池内评分/决胜，因此 Query 未召回的 Sense 命中无法进入结果。 | 对照设计确认 Query/Sense 的预期关系，并测试仅 Query、仅 Sense、两者同时存在的候选池；包括 Sense 命中未出现在 Query 结果中的场景。 |
| RECALL-GAP-02 | 仅 Sense 检索最多返回一个 Episode，而不是保留多个各自达到强度要求的场景/情绪匹配项。 | 确认预期返回数量与上限，并测试零个、一个、多个合格候选及阈值和截断行为。 |
| RECALL-GAP-03 | 过滤能力比设计窄：没有 Node 类型组过滤；Recall 入口也没有始终依据已注册本体拒绝不支持的 Node 类型或关系名，非法值可能表现为空结果。 | 对齐设计中的过滤维度，并测试“不支持的输入状态”与“合法但无匹配结果”的区别。 |
| RECALL-GAP-04 | 面向模型的请求没有通用 Episode/Node/Assertion 精确 ID 查找；`RecallBundle` 也不提供逐结果的匹配原因或命中词（后者目前仅用于诊断）。 | 确认精确 ID 和解释字段的需求，再通过消费方可见的 bundle 测试 ID 查找与匹配依据。 |
| RECALL-GAP-05 | 图检索仅覆盖一跳亲属关系切片。通用锚定图计划（例如材料、空间、因果或多跳关系）不可执行，也没有结构化图路径输出。 | 按真实场景确定支持的图查询切片；针对选定切片测试锚点解析、有界遍历、返回路径/来源及不支持计划状态。 |
| RECALL-GAP-06 | 图候选在截断前按重要度/置信度排序，会影响哪些候选保留下来；这与设计中不把这些字段作为排序加分项的规则不一致（显式硬过滤除外）。 | 对相关性相同但重要度/置信度不同的候选测试截断选择，并使实现符合最终确认的排序规则。 |

### 验证范围、停止条件与非目标

- 重点复用 `test/elfie/brain/memory/test_{memory_system,tokenizer}.py`，`test/infrastructure/persistence/memory/test_{source_first_memory,memory_contract_hardening,recall_selection_observation}.py` 及 `test/elfie/brain/reasoning/test_{memory_context,memory_compiler}.py`，新增用例就近放置，不创建根目录测试或新评测框架。
- API 改动追加一个直接上层 Reasoning 契约测试；schema 改动追加当前 schema 拒绝/重开测试与持久化 inventory，选一个相关架构检查。使用 `scripts/quality/validation/test_bundles.py --selectors ...` 执行选中测试及局部 lint/typecheck；不默认跑全仓或启动服务/UI。
- FTS5 在某个受支持运行包不可用、中文短词回归、来源丢失或正例全部返回空时不能关闭切片；报告精确缺口，不用无声 LIKE 回退或放松断言掩盖。不得为解决依赖升级 CPython 3.9.25。
- 本次实现限于已批准的本地代码与文档范围；未重建生产数据、安装依赖、提交、推送、创建 PR 或发布。向量、复杂图语言、多维 Sense、生产迁移、反馈强化和 UI 改版仍不在范围内。

### 技术可行性与剩余验证

此前仅文档版本断言的残余已关闭：Brain 1.15 架构契约检查通过。上面列出的两项范围外失败仍保持 open，不能当作 Recall 回归证据。

首选 SQLite FTS5/BM25 与同库结构化索引，无需更换事实数据库；FTS5 是虚拟表/专用全文索引，不是给正文加一个普通 B-tree 就能得到全文检索。文档与 Query 使用同一规范化，索引由 Adapter 在事实提交边界维护，可从来源重建。细节与官方参考见设计 §5.2。

2026-09-26 使用项目 `.venv/bin/python3` 在独立 `:memory:` 库探测：CPython 3.9.25、SQLite 3.50.4；FTS5 创建、MATCH、BM25 及预分词中文查询通过。三字 trigram 查询可命中而两字查询不行，因此首版采用字/二元组合预分词。当前 source-first 持久化测试还覆盖 FTS 写入、更新、重建、重开和 旧版库拒绝；仍未证明发行平台覆盖或真实中文相关性质量。

向量检索有现成 SQLite 扩展（例如 sqlite-vec），但还需选择 Embedding、固定模型/维度/版本、验证 CPython/各平台的扩展加载和发行依赖，以及比较召回收益；这些未安装、未验证，也不阻塞上述首版。需要时单独开启向量切片，不把 B-tree 或已有 FTS 表误认为向量索引。

## 当前基线后的优化台账

下面记录基线之后的当前开发优先级；它们不是对 `MEM-001`–`MEM-008` 已关闭/暂缓状态的改写。

| ID | 优先级 | 状态 | 当前差距 | 下一验收门 | 证据 / 参考 |
| --- | --- | --- | --- | --- | --- |
| OPT-001 | P0 | closed | 有界切片现已让冻结的 E1 fixture 走类型化 Elfaria/Genesis 路径，移除推理提示中重复的身份事实，覆盖跨文件发布失败时的清理，并通过确定性 E2/E3 门。 | OPT-001 没有后续 Memory 实现门；本行不关闭 ELF-010、ELF-013 与 CFG-005 记录的 Profile/Genesis 所有权迁移。 | target=OPT-001；inventory=`config/world/elfaria.yaml`、类型化 Genesis 和领养模块；references=OPT-001 开工文档与 E1/E2/E3 场景集；verification=类型化 fixture、受影响 Memory/Reasoning 测试、确定性 E2/E3、Ruff 和持久化扫描通过；residuals=生产回填按计划未执行；创建资料所有权迁移由其他台账跟踪。 |
| OPT-002 | P0 | closed | WorkingContext 已能闭合有界话题 Episode，在推理前先落盘来源，抽取带归因的主人/人物事实，保留别名并支持显式纠正链。 | 确定性持续学习回归的八类 source-first 场景全部通过。 | target=OPT-002；inventory=`conversation_context.py`、`settlement.py`、`consolidation.py` 和 SQLite Memory Adapter；references=OPT-002 开工文档与 Memory 设计第 9.4–9.5 节；verification=八类持续学习场景、受影响测试、Ruff 和持久化扫描通过；residuals=生产切换仍由 MEM-007 单独治理。 |
| OPT-003 | P1 | closed（v2 基线；新 schema 后重跑） | v2 Lifecycle/Memory Maintenance 和耐久性评测已覆盖代表性增长、来源锚定、重启、重试、锁等待以及 Basic/Local 延迟，且不调用模型。 | 保留有界 Worker/租约控制；本体/Claim schema 或 Recall 筛选变化后，重跑直接受影响的规模和生命周期检查。不要增加反馈强化或自适应排序门：当前目标已将这些能力延期。 | target=设计第 6、8.4–8.5、9.2 和 9.6 节；inventory=`sqlite_lifecycle_store.py`、`score_policy.py`、`sqlite_graph_store.py`、`devtools/evals/opt003_memory_endurance.py`；references=`/private/tmp/opt003-v2-full.json`（历史本机脱敏机器报告）；verification=v2 基线：10,000 Episode、50,000 Node、200,000 Assertion；全部 Assertion 有来源；Basic p95 59.503ms、Local p95 47.960ms（各 30 次）；幂等重试、重启一致、锁等待完成、退役模块/导入为零以及 `full→compressed→digest→archived→forgotten` 全链路重放均通过；seed 513.232 秒，进程总时长 537.174 秒；residuals=schema/Recall 改动后需重跑；v3 反馈/排序行为作为独立设计差距由 MEM-012 跟踪。 |
| OPT-004 | P1/P2 | deferred | 真实精灵巢观测、活动和多精灵互动尚未进入当前聊天闭环。 | 第二阶段真实巢场景接入后，再验证具身记忆和世界事件来源。 | — |
| OPT-005 | P1 | deferred | 当前图谱能保存并召回带来源的 Node/Assertion，但尚未把它们聚合为 Pattern 知识 Node，也不能按场景召回并应用 Pattern；`pattern` 是目标注册类型，`patterns_created` 按设计保持为零。 | 将带来源的图上 Pattern 提案、确定性校验/持久化、由事实所有者提供的场景特征匹配/向上遍历和结构化 `RecallBundle` 消费作为一个经过评测的切片。首期不加结果反馈或自适应排序；只有独立设计批准后再加。 | target=设计第 2.2.1、3.5 节；inventory=`elfie/brain/memory/consolidation.py`、`memory_records.py`、`reasoning/memory_context.py`；references=Memory Abstraction Loop 边界；verification=未来的来源/幂等测试和跨场景召回/应用评测；residuals=Pattern 生成和应用当前均明确缺失，反馈仍延期。 |

OPT-001 与 OPT-002 曾使用各自功能分支和独立评测并行开发，组合回归已通过。历史 OPT-003 v2 验收仍对该基线有效；当前 schema 的重跑尚未完成，继续由 MEM-020/MEM-023 跟踪；OPT-004 与 OPT-005 仍暂缓。

OPT-001 第一版证据（2026-08-28）：target=OPT-001 计划第 3–5 节；inventory=`config/world/elfaria.yaml`、
配置 registry/schema、`elfie/genesis/{contracts.py,initializer.py}`、
`infrastructure/persistence/elfie_workspace/adoption_profiles.py`；references=类型化 Elfaria 创建资料/物种卡与
Genesis 测试；verification=类型化 fixture 编译测试、15 项聚焦领养/评测测试、受影响的 Memory/Reasoning 测试、
Ruff、`git diff --check` 及既有持久化扫描；Canon 共 42 条事实，每个已发布物种的领养按资格选择 40 条知识 seed，
并生成 5 段 Episode、13 个私有关系对象；注入发布失败测试覆盖物料化清理，推理提示不再重复 Selfhood 已提供的
Selfhood 身份事实。未做生产回填；OPT-002 和 OPT-003 已对开发目标关闭，OPT-004 仍暂缓。
类型化 `stage1-e1.v2` fixture 已通过确定性门，并完成一次真实 Ark 单重复运行（26 次 provider 调用；机器门和裁判门均通过），
报告位于 `/private/tmp/elfie-e1-real-20260828-final2/report.md`。
OPT-001 的确定性 E2/E3 门也已通过：2 个 published 物种、每物种 96 条合资格知识问法、240 条 unknown 边界问法，
以及 24 个传记组合（每物种 4 个 life stage × 3 个 seed），报告位于 `build/evaluations/stage1-chat/opt001-e2e3-final/report.json`。
负责人已确认第一阶段体验；未做生产回填；OPT-002 和 OPT-003 已对开发目标关闭，OPT-004 仍暂缓。

OPT-002 实现与评测证据（2026-08-28）：target=持续学习 source-first 流程与 WorkingContext 边界；inventory=`elfie/brain/reasoning/conversation_context.py`、`coordinator.py`、`settlement.py`、`elfie/brain/memory/consolidation.py`、`infrastructure/persistence/memory/{schema.py,sqlite_memory_store.py,sqlite_graph_store.py}`；references=OPT-002 开工文档 §3–§7 与 Memory 设计 §9.4–§9.5；verification=`devtools/evals/opt002_continuous_learning.py` 与 `test/devtools/evals/test_opt002_continuous_learning.py` 的八类场景全部通过：Episode 边界、实体/别名/歧义、主人纠正/重启、冲突、幂等重放、失败重试、投递失败边界、精灵隔离；组合受影响测试 36/36 通过，Ruff 和持久化扫描退出码 0，报告为 `build/evaluations/stage1-chat/opt002-final/report.json`；生产切换仍归 MEM-007。历史 OPT-003 v2 证据仍记录在上方；当前 schema 的重跑未完成。

## 验收后的后续工作

1. 0.5 之前，旧 Memory 数据库只允许显式备份后重建全新根目录；不执行生产数据迁移。
2. 如果持久化 schema 或排序策略变化，重新运行 OPT-003 的有界增长和可恢复生命周期评测。
3. 第二阶段真实巢接入后，为 OPT-004 建立具身记忆评测。
4. 只按设计第 3.5 节定义的完整“抽象—应用”切片实施 OPT-005，不先制造无法使用的 Pattern 数据。
5. 在另行批准的代码对齐任务中解决 MEM-012；不要在本体/Claim 切片中实现已延期的反馈、强化或自适应排序。

要求的只读持久化盘点命令是：

```text
uv run --no-sync python scripts/governance/persistence/scan.py --project-root . --check
```

修改 schema 后必须再次运行。每一行只有在 target、inventory、references、verification 和 residuals 五类信息都记录完整后才能关闭。当前代码已进入 `memory.v3` 最小实现切片；冷 Recall、生产切换、具身世界评测和抽象/应用闭环仍单独治理。

当前最小切片的本地验证证据（2026-08-31）是：受影响 Memory/Brain 与持久化测试 `117 passed`；Ruff 检查和格式检查通过（24 个文件）；mypy 检查 21 个源码文件无问题；compileall 退出码为 0；持久化扫描退出码为 0；`git diff --check` 通过。该证据仍是聚焦验证，不替代 OPT-003 的大规模耐久/重启重跑或其他延期验收门。

**收口状态：** open
