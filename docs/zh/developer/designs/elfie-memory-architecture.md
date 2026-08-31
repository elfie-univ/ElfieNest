# Elfie Memory 架构

> 状态：目标设计。本文是 Memory 语义和类型化访问契约的权威；代码和一致性台账记录实际实现状态。
>
> 范围：持久化的主观经历、有来源的个人知识和确定性召回。不定义 Event Workspace 或 Reasoning 的完整上下文策略，也不定义其他模块的状态。

## 1. 目标、边界和所有权

### 1.1 Memory 要解决什么问题

Memory 为一只精灵提供持久、有来源的个人记忆。它既保留发生过什么的细节，也保留可按措辞、时间、人物、情绪、主题和关系召回的语义结构。

设计由三个不可拆开的部分组成：

1. **Episode Timeline（经历时间线）**：按时间顺序保存完整、有边界的经历。
2. **Personal Knowledge Graph（个人知识图谱）**：保存从这些经历和 Genesis 批准知识中投影出的语义节点与关系。
3. **Hybrid Graph/Text Retrieval（图谱/文本混合检索）**：联合检索文本、图结构和来源证据。

这就是 **source-first（来源优先）** 设计：图谱是历史来源的投影，不是历史来源的替代品。

### 1.2 Memory 不负责什么

Memory 接收已经闭合的事件，不决定事件从哪里开始或结束。它不拥有 Profile、不可变身份、当前位置、实时身体状态、实时情绪、进行中的计划、承诺、权限或外部行动。它不直接读取 Profile、Communication 历史、世界运行时状态或其他模块的数据库。需要使用的事实必须由所有者作为带来源的事件或引用提供。

Memory 不负责组织回复，也不定义 Brain 的 Working Memory 或 Reasoning 的完整上下文，只通过类型化 Recall 契约返回有界、带来源的材料。

### 1.3 Memory 与 Brain / Cognitive Consolidation 的关系

普通 Memory 写入只接受完整、带来源的 `ClosedEpisode`。跨系统的 `Cognitive Consolidation` 调度器只是后台入口：目标是 Memory 时，它调用或分配 `Memory Maintenance` 的预算。Memory 拥有持久化写入、图谱投影、召回和生命周期维护；其他调度器或所有者都不能再创建第二条 Memory 写入路径。

`Memory Maintenance` 是 Memory 所有的操作。它与跨系统的 `Cognitive Consolidation` 调度器有关联，但不是同一个东西。

### 1.4 核心来源规则

对于在线 Memory 模型，来源只有两种：

- 普通运行时：完整、已闭合的 `ClosedEpisode`；
- 一次性初始化：完整、有版本的 `ApprovedSeedSource`。

每个持久化 Assertion 都必须指向一个 Episode 或批准种子的 Evidence。模型提案、摘要、缓存或没有来源的 Profile 值都不是证据。运行时学习始终先写 Episode；只有批准的 Genesis 路径可以直接投影初始 Node/Assertion。

## 2. 持久记忆模型

### 2.1 Episode Timeline

Episode 是一个有意义、有边界、已经闭合的事件或场景，不是一轮聊天，也不是关键词摘要。上游事件边界先把相关回合或观察聚合起来，再交给 Memory。

Episode 可以是一段对话或关系事件、一次学习过程、一次身体或环境经历、一次包含文字/音频/视频/图片的感知，或一次有意义的情绪/社会事件。

它保留：

- 稳定 ID、发生时间范围和事件类型；适用时记录历史 `life_stage`/`temporal_label`（例如 `youth` 或 `before_arrival`），并与写入时间分开；
- 参与者、地点、物品和场景上下文；
- 完整原文/转写和持久媒体引用；
- 可用时的派生特征；
- 精灵观察到、被告知、推断或感受到的内容及其归因；
- 来源引用、隐私范围、`importance`、`retention_profile`、`half_life_days`、`detail_level`、`lifecycle`、版本和内容哈希。

运行时学习必须先完整写入，再投影图谱。例如学习牛顿第一定律时，解释、教学上下文和来源先作为一个 Episode 保存，后续维护再从中投影可复用知识。Genesis 种子内容在批准来源中保持完整；属于个人经历的传记种子表示为完整 Episode。

后续维护可以把细节从 `full` 变为 `compressed` 或 `digest`，并把记录作为独立生命周期状态归档。摘要不能替代图谱所需的最后可审计来源。

### 2.2 Personal Knowledge Graph

图谱是精灵自己、带来源的主观理解，不是客观万能数据库，也不会静默导入模型常识。它是可持久化的投影，但可以依据完整 Episode、批准的种子来源及其 Evidence 重建和对账；投影修订号标识它对应的来源版本。

#### 2.2.1 Nodes

节点是异构语义锚点，包括精灵、人、宠物、群体、星球、地点、设施、物品、食物、物种、概念、文化观念、物理规律、理论、情绪、主观体验、事件引用和 Claim/知识对象。

Node 具有稳定身份、`node_type`、规范名称、作用域、状态、`importance`、`retention_profile`、`half_life_days` 和 `confidence`。别名和带来源的描述与 Node 关联。大小和层级通过 `part_of`、`subtype_of`、`generalizes` 等带类型关系表达。不把每个词都拆成 Node；可复用的语义单元才规范化，完整措辞仍保留在描述或 Episode 中。

#### 2.2.2 Assertions / Relations

Assertion 是带来源的命题。简单命题可以表示为带类型的有向关系：

```text
地球 --has_shape--> 球体
主人 --helped--> 精灵
```

它可以带 Node 或带类型字面量作为对象，并包含极性、认识状态、时间范围、视角、上下文、有效期、冲突组、`importance`、`retention_profile`、`half_life_days` 和 `confidence`。对于社会关系亲密度、信任度等领域专属程度，使用带类型的 Assertion 限定信息；`importance` 是召回和维护使用的默认边重要性。Evidence 行及其立场提供支持记录，不再存第三个语义分数。

如果命题本身有条件、版本、描述或证据，就用 Claim/知识 Node 以及相关 Assertion 表达，而不是把整句话硬塞进一条边：

```text
NewtonFirstLaw --part_of--> ClassicalMechanics
NewtonFirstLaw --related_to--> Inertia
NewtonFirstLaw --has_condition--> NetForceIsZero
```

没有某条关系表示“尚未记录”，不表示“明确为假”。

#### 2.2.3 Evidence

Evidence 是一级来源关联。它标识 Episode 或 `ApprovedSeedSource` 及其来源版本、摘录或媒体定位、模态、文本片段、捕获时间、说话者/视角和抽取运行。Assertion 与 Evidence 的关联带有一种立场：`supports`、`contradicts` 或 `context`。

一个 Assertion 可以有多条独立 Evidence。重复写入同一来源关联必须幂等。即使描述被压缩或模型提案被丢弃，Evidence 仍然保留。

#### 2.2.4 Aliases、Descriptions、Episode Mentions

别名、描述和提及单独成子记录，是因为一个 Node 可以有很多条记录，而每条记录都可以保留自己的来源/定位、内容或片段、种类/解析状态和可信度。它们不单独拥有重要性分数，可用状态跟随父记录/来源的保留策略。Node 主表只保留规范身份和有界摘要。

`episode_mentions` 记录有语义意义的表面提及、角色/片段和解析状态（`resolved`、`ambiguous` 或 `unresolved`），不记录每个词。未解析提及和原始措辞仍可在 Episode 中搜索，因此一个罕见词在还没有成为规范 Node 前也能被召回。

首版实现限制每个 Episode 的语义提及数量（默认 128 条）并报告溢出；完整来源文本不能被截断。

#### 2.2.5 冲突、视角和 Claim Node

相互矛盾或依赖视角的命题保留为冲突组中的不同 Assertion。极性、认识状态、有效时间和视角都保留；规范化只合并身份，不合并分歧。命题本身需要条件、版本或多种描述时使用 Claim Node。没有来源关联的 Assertion 不能提升为事实。

### 2.3 分数和生命周期状态

#### 2.3.1 importance

`importance`（`I`）表示 Episode、Node 或 Assertion 对精灵的持久语义重要性，范围为 `[0, 1]`。它不是鲜度、熟悉度、Evidence 数量或检索频率，自然时间永远不改变它。合格语义事件把 `I` 向策略拥有的目标 `T_I` 移动：

```text
raise 且 T_I > I：I' = I + eta * (T_I - I)
lower 且 T_I < I：I' = I + eta * (T_I - I)
```

`memory.v3` 事件类别是普通 `routine` `(T_I=.35, eta=.10)`、有意义 `meaningful` `(.60, .20)`、重大 `major` `(.85, .35)` 和核心 `core` `(1.0, .50)`。可审计的重新评价使用普通降低 `(.30, .25)`、重大降低 `(.10, .50)` 或解除 `(0, 1)`。模型可以提出事件类别，但不能选择 `T_I` 或 `eta`。Node 与 Assertion 的重要性各自独立，不能沿图邻接传播。

更新按 `(event_id, target_kind, target_id)` 幂等。同一 ClosedEpisode 内同一目标、方向和类别的重复信号只结算一次。跨 Episode 时，提高和降低方向分别进入按事件时间排列、由窗口首个事件锚定的 24 小时窗口；每个方向/窗口只结算最高类别。相反方向仍是两次独立重估，并按事件时间折叠。收据保留来源、发生时间和策略版本；迟到事件按 `(occurred_at, event_id)` 重放，因此到达顺序不会改变结果。过期、长期未使用、召回失败和冲突 Evidence 都不会在缺少独立语义重估事件时降低 `importance`。

#### 2.3.2 Retention 与 freshness

每个 Episode、Node 和 Assertion 都保存 `retention_profile`、`half_life_days`（`H > 0`）、`last_reinforced_at` 和 Retention 策略版本。`H` 是 freshness 从 `1` 降到 `.5` 所需时间，不是剩余天数；仅仅经过时间不会改变 `H`。当前 `freshness`（`F`）只派生、不持久化：

```text
t = max(0, now - last_reinforced_at)
F(t) = 2^(-t / H)
```

因此 `F(0)=1`、`F(H)=.5`、`F(2H)=.25`。Memory 只拥有一套带版本的准入策略，根据记录种类、已注册的 Node 类型或 Assertion predicate、经授权的来源类别及有界显著性信号，解析出策略拥有的 `retention_profile` 和初始半衰期 `H0`；调用方和模型不能选择任意数值。初始 profile 为：短暂细节 `transient` `.5` 天、普通运行时 Episode `ordinary` `2` 天、显著 Episode `salient` `9` 天、可复用语义 Node/Assertion `semantic` `30` 天、Pattern/规律 `pattern` `60` 天、稳定人物/身份/长期关系 `stable_identity` `365` 天、经授权 Genesis `genesis` `3650` 天。event/context Node 以及 `involves`、`temporal`、`felt` 等情景 Assertion 跟随来源 Episode profile。同一记录种类同时命中多个条件时，按 `genesis > stable_identity > pattern > semantic > salient > ordinary > transient` 确定性选择。持久化最终 profile、策略版本和准入原因。强烈且有来源的情绪、感官或后果显著性可以把运行时 Episode 提升到 `salient`，但不能自动提高 importance 或 confidence。强化只改变 `H`，保留 profile 作为准入来源；带来源的重新学习才可以重新解析 profile 和 `H0`。所有经授权的 Genesis 记录都选择 `genesis`：其十年数值是半衰期（十年后 `F=.5`），不是归档截止期；归档和遗忘由 Lifecycle 独立决定。`H` 的全局上限为 `36500` 天。

记录只有在产生带来源的合格结果或直接学习事件后才能强化：此前的准确使用被明确确认有用/正确、使用它的行动成功、一次隐藏来源的主动复习被独立验证成功，或新的独立 Evidence 通过正常 Consolidation 路径直接再次覆盖这条精确记录。失败检索后的权威重新呈现遵循下文单独的重学规则，不获得成功使用乘数。聊天回答仅仅完成不等于得到确认。候选生成、进入 RecallBundle/Prompt、图邻接、情绪/感官命中、维护、模型自称成功以及失败/拒绝/结果未知都不合格。强化公式在 `0 < F <= 1` 上连续，不含 Lifecycle 阈值；非 superseded 的归档记录被成功回忆后，按同一规则判定资格。一个唯一合格事件执行：

```text
difficulty = 1 - F
multiplier = 1 + 2 * difficulty = 3 - 2F
H' = min(36500, H * multiplier)
last_reinforced_at = event.occurred_at
```

倍数在 `F=1` 时为 `1`，在半衰期 `F=.5` 时为 `2`，并在 `F` 趋近零时趋近硬上限 `3`。初版带版本的调度校准采用 `p_success(F)=F`，因此按成功率加权的相对收益是 `G(F)=p_success(F)*(multiplier-1)=2F(1-F)`，它在 `.5` 有唯一最大值 `G(.5)=.5`。所以半衰期是默认的高效复习目标，但不是强化资格的硬阈值。`G` 只是派生的调度/评测代理量，不持久化，也不参与第二次强化计算。后续可在新策略版本中用实测校准替换 `p_success`，但不得静默改写已存 `H`。Importance 可以决定稀缺主动复习机会优先给谁，但不能改变该公式或直接改变 `H`。

更新按目标串行且幂等，把 freshness 恢复为一；然后由带版本的 Lifecycle 策略决定是否重新激活非 superseded 归档记录。收据按事件时间重放；强化资格按 `event.occurred_at` 时的状态计算，因此维护时机不能改变结果。收据时间统一使用权威 UTC：超过有界未来时钟偏差的事件直接拒绝，小幅负读取时差钳制到零；缺少原始发生时间时不能用处理时间代替。失败召回且没有权威反馈时，`H` 和强化锚点都不变。失败召回后获得权威再暴露属于重新学习：写入新 Episode/Evidence，使用正常写侧身份解析器对 archived/forgotten 指纹做有界查找——不是普通 Recall，也不是第二个 Retriever——复用已解析的 Node/Assertion 身份，将 `H` 设为 `max(当前 H, 新解析 H0)` 并重置锚点，但不应用成功召回倍数。现实世界中重复发生的事件是新 Episode，不是改写旧 Episode。纠正走带来源的 Evidence/冲突路径，可以在降低 confidence 的同时恢复清晰度；superseded Assertion 必须有带来源的撤销才能重新激活，不能因为再次被提到就自动复活。

#### 2.3.3 confidence

`confidence`（`C`）只存在于 Node 和 Assertion。Node 的值表示身份解析可靠性，Assertion 的值表示命题可靠性。Episode 保留明确的归因和来源，但没有 confidence 分数。时间、重要性、召回和 Retention 强化都不改变 `C`。

策略依据完整的唯一 Evidence 集合重算 `C`，而不是按到达顺序增减：

```text
C = (prior_weight * initial_confidence + sum(support_weight))
    / (prior_weight + sum(support_weight) + sum(conflict_weight))
```

Evidence 权重来自带版本的来源策略；重复 ID 不计数。相关来源共享 `independence_key`，同一个 `(independence_key, stance)` 组只采用最高来源权重，而支持和冲突仍是不同立场；`context` Evidence 不改变 `C`。Assertion confidence 使用自身 `assertion_evidence`；Node confidence 使用别名、描述和提及所关联的唯一、有来源身份观测，永远不接收相邻 Assertion 传播来的分数。纠正时保留旧的低可信/superseded Assertion，创建修正后的 Assertion 并连接历史。新冲突 Evidence 可以在强化 Retention 的同时降低 confidence；清楚记得旧信念不等于它是真的。

每个 Node/Assertion 的带来源准入会建立不可变的 `initial_confidence`、`prior_weight` 和 confidence 策略版本元数据；它们只是重放输入，不是额外动态分数。创建来源已经由该先验表示，不能再次进入 support 总和。Genesis 可以提供经过批准的初始 confidence；普通运行时准入的先验由固定来源可靠性类别给出，模型不能提交任意浮点值。策略升级必须显式带版本重算，不能在重开数据库时静默改分。

#### 2.3.4 Lifecycle eligibility（不新增分数）

时间和 `H` 产生 `F`，`F` 驱动 Lifecycle eligibility。带版本的 Lifecycle 策略独占压缩、归档和遗忘阈值；强化不含这些阈值，Recall 只消费生命周期状态，不重新定义阈值。Lifecycle 不降低 `F`，也不改变 `I`、`H` 或 `C`。子级别名、描述和提及跟随父记录/来源依赖。设计不持久化 freshness 或综合召回分数。

#### 2.3.5 detail level

`detail_level` 只表示 Episode 内容细度：`full`、`compressed` 或 `digest`。Episode 的 `lifecycle` 表示 `active`、`archived` 或 `forgotten`。归档是状态转换，不是第四种内容细度；归档的 Episode 仍可保留 full、compressed 或 digest 表示。Assertion lifecycle 可以是 `active`、`superseded`、`archived` 或 `forgotten`，但维护不能删除它的最后可审计 Evidence。历史 `life_stage` 表示经历发生时精灵所处的成长阶段；`temporal_label` 表示相对时期（例如 `before_arrival`）。二者都不是 `Lifecycle Stage`、`lifecycle` 或 `detail_level`。对 Node 而言，身份可用性由 `status` 和合并状态控制；维护可以归档低鲜度 Node，但不能改变它的重要性，也不能删除仍被 Assertion 引用的规范 Node。

## 3. 运行流程

```text
一次性 Genesis
ApprovedSeedSource ──► Genesis manifest
                         └─ 每次 submission：原子提交 ──► 本次 Memory 输出 + 完成标记

普通运行时
Workspace 闭合 ClosedEpisode ── 捕获事务 ──► 完整 Episode + 来源引用
                                               │
                                               ▼
                                        Memory Maintenance
                                        ├─ Consolidation Stage
                                        │  Episode ► 图谱投影 + 分数更新
                                        └─ Lifecycle Stage
                                           到期记录 ► freshness 驱动的细节/生命周期策略

Episodes + Nodes + Assertions + Evidence ──► Hybrid Recall ──► 有界 RecallBundle
```

Genesis 是一次性的侧入口。普通路径不会从不完整事件写入图谱事实，捕获也不会等待维护。

### 3.1 Genesis 初始化

`ApprovedSeedSource` 不可变、有版本并带哈希。Genesis manifest 只有三类种子：`KnowledgeSeed[]`（已掌握的世界/知识）、`EpisodeSeed[]`（个体过去，每条都物化为完整 Episode）和 `RelationshipSeed[]`（关联 Episode 或种子 Evidence 的类型化关系 Assertion）。不存在第四类传记或关系记忆：传记就是 Episode 的物化，关系就是 RelationshipSeed 的投影。世界/知识与关系种子可以直接投影；每条 `EpisodeSeed` 必须保留为完整 Episode，也可以在同一完整包内投影其派生 Node/Assertion。所有输出都带种子 Evidence。

Genesis 使用“单次提交”完成合同。一次 Genesis submission 是调用方交给 Memory、准备在一次原子提交中写入的完整、不可变 Memory 输出集合。Genesis 可以调用 Memory 任意多次；提交次数、大小、顺序、分组、调度以及这些提交代表核心知识还是扩展知识、前台还是夜间任务，都由 Genesis 决定，Memory 不负责决定。即使多个 submission 属于同一次更高层 Genesis 操作，每个 submission 也必须有自己的稳定提交/幂等身份和内容哈希。

对于一次有效 submission，所有预期的权威记录和子记录——Node、Assertion、Evidence、传记 Episode、别名、描述和提及——以及本次 submission 的完成标记，必须作为一个完整单元持久化并可见。原子性就是“只接受当前提交”：写入前完成校验；Unit of Work 要么提交所有输出和标记，要么一个都不提交。失败调用只能返回失败或可重试结果，绝不能返回 `committed`。相同 submission 身份和哈希重放必须幂等；同一身份换用不同哈希必须拒绝。后续 submission 失败不能回滚先前已经成功提交的 submission。

Genesis 调用方负责批次划分、顺序、重试时机以及何时发布领养结果。Memory 只向读取和维护暴露已经提交的 submission，不报告整个 Genesis 操作是否完成。已提交的 Elfie 不能被不同 manifest 静默重新初始化；升级是另一个经批准的操作。跨所有者领养发布由其自身契约定义，本文不假装存在跨存储的单一事务。Genesis 接受显式的 Episode/Node/Assertion 初始 `importance` 和 Node/Assertion `confidence`；它的授权准入统一选择 `genesis` profile，使 Genesis 产生的每条语义记录都获得 `retention_profile=genesis` 和 `half_life_days=3650`。它不模拟对话，也不靠情绪强度制造重要性。普通运行时调用方禁止直接投影图谱。

Genesis 对每只 Elfie 的准入按串行方式执行。完成标记是 Genesis 行的唯一可见性闸门：标记出现前，读取和维护都不能使用该 submission 的任何行。Genesis 可以接受只包含部分批准种子类别的一次完整 submission，不要求每次 submission 都包含所有种子类别，也不会推断调用方的批次策略。

### 3.2 普通运行时写入

上游 Workspace 闭合并校验事件，然后提供完整 `ClosedEpisode`。捕获事务写入 Episode、幂等键、来源引用和内容哈希。它不调用模型，也不从不完整内容更新 Node/Assertion。图谱 Evidence 关联和投影延后到 Consolidation Stage；文本投影可重建，不是第二个事实源。

### 3.3 Memory Maintenance

Memory Maintenance 是一个有界操作，可以持续小批量运行，也可以利用空闲/睡眠时间追赶。它有两个有序阶段和一套预算规则。检查点、租约和重试次数属于权威 Memory 事实记录之外的运行控制状态；它们不是语义记忆类型、可召回队列或第二个事实源。

#### 3.3.1 Consolidation Stage

处理针对当前来源版本/内容哈希尚无成功投影（包括之前尝试失败）的完整 Episode：

1. 从来源中抽取事件、提及、概念和候选 Claim；
2. 处理别名、共指和实体身份；
3. 归一化谓词，选择关系或 Claim Node；
4. 合并相容 Assertion，保留独立 Evidence 并记录冲突；
5. 根据唯一 Evidence 重算 Node/Assertion `confidence`，只产生合格、带来源的 importance 事件，并且只强化被新独立 Evidence 直接再次涉及的准确记录；
6. 提交投影并记录成功的来源/投影修订号。

谓词来自有版本的词汇表。未知谓词在校验前只能保持为未解析候选，不能静默提升为事实。

模型可以在写事务外提出抽取、消歧或摘要建议。确定性代码校验片段、类型、作用域、谓词、ID、Evidence 和版本，并执行最终写入。没有模型时，Episode 捕获和 FTS 仍可用，语义投影等待后续尝试；不能退化成关键词准入，也不能把无来源事实作为回退。

#### 3.3.2 Lifecycle Stage

对任何 `lifecycle` 为 active 的 Episode/Assertion，或 `status` 为 active 且没有规范合并目标的 Node，只要派生 freshness 到达阈值，就执行第 6.3 节带版本的转换，不受捕获日期限制，并且不修改 `importance`、`retention_profile`、`half_life_days`、`confidence` 或 `last_reinforced_at`。这些阈值是 Lifecycle 运行参数，不是强化或 Recall 常量。

当前来源版本没有成功投影的 Episode 必须保留足够完整来源。自动遗忘只做逻辑标记并保留最小 digest、哈希和来源链；物理删除不属于 `memory.v3`。低 confidence 不是删除理由。旧记录由计算出的 `next_review_at` 发现，单条不安全目标不会阻塞其他有界记录。

### 3.4 Hybrid Recall

召回热路径是确定的、由索引驱动的，不要求调用模型。

#### 3.4.1 Basic / Text Search

词法/全文搜索（以及可选的向量索引）用于查找精确名称、别名、罕见词、原始措辞、详细故事和来源/媒体引用。它覆盖尚未规范化到图谱中的细节。

#### 3.4.2 Local / Graph Search

从文本命中或提供的 Node/Claim ID 开始，沿有界的带类型路径扩展到相关人物、地点、概念、情绪、事件和支撑 Episode。遍历维护已访问集合，同一路径不重复访问同一 Node，并返回明确路径；跳数、邻居数和结果数都是硬上限。人物、时间、地点、历史情绪、主题和原因条件只约束或排序同一批有来源候选。

#### 3.4.3 Global Search（后续能力）

全局主题或社区搜索等图谱密集能力推迟到图谱积累了代表性密度之后。所有摘要都必须能回溯到 Assertion 和 Episode，不能成为新的事实源。

#### 3.4.4 RecallBundle

最小路径是 Basic/Text → 种子 Node/Episode → 有界 Local/Graph 扩展 → 来源 Episode/Evidence 获取。排序前先执行隐私和 namespace 过滤。第一轮 Recall 只使用 active 记录；只有该有界检索不足、查询明确要求历史材料，或存在精确稳定 ID/高相关来源指纹时，独立限额的归档通道才能返回 archived 记录，并且不占用 active 通道配额。查询相关性 `R` 综合文本/语义匹配、路径及请求的时间/facet；Memory 再派生 `A=.65F+.35I`。在任一状态通道内，Node/Assertion 使用 `R*A*(.25+.75C)`，没有 confidence 的 Episode 使用 `R*A`；superseded/冲突 Assertion 进入独立的 `R*A` 通道，避免低 confidence 隐藏历史。每种记录及状态通道各有自己的有界配额和稳定 ID 决胜规则；`H` 已经决定 `F`，不能重复计分。单纯命中不构成强化；只有合格的成功结果才能重新激活并巩固 archived 记录。

### 3.5 延期的 Memory Abstraction Loop

本能力当前明确不实现。未来必须一次交付完整闭环：

```text
Node + Assertion → 夜间图上聚合 → 模型提案 + 确定性校验
                 → Pattern 知识 Node → 按场景召回 → Reasoning 应用
                 → 结果反馈
```

聚合从图中已有的相关 Node 和带来源 Assertion 出发；Episode 只用于核验来源链和原始语境，不作为主要聚类面。它是 Consolidation Stage 的未来扩展，不新增第三个 Memory Maintenance 阶段或另一维护入口。通过校验的 Pattern 是可复用的 Claim/知识 Node，包含规范化规律、适用条件和限制/反例。其推导必须保留对支撑 Node、Assertion 或下层 Pattern 及底层 Evidence 的引用；具体物理表示随该能力一并设计。

不得只生成 Pattern。相同的端到端切片还必须接收事实所有者提供的类型化当前场景特征，通过直接匹配或向上图遍历召回适用 Pattern，在 `RecallBundle` 中完整保留规律、条件、反例和来源链，由 Reasoning 判断是否应用，并把结果写成新的 Episode，供后续强化、反驳或收窄 Pattern。上述路径及评测未同时完成前，Memory 不宣称支持 Pattern 抽象。

## 4. 类型化接口契约

本节固定语义输入、输出和保证，不固定编程语言的方法名。具体方法名可以在实现中调整，并记录在代码和一致性台账中。

### 4.1 Episode 写入

输入是完整 `ClosedEpisode`，包含稳定 ID 或幂等键、发生时间范围、文本/媒体、归因、来源引用和哈希。哈希覆盖完整持久化来源载荷及其引用的来源版本，不覆盖摘要或派生投影。输出是包含持久 Episode ID 与状态的回执。操作必须原子且幂等，不能从部分内容生成图谱事实。

### 4.2 Recall

`RecallRequest` 可以指定文本、种子 Node/Claim ID、节点类型、关系白名单、时间范围、人物/地点/历史情绪/主题/原因条件、检索模式和数量限制；不能携带 SQL 或图查询语言。

Memory Port 绑定单只 Elfie 的命名空间；请求不能扩大这个作用域。

默认硬上限为：20 个词法命中、8 个种子 Node、2 跳图遍历、每个扩展 Node 12 个邻居、40 个 Node、80 个 Assertion、8 个 Episode、24 条 Evidence 和 12,000 个渲染字符。调用方可以请求更低上限，不能突破 Memory 上限。

输出是有界的 `RecallBundle`：

```text
RecallBundle {
  focus_nodes: [{id, type, label, description, relevance,
                 importance, freshness, confidence}],
  assertions: [{id, subject, predicate, object, qualifiers, status,
                relevance, importance, freshness, confidence, evidence_ids}],
  paths: [{node_ids, assertion_ids, hop_count}],
  episodes: [{id, time_range, life_stage, temporal_label, excerpt,
              detail_level, relevance, importance, freshness, source_event_ids}],
  evidence: [{id, source_type, source_id, source_version,
              span_or_locator, stance}],
  conflicts: [{assertion_ids, reason}],
  limits: {requested, returned, truncated}
}
```

图谱提供结构，Episode 提供细节，Evidence 提供依据，使用它的上层负责组织叙述。

### 4.3 合格使用与结果反馈

已完成的回答、行动或叙事首先只能记录有界使用提案，其中包含发生时间、准确 Memory 记录 ID，以及这些记录所支撑的 claim/行动/叙事片段。模型返回的引用只是提案：确定性代码只接受本轮实际提供、绑定同一 Elfie 命名空间和 Recall context revision 的 ID，并限制每个结果的数量。使用提案不是强化事件。

只有出现权威结果后才能发出类型化强化收据：用户明确确认、确定性行动成功、主动复习完成或新的独立 Evidence。收据包含稳定事件 ID、原始使用/复习发生时间、准确目标、结果种类以及持久结果/来源引用。模型不能证明自己的成功。拒绝、失败或结果未知不产生通用强化；纠正可以改为产生冲突 Evidence。

权威结果必须先提交，再投递反馈。Memory 原子且幂等地消费收据；稳定事件 ID 保证结果存储与 Memory 之间崩溃后可以重试而不会重复强化。收据只强化准确的已接受目标，永远不强化图邻居。

### 4.4 Memory Maintenance

输入是有界批次/时间预算和运行控制用的维护检查点。操作先执行 Consolidation Stage，再执行 Lifecycle Stage；只提交经过校验、带来源的变更；失败信息写入运行控制状态且不能丢失 Episode；输出数量、检查点和状态。若使用模型，推理必须在写事务外完成，模型永远不是最终事实的权威。

### 4.5 来源查看

经过授权的 Memory 调用方和诊断工具可以按稳定 ID 有界读取一个 Episode 或 Evidence，包括来源内容、细节状态和来源链。查看是只读操作，不会隐式变成聊天历史或 Profile 读取。

### 4.6 幂等、失败和预算约束

每次写入都有稳定幂等键或指纹。Unit of Work 必须短小，使用一个串行化 SQLite 写入者，并且不能等待模型、网络、设备或世界运行时。租约/检查点使中断的维护可重试；失败不会破坏来源内容和 Evidence。召回必须限制文本命中数、图跳数/邻居数、返回的 Assertion/Episode/Evidence 数和渲染字符数，并明确报告截断。

## 5. SQLite 物理实现

### 5.1 权威事实表

SQLite 是第一种物理实现。一个 Memory Adapter/数据库只绑定一只 Elfie 的命名空间，调用方不能查询其他 Elfie 的行。下列表保存权威事实；JSON 列只存有界元数据，不能隐藏图边或来源链。

| 表 | 必须承担的职责 |
| --- | --- |
| `episodes` | 完整来源内容、发生时间范围（未知时可为空）及精度、历史 `life_stage`/`temporal_label`、独立写入时间、带归因的上下文/媒体/来源引用、隐私范围和版本、`importance`、`retention_profile`、`half_life_days`、强化/生命周期元数据、`detail_level`、`lifecycle`、成功投影标记、幂等键和内容哈希。Episode 没有 confidence 列。 |
| `nodes` | 规范身份、类型/名称、作用域/状态、有界摘要、`importance`、`retention_profile`、`half_life_days`、`confidence`、不可变 confidence 先验/策略来源、强化/生命周期元数据和合并指针。 |
| `node_aliases` | 多条带作用域的别名及其来源和可信度。 |
| `node_descriptions` | 多条按语言/种类区分的描述、内容哈希和来源关联。 |
| `episode_mentions` | Episode 到 Node 的提及、角色/片段以及已解析/歧义/未解析状态。 |
| `assertions` | 主体、谓词、Node 或显式带类型的字面量对象（type/value/unit）、限定信息、极性、认识状态、视角/上下文、有效期、`importance`、`retention_profile`、`half_life_days`、`confidence`、不可变 confidence 先验/策略来源、强化/生命周期元数据、冲突组、生命周期状态和指纹。 |
| `evidence` | Episode 或种子来源的定位、来源版本、摘录/媒体片段、模态、说话者/视角、捕获时间、`independence_key`、来源可靠性类别/策略版本和抽取元数据。 |
| `assertion_evidence` | Assertion/Evidence 多对多立场：`supports`、`contradicts` 或 `context`。 |
| 分数事件收据 | Adapter 私有、不可召回、带来源的 importance 及合格使用/retention 事件，用于幂等、聚合和按事件时间重放；它是权威策略输入/审计状态，不是语义记忆类型，也不是被记住命题的第二来源。 |

每次 Genesis submission 的 ID/版本/哈希及完成标记是 Memory Adapter 所有的持久化包元数据，不是语义 Node/Assertion，也不是重试队列。完成标记位于同一个 Memory SQLite 数据库中，并与本次 submission 在同一事务提交；其物理元数据记录/表名由 Adapter 私有决定，不增加语义记忆表。只有所有预期 Memory 行（包括子记录）准备好并完成本次提交后才能写入完成标记。每条 Genesis 产出的行都带有 submission 身份；缺少对应完成标记的行对读取者不可见。可重试或中断的 submission 不是已初始化的 Memory，不能被召回；它的运行控制状态可以从不可变输入重建。完成标记记录（或校验）每类输出的预期 ID/数量，使对账不只检查 Node 是否存在。派生的 FTS/向量索引和内存缓存不属于事实包完成检查，只能在完整提交后重建。这些记录不形成第二个可变事实源。`importance` 和 Node/Assertion `confidence` 是语义分数；`retention_profile` 和 `half_life_days` 是持久策略状态，freshness 和查询 rank 只派生。Evidence 行及其立场仍是权威支持记录。

### 5.2 派生索引和缓存

`episodes_fts` 和 `nodes_fts` 是可重建的全文投影，覆盖来源文本、摘要、名称、别名和带来源描述。向量索引（若启用）属于后续优化，不是首版前置条件，同样是派生物。必需查询索引覆盖 lifecycle/status 与 `next_review_at`、Episode 成功投影修订/时间/哈希、Node 规范名称/类型/状态、别名、描述、按 Node/Episode 的提及、Assertion 两端、冲突/替代、Evidence 来源/independence key、`assertion_evidence` 两个方向及唯一分数事件收据。Recall 先获得有界索引候选集，只对候选派生 freshness/rank，不能扫描全库计算。运行租约、重试次数和检查点是有界控制状态，不返回 Recall。非空成功投影修订号仍绑定 Episode 来源版本/内容哈希。每个索引都服务于有界查询并声明重建来源；首版继续使用内嵌关系库，不以专用图数据库为前置条件。

分数收据也必须控制运行增长。在带版本的迟到安全窗口内保留可完整重放的收据；当来源 Outcome/Evidence 已持久化、目标水位之前的本地 outbox 事件全部结算且安全窗口结束后，importance 收据压成每方向/窗口最高类别，reinforcement 收据折成保留策略版本、折叠状态、事件数量/哈希和最后事件时间的检查点。早于已结算水位的收据进入可观察的 reconciliation 状态并被拒绝，不能静默改分或改用处理时间。该压缩只作用于评分控制收据，不作用于语义 Episode、Evidence 或冲突历史。

内存只保留有界的热点 Node、邻接页、近期邻域和索引页。缓存未命中时重新读取持久行，不等于记忆丢失；媒体按需加载。

### 5.3 约束、唯一性和冲突保留

启用外键，默认限制删除。Episode 幂等键和内容哈希防止重复捕获。Assertion 指纹包含规范化主体、谓词、对象、限定信息、极性、视角和有效期，不会把不同时间、视角或冲突折叠成一条。Evidence 身份还必须包含来源版本、模态和定位/片段；同一定位在新来源版本中是不同的来源关联。完全重放必须幂等。

别名在不同作用域中可以有歧义。提及可以保持未解析。描述按 Node/语言/种类/内容哈希去重，同时保留不同来源版本。一个 Assertion 必须且只能有一个 Node 对象或一个带类型字面量对象。需要查询的 Assertion 字段和限定信息使用列或明确建立索引的子记录；带类型字面量使用互斥的 Node ID 或类型/值/单位字段，有界 JSON 只能存不可查询元数据。Node 合并保留旧 ID，并通过 `merged_into` 指向规范 ID。不能用简单的三元组唯一键覆盖证据或分歧。

### 5.4 事务和 Unit of Work

Genesis 按第 3.1 节的完成保证执行：先校验一次完整 submission，再打开限定在本次 submission 范围内的事务，在同一提交中写入全部 Memory 输出（Node、Assertion、Evidence、Episode 及其子记录）和本次标记，并在对账确认完整集合后才返回成功。提交失败不构成完成状态；同一不可变 submission 保持未发布，并可使用相同身份和哈希重试。此前成功的 submission 不因后续失败回滚。普通捕获把完整 Episode 和来源引用一起提交；其派生文本索引可以在同一事务更新，也可以在提交后重建。维护在事务外校验模型提案，再在一个短 Unit of Work 中提交图谱变更、Evidence 关联、分数更新、生命周期和成功投影修订号；派生索引只能在事实提交成功后更新或重建，不能决定事实包是否完成。事务内不能调用模型或网络。

SQLite 使用 `PRAGMA user_version`、外键、WAL、有界忙等待和一个串行化写入者。派生索引必须能从权威表确定性重建。

### 5.5 重启恢复

Episodes、Nodes、Assertions 和 Evidence 在重启后仍存在。维护以运行控制用的租约/检查点处理有界记录；过期租约可以重新处理。普通提交前崩溃保持来源不变；提交后崩溃通过幂等键/指纹识别。Genesis 在某次 submission 提交前崩溃不会形成可接受的该次初始化结果；恢复时检查相同不可变 submission 身份/哈希，并重试该 submission。只有全部预期输出、子记录和本次完成标记都存在时，`committed` 状态才有效。缺失的 FTS 和内存缓存可以重建。

## 6. 生命周期、恢复和全新库策略

### 6.1 Episode 细节生命周期

生命周期是已经存储记录的细节与可用状态，不是新的记忆类型。到期扫描同时覆盖新旧记录。`next_review_at` 是下一个 freshness 阈值预计被墙钟时间穿越的时刻，`H` 变化时重新计算，因此维护频率不能改变 freshness。穿越阈值只会产生待维护工作，不会隐式改状态；Recall 在有界且可观测的维护事务推进前，只能看到最后已提交状态。Lifecycle 消费派生 `F`，但不更新 `I`、`H`、`C` 或强化锚点。当前来源版本没有成功投影的 Episode 必须保留足够完整来源；已投影 Episode 的细节可以从 `full` 变为 `compressed` 或 `digest`，归档是独立可用状态。两种变化都必须通过来源和图谱依赖检查。

### 6.2 来源证据保护

作为某个 active Assertion 最后一条可审计来源的 Evidence 不能删除。压缩可以缩短 Episode 的展示细节，但必须保留哈希以及足以追溯 Assertion 的摘录、定位或摘要存根。种子来源及其版本保持不可变。任何破坏性删除都必须显式、开发期间可恢复，并按 ID 报告。主人明确纠正时，写入新的带来源 Episode/Assertion，并可将旧 Assertion 标记为 superseded；不能原地改写历史来源。

### 6.3 压缩、归档、摘要存根和遗忘

`memory.v3` 初版 Lifecycle 策略是：

| 到期条件 | 一次提交的转换 |
| --- | --- |
| `F <= .40` | 符合条件且已投影 Episode：`full → compressed` |
| `F <= .20` | 符合条件且已投影 Episode：`compressed → digest` |
| `F < .10` | 符合条件的 active 记录：`active → archived` |
| `F <= .01`、`I <= .10`、已归档至少 90 天且依赖安全 | `archived → forgotten` |

这些数值是带版本的运行参数，不是人类记忆常量。一个事务对每个目标最多推进一个生命周期阶段。当前投影未成功的 Episode 继续保留来源。遗忘保留最小 digest、哈希、来源链、稳定语义/来源指纹，以及有界写侧身份解析和带来源重学所需的 `retention_profile`、`H` 与锚点；它不删除最后一条可审计 Evidence。合格的成功回忆可强化归档记录，并让 Lifecycle 重新激活它，但重新激活不会恢复已丢弃的细节。回忆失败后的权威重新暴露是新的带来源重学事件：至少保留原 `H`，可接受重新解析出的更高 `H0`，但不使用成功回忆倍数。现实世界再次发生的事件写成新 Episode。

### 6.4 0.x 全新库策略

在 0.5 的数据兼容基线冻结前，Memory 只支持由当前 schema 创建的全新数据库。发现旧版或混合数据库时，必须在任何业务写入前拒绝。运行时不导入、不重放、不双写，也不回退读取旧 Memory 数据。操作者可以先备份精确的数据根再显式重建；应用程序不得自动删除或覆盖旧数据库。

因此，旧的 `entities`、`events`、`entity_edges` 及相关表按策略废弃，而不是在原文件上转换。reset-required 结果必须指出数据库路径，并保证被拒绝文件保持不变。全新初始化只创建当前的 Episode、图谱、Evidence 和运行控制表。

## 7. 不可破坏的不变量

1. 运行时内容在抽取前完整存在于 Episode；Genesis 内容在投影前完整存在于批准来源。
2. 每个持久 Assertion 都有 Episode 或种子 Evidence；模型输出本身永远不是事实。
3. 规范化合并身份，不合并相互矛盾的视角或无关实体。
4. 冲突 Assertion 保留极性、时间、视角和来源。
5. 图谱摘要、向量和分数没有明确认识状态时不能越过来源依据。
6. Episode 是详细的历史线；图谱是它的结构化语义投影。
7. 实时状态、计划、承诺、权限和行动由其所有者负责。
8. Memory 不直接读取 Profile、Communication 历史或世界运行时状态。
9. Genesis 直接投影只限批准的 submission，不能变成运行时 CRUD。

## 8. 验收和阶段门

每一轮实现只有在代码和可重放证据都具备时才能关闭。本目标设计本身不证明当前实现已经符合。

### 8.1 来源完整性

验证完整 Episode 捕获、内容哈希、幂等、Genesis submission 原子完成、重试和重启复开。门槛：100% 的验收夹具保留来源哈希，每个被接受的 submission 都达到包含全部预期子记录的完整完成标记，且看不到未提交 submission 的输出。

### 8.2 图谱来源链

验证提及解析、规范化、Assertion/Evidence 关联、Claim Node、独立描述和冲突保留。门槛：每个夹具 Assertion 都有可解析来源；无来源提案被拒绝。

### 8.3 混合检索

重放罕见词、关系网络、知识对象、情绪条件和时间限定经历。验证 Basic/Text 回退、有界 Local/Graph 路径、RecallBundle 来源链和明确截断。初始目标：罕见词 recall@5 ≥ 0.90，关系路径 precision = 1.00。

### 8.4 Importance、Retention、confidence 和冲突

验证目标上限式 importance 更新及 24 小时聚合、事件时间重放、检查点压缩等价性和水位前迟到事件拒绝、冻结 freshness 向量、强化倍数单调且满足 `M(1)=1`、`M(.5)=2`、`lim(F→0+)M(F)=3`、`2F(1-F)` 在 `.5` 取最大值、归档记录成功回忆后重新激活、失败回忆与带来源重学、与 Evidence 到达顺序无关的 Node/Assertion confidence、每个带版本 Lifecycle 边界，以及 Episode 不含 confidence。时间和 Lifecycle 不能修改 importance、retention 或 confidence；仅成为 active 或 archived Recall 候选不能强化；冲突 Evidence 仍可见，并可以通过带来源的重新评价恢复清晰度，同时降低 confidence。

### 8.5 性能和容量

测量两个维护阶段、有界内存、增长/保留行为，以及代表性 10,000 Episode / 50,000 Node / 200,000 Assertion 数据集上仅数据库 Basic + Local 的 p95 ≤ 150 ms。耐久性门还必须证明旧版或混合数据库会在不修改文件的情况下被拒绝，并且全新数据库能够重建和复开。

## 9. 已确定的实现决策

本节关闭审查中发现的实现歧义，是 Memory 实现的规范；但不会把 Genesis 的批次、顺序或调度分配给 Memory。

### 9.1 来源形态、命名空间和隐私

- Memory Adapter 按一只精灵的不可变 `elfie_id` 构造；每次读取、写入、维护和 Genesis submission 都校验该命名空间。调用方不能通过请求或原始 ID 扩大作用域。
- `occurred_from` 和 `occurred_to` 可以未知。使用显式的发生时间精度区分精确时刻、有界范围和未知时间；未知时间不能替换成伪造的 epoch，除非调用方明确请求未知时间 facet，否则不参与时间排序。
- Episode 的归因使用 `observed`、`told`、`inferred`、`felt` 四种类型。参与者、地点和物品通过带角色的有界 `episode_mentions` 表示；场景上下文保留为有界来源上下文，不能隐藏图谱边。
- 来源和媒体引用携带版本、定位和 hash。隐私范围由 Memory 边界强制执行，并进入来源检查和 Recall 过滤，不能从展示名称推断。
- 修正通过新的带来源 Episode/Assertion 表达，历史来源行及其版本不能原地修改。

### 9.2 分数、复查和生命周期

- `importance` 和 Node/Assertion `confidence` 是持久化语义分数；`retention_profile` 和 `half_life_days` 是持久策略状态。Episode 没有 confidence；freshness、按成功率加权的复习收益和综合召回 rank 只派生、不持久化。不再保留 `support_score`。
- Importance 根据幂等、带来源、已聚合的语义事件收据按事件时间折叠；confidence 根据全部唯一 Evidence/独立性组重算；成功使用的 Retention 根据幂等、按目标的合格结果/复习收据及 `H'=H*(3-2F)` 全局封顶公式折叠。回忆失败不变；权威重新暴露使用独立的带来源重学规则。重试或维护不能重复增加贡献。
- Episode、Node 和 Assertion 保存 `retention_profile`、`half_life_days`、强化/复查时间和策略版本。Lifecycle 独占带版本的压缩、归档和遗忘阈值。Recall 只消费 `active`/`archived`/`forgotten` 状态，并把 archived 结果放入独立限额通道；强化保持连续且无阈值。
- 生命周期转换受保护且按顺序执行：当前来源没有成功投影时先保留来源；再允许 `full` → `compressed` → `digest`，单独归档；只有通过 freshness、importance、驻留期和来源/Evidence 依赖检查后才能逻辑遗忘。遗忘不能删除 active Assertion 的最后可审计 Evidence。
- Consolidation 租约、重试次数、检查点和被拒绝的提案属于权威事实之外的运行控制数据。一个有界的 Memory Maintenance Unit of Work 拥有写事务；普通捕获和 Genesis submission 仍是独立操作。

### 9.3 投影和 predicate 校验

- Predicate 必须从带版本的 registry 解析，并显式登记别名和弃用项。每个成功投影记录 registry 版本。
- 未知或无效的模型提案只能保留为有界诊断/重试数据，不能插入为 active Assertion；registry 或来源校验改变后才可重试。
- 成功投影记录 `(source_version, source_hash, projection_revision)`。缺失或过期的修订表示当前来源仍需投影；重试不能创建第二个 Episode。
- 运行时调用方只使用 source-first 类型化路径。旧的 `add_edge`/裸边写入在调用方迁移后删除，不再是运行时或迁移 API。

### 9.4 Recall 语义

- Facet 是正向约束：不同 facet 类别之间使用 AND，同一类别内的值使用 OR；缺少 facet 信息不能变成负事实。历史情绪读取 Episode 的带归因来源，不能读取实时 Emotion 状态。
- 排序按记录种类确定：先派生查询相关性 `R` 和 freshness `F`，在各自 active 或 archived 通道内的合格 Node/Assertion 使用 `R*(.65F+.35I)*(.25+.75C)`，Episode 和冲突通道使用 `R*(.65F+.35I)`。结果按种类和状态分开并用稳定 ID 决胜；策略分量都有界且带版本。
- 优先返回 active Assertion，但相关的 `superseded` 和冲突 Assertion 仍保留，并明确返回状态和 Evidence。隐私与命名空间过滤在排序前完成。
- 初始模式只有 Basic/Text 和 Local/Graph。Global/community 与向量检索仍是后续的派生能力，初始契约不宣称支持。

### 9.5 全新 schema 和兼容边界

- Schema 变更使用全新的目标 schema 和显式版本检查。旧库或混合库必须在初始化修改它之前被拒绝；0.5 前不存在 importer、回退读取器或双写。
- reset-required 结果必须指出精确数据库路径，并指导操作者备份后显式重建数据根。应用程序不得自动删除、覆盖或静默修复被拒绝的数据库。
- 当前 schema 只包含 source-first Episode、Node、Assertion、Evidence 和运行控制表。旧实体/事件表、旧边、`support_score` 和 `source_type='legacy'` 都不是可接受输入。

### 9.6 验证和可观测性

- 每条写入路径都要覆盖提交点前后的故障注入，包括并发重复提交、哈希不匹配、重启、租约过期和未提交行不可见。
- Maintenance 和 Recall 测试覆盖幂等分数更新、来源保护、facet 语义、supersedes/冲突可见性、命名空间/隐私隔离和硬截断限制。全新库测试覆盖旧/混合 schema 不修改拒绝、新 schema 创建和复开。
- 性能证据记录冷/热初始化、每个 Unit of Work 耗时、SQLite 锁等待、行数、重试延迟和 Recall p95。现有代表性 Recall 目标仍为 p95 ≤ 150 ms；Genesis 是否分批由启动实测决定，不由本 Memory 契约决定。
- 每次 schema 或事务变更后，重新运行持久化盘点、聚焦的 Adapter/契约测试、质量检查和 `git diff --check`；并按 `target`、`inventory`、`references`、`verification`、`residuals` 更新 Conformance 台账。
