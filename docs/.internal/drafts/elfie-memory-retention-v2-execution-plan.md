# Elfie Memory Retention v2 执行计划

状态：**代码实现与确定性验收已完成；MEM-012 仍等待负责人体验确认及跨进程 Outcome/outbox 接入决策**
权威设计：[`docs/developer/designs/elfie-memory-architecture.md`](../../developer/designs/elfie/brain/elfie-memory-architecture.md)
符合性台账：[`MEM-012`](../../developer/conformance/elfie-memory.md)
适用范围：Memory 的重要性、保持、置信度、召回排序、生命周期及有效使用反馈

## 1. 目标与边界

本计划把 Memory 从当前 `memory.v1` 的“固定降低 importance + 固定复查周期”收敛到
Retention v2：

- `I = importance`：语义重要性，只由显式语义事件改变；
- `D = retention_days`：保持跨度，只由有效使用、复习、重新学习或新独立证据改变；
- `C = confidence`：事实可信度，只存在于 Node/Assertion，并由唯一证据重算；
- `F = freshness`：当前记忆清晰度，由时间、`D` 和强化锚点即时计算，不持久化；
- 召回同时使用查询相关性、`I`、`F` 和适用时的 `C`；
- `F` 驱动压缩、归档和逻辑遗忘，生命周期不得反向修改 `I/D/C/F`。

本计划不包含：

- Pattern/Abstraction 提取与应用闭环；该能力仍由 `OPT-005` 单独跟踪；
- 第二套 Retriever、第二套评分系统或新的记忆类型；
- 旧开发数据库迁移、兼容读取、双写或生产数据迁移；Schema 升级后显式重建开发库；
- 物理删除已遗忘记录；v2 只实现可审计的逻辑遗忘；
- 仅因候选、召回、放入 Prompt 或图邻居展开而强化记忆。

## 2. 冻结契约

### 2.1 保持与清晰度

```text
t = max(0, now - last_reinforced_at)
F = 1 / (1 + 9 * (t / D) ^ 2.6)
```

边界：`F(0)=1`、`F(D/2)≈0.4`、`F(D)=0.1`。`D` 的单位为天，不叫半衰期。

初值：

| 来源 | `D0` |
|---|---:|
| 瞬时普通经历 | 2 天 |
| 普通经历/知识 | 7 天 |
| 显著或重大经历 | 30 天 |
| Genesis 创建的 Episode/Node/Assertion | 3650 天 |

上限为 `Dmax=36500` 天。有效强化仅在 `F>=0.1` 时发生：

```text
q  = (1 - F) / 0.9
D' = min(Dmax, D * (1 + q^2))
last_reinforced_at' = occurred_at
```

`F<0.1` 后，旧 `D` 不再获得强化资格。重新学习必须写入新的 Episode/Evidence，复用适用的
语义 Node/Assertion 身份，并按新的 `D0` 重新起算。

### 2.2 重要性

```text
I' = I + eta * (T_I - I)
```

只有当目标方向与当前值一致时才应用：提高事件要求 `T_I>I`，降低事件要求 `T_I<I`。
模型只能提出事件等级，确定性策略拥有数值：

| 提高等级 | `T_I` | `eta` |
|---|---:|---:|
| routine | 0.35 | 0.10 |
| meaningful | 0.60 | 0.20 |
| major | 0.85 | 0.35 |
| core | 1.00 | 0.50 |

| 降低等级 | `T_I` | `eta` |
|---|---:|---:|
| ordinary | 0.30 | 0.25 |
| major | 0.10 | 0.50 |
| revoked | 0.00 | 1.00 |

同一 ClosedEpisode、目标、方向和等级只能生效一次。跨 Episode 时，提高/降低方向分别进入
按事件时间排列、由首个事件锚定的 24 小时窗口，每个方向/窗口只接受最高等级；相反方向仍按
事件时间依次生效。事件必须按 `(occurred_at, event_id)` 重放，且不得沿图传播。

### 2.3 置信度

Episode 没有 `confidence`。Node/Assertion 的 `C` 根据全部唯一 Evidence 重算：

```text
C = (prior_weight * initial_confidence + support_weight_sum)
    / (prior_weight + support_weight_sum + conflict_weight_sum)
```

相关副本共享 `independence_key`，同一 `(independence_key, stance)` 组只采用最高来源权重。
普通召回、上下文使用和时间经过不改变 `C`；
纠正保留低 `C`/`superseded` 的旧 Assertion，并创建有证据的新 Assertion。

### 2.4 召回与生命周期

```text
A = 0.65 * F + 0.35 * I
Q = 0.25 + 0.75 * C

Episode rank          = R * A
active Node/Assertion = R * A * Q
conflict/superseded   = R * A
```

`R` 是查询相关性。各类型使用独立配额，稳定 ID 作为最终并列项；不得把 `D` 重复计分。

生命周期阈值：

| 条件 | 动作 |
|---|---|
| `F<=0.4` | full → compressed |
| `F<=0.2` | compressed → digest |
| `F<0.1` | archived |
| `F<=0.01 AND I<=0.1 AND archived>=90d AND dependency-safe` | logical forgotten |

时间和 `D` 产生 `F`，`F` 触发生命周期动作；生命周期只改变详情层级或状态。

## 3. 当前代码差距

实现已按本计划收敛，当前事实与剩余边界如下：

| 区域 | 当前事实 | 剩余项 |
|---|---|---|
| `score_policy.py` | `memory.v2` 已统一实现 `I/D/C/F`、公式、事件窗口、证据重算、边界校验和重放。 | 参数若要调整必须升策略版本并重跑评测。 |
| `schema.py` | fresh-store Schema v6 已包含三类记录的 `retention_days`/锚点、独立 Evidence、事件/回执/检查点和 reconciliation；旧库显式拒绝。 | 不迁移旧库；用户需备份后显式重建。 |
| 写入与 Graph | Episode→Evidence→Node/Assertion 投影、Genesis 十年准入、纠正历史、独立证据和乱序/幂等重放已实现；Node 不再接收关系证据评分。 | Pattern/Abstraction Loop 保持 OPT-005 deferred。 |
| Recall | 统一派生 `F`，按 `R/I/F/C` 与类型配额排序，保留情绪/主题/因果/关系/时间/隐私过滤。 | Global/community、向量检索仍是后续投影。 |
| Lifecycle/Maintenance | Consolidation→Lifecycle 有序闭环、历史到期扫描、租约/检查点/重启恢复、`F` 阈值压缩/归档/逻辑遗忘已实现；Lifecycle 不改 `I/D/C/锚点`。 | 更换策略或 Schema 后需重跑 OPT-003。 |
| Reasoning 反馈 | RecallBundle、稳定记忆 ID、allow-list、`MemoryUseProposal` 和幂等 `QualifiedReinforcementReceipt` 已接入；普通召回/回答/失败不强化。 | 当前 proposal 暂存于 MemorySystem 内存；跨进程 Outcome/outbox 的持久化与重启补投由上层结果源决定，仓库暂无独立 Outcome store。 |
| Genesis/调用方 | Genesis 每次提交原子且幂等、可分批；Memory 不管理批次；Lab/诊断/生产路径已迁移 typed API，退役模块/引用为零。 | 不执行生产数据迁移；需继续保持 fresh-store 策略。 |
| 评测 | 受影响测试、架构门禁、持久化扫描、真实 Ark 单场景和刷新后的 OPT-003 已完成。 | 真实 Ark 报告 promotion 仍等待负责人对匿名样本的体验确认。 |

## 4. 实施原则

1. 先建立失败测试和纯策略，再改 Schema 与持久化；不得边实现边改变公式。
2. 所有分数更新由一个版本化确定性策略拥有；模型只能输出受限枚举和证据内容。
3. 持久化当前物化值，同时保留足够事件来源以支持幂等、乱序重放和审计。
4. “使用成功”是业务事实，不用文本相似度猜测；失败、放弃、仅召回均不强化。
5. 单库事务内原子；跨 Brain Journal 与 Memory 不虚构分布式原子性，采用结果先落账、幂等回执重试。
6. 每个阶段交付可独立重放的垂直切片；未达到退出条件不得进入大规模评测。

## 5. 分阶段执行

### Phase 0：冻结基线与影响清单

改动：

- 以权威设计和 `MEM-012` 为唯一目标；`MEM-011` 只保留为已实现 v1 的历史证据。
- 固定受影响调用链：准入、Consolidation、Evidence、Recall、Reasoning、Lifecycle、Genesis、Lab。
- 记录现有测试入口和 OPT-003 基准，禁止用删除旧断言来消除新契约冲突。

退出条件：目标公式、边界、排除项与中英文设计一致；影响文件和消费者无未分类路径。

### Phase 1：实现纯 Retention v2 策略和黄金向量

主要文件：

- `elfie/brain/memory/score_policy.py`
- `test/elfie/brain/memory/test_score_policy.py`

先写失败测试：

- `F` 在 `0`、`D/2`、`D`、未来时间戳和极大时间差上的数值；
- `F=1/0.4/0.1` 的强化结果、`Dmax` 封顶及 `F<0.1` 拒绝强化；
- 情绪/感官显著性只能选择 30 天准入档，不能隐式改变 `I/C`，相似情绪召回不能强化；
- `I` 提高、降低、饱和、24 小时聚合、重复事件和乱序事件；
- `C` 对 Evidence 到达顺序不敏感，同 `independence_key` 不重复计数；
- 生命周期边界采用明确的不等号：`F=0.1` 仍可强化，`F<0.1` 归档；
- Episode 类型在编译/运行契约上均无 `confidence`。

黄金值固定为：`F(D/2)=0.402504156`、`F(D)=0.1`；`F=.4/.2/.1/.01` 的到期时间分别为
`0.502008485D/0.732057485D/1D/2.514986442D`；在 `F=1/.4/.1` 强化时，`D` 倍数分别为
`1/1.444444444/2`。测试采用明确容差，不以格式化字符串比较浮点数。

实现：

- 将 `MemoryScorePolicy` 收敛为 `memory.v2` 下的纯函数/不可变结果，不建立平行策略类；
- 时间计算统一使用 UTC，小幅负读取时差钳制到零，超过固定未来时钟偏差的写事件拒绝；缺少
  原始发生时间的使用反馈不允许退化成处理时间；所有输入输出做有限数和范围校验；
- 来源可靠性使用少量固定枚举映射先验/权重，模型不得提交任意浮点权重；
- Genesis 显式 `C` 成为不可变准入先验；创建来源不能同时再次进入 support 和，避免重复计数；
  运行期物化 `C` 由准入先验和后续 Evidence 重算。

退出条件：黄金向量通过；函数无数据库、模型、当前时钟隐式依赖，`now` 均由调用方传入。

### Phase 2：升级类型和 fresh-store Schema

主要文件：

- `elfie/brain/memory/memory_records.py`
- `infrastructure/persistence/memory/schema.py`
- 对应 Schema、Repository 和类型契约测试

Schema v6：

- Episode、Node、Assertion 新增非空 `retention_days`、`last_reinforced_at`、
  `lifecycle_changed_at`，并约束 `0<D<=36500`；
- Episode 继续没有 `confidence`；Node/Assertion 保留 `confidence`；
- Node/Assertion 增加 `archived` 状态，保留 Assertion 的 `superseded`；
- Evidence 新增非空 `independence_key` 和受限 `source_reliability_class`；
- Node/Assertion 保存不可变 `initial_confidence`、`prior_weight` 和 confidence policy version；
  它们只用于重放，不是新的动态分数；
- 增加适配器私有的 importance event 与 reinforcement receipt 表：包含 `event_id`、目标、
  方向/类别、`occurred_at`、来源、聚合窗口信息和 `policy_version`；窗口由事件时间首项锚定，
  不能使用会产生边界漏洞的自然日桶；准入事件与记录在同一事务写入；
- 建立目标+事件唯一约束、目标+发生时间重放索引及生命周期到期索引；
- 增加按目标的 score fold checkpoint/watermark 与有界 reconciliation 状态；它们是运行控制，
  不进入 Recall；
- 旧 v5 数据库明确拒绝启动并提示重建，不写 migration/fallback/dual-write。

类型：

- 创建输入不开放任意 `retention_days`，改用受限 `retention_class`；Genesis 使用专用来源；
- `RecallEpisode/Node/Assertion` 增加派生的数值 `freshness`，内部诊断可见 `retention_days`；
- 将现有 `MemoryStateSnapshot.freshness` 字符串状态迁为 `snapshot_freshness`，禁止把
  `current/stale/unknown` 当成记忆强度；
- 将 `MemoryContext.items` 收敛为可区分的 Episode 项（`R/I/F`，无 `C`）和 Node/Assertion 项
  （`R/I/F/C`）；删除会压扁或复制置信度语义的 `certainty=high/medium/low`；
- 增加类型化 `ImportanceEvent`、`MemoryUseProposal`、`QualifiedReinforcementReceipt` 和必须携带
  新 Episode/Evidence 的 `RelearningSubmission`；
- 所有事件拥有稳定 `event_id` 和明确 `occurred_at`。

退出条件：新库约束与索引测试通过；旧库拒绝路径可重放；不存在 Episode confidence；不产生兼容层。

### Phase 3：收敛写入、Evidence 和事件重放

主要文件：

- `infrastructure/persistence/memory/sqlite_episode_store.py`
- `infrastructure/persistence/memory/sqlite_graph_store.py`
- Memory Port 与组合根

实现：

- 准入事务同时写记录、初始 `I/D` 事件和正确的下一生命周期时间；
- 删除 `_apply_evidence_score` 的线性 `I` 增长和端点 Node 传播；
- Assertion 的 `C` 从唯一 Evidence 全量重算；Node 的 `C` 从有来源的名称、描述、提及等
  Node 自身证据重算，不借 Assertion 端点间接传播；
- 新的独立支持或冲突证据只强化它直接证明/反驳的目标；冲突可使 `D` 增加、`C` 降低；
- importance event 按 `(occurred_at,event_id)` 重放，24 小时窗仅保留最高有效等级；
- receipt 重复提交无副作用；同目标写入串行化，失败事务不留下半更新状态；
- 安全窗口内保留明细；来源已持久化、outbox 到水位已结算且窗口到期后，importance 事件压成
  每方向/窗口最高类别，reinforcement 折成带 policy version/count/hash 的检查点；水位之前迟到
  事件进入 reconciliation 并拒绝自动改分；
- 身份解析器用现有指纹/规范键有界查找 archived/forgotten 记录；重新学习写新 Episode/Evidence、
  重置准入 `D0` 并只激活非 superseded 目标，不建立第二套 Retriever；
- 任意物化值都能由准入事件和后续事件重建，并与当前行一致。

先写失败测试：重复、乱序、同窗多等级、跨窗、相关 Evidence、归档身份重学、superseded 不自动
复活、检查点前后重放、未结算 outbox 禁止压缩、水位前迟到诊断、事务故障注入、重启后重放。

退出条件：写入路径不再存在 `I-0.05`、Evidence→Importance 或图端点评分传播；重放结果与到达顺序无关。

### Phase 4：建立“实际使用 + 权威结果”反馈闭环

主要区域：

- `elfie/brain/reasoning/`
- Brain Journal/TurnOutcome
- Memory Port 的幂等权威结果/强化回执

实现一条端到端垂直切片：

1. MemoryContext 为提供给模型的每条记忆分配稳定、可引用的 record ID；
2. 推理结构化输出把采用过的 memory ID 绑定到具体 claim/行动/叙事片段；解码器只接受本轮
   提供集合的子集，并执行每个结果的数量上限；此时只写有界 use proposal；
3. 普通聊天回答完成不自动强化；只有后续用户明确确认、确定性校验通过、主动复习完成或新的
   独立 Evidence 才把 proposal 结算为 reinforcement receipt；模型不能自证成功；
4. 对工具/行动，只有执行成功回执能确认相应记忆被有效使用；失败/未知结果不结算；
5. 权威 Outcome/反馈来源先持久化，再提交 `QualifiedReinforcementReceipt`；失败重试依靠稳定
   event ID 幂等；
6. Memory 根据原始使用/复习发生时间计算当时 `F`，只对 `F>=0.1` 的目标更新 `D` 和锚点；
7. 候选生成、RecallBundle、Prompt 注入、模型未引用、未确认聊天回答、失败/取消结果全部不产生
   reinforcement receipt；纠正改走 contradicting Evidence。

安全约束：模型返回 ID 不是成功事实，回答完成也不是成功反馈；必须同时通过集合/绑定校验和
独立权威结果条件。

先写失败测试：模型伪造 ID、跨 Elfie ID、过期 Recall revision、仅召回、回答完成但未确认、
用户确认、用户否定/纠正、行动成功、结果失败/未知、回执重试、进程在 Outcome 和 Memory 之间
崩溃、重启补投、同回执重复消费。

退出条件：只有可审计的独立权威结果能强化；Memory 侧回执消费幂等且不会重复增大 `D`。
跨存储的 Outcome outbox 由结果所有者持久化并在重启后重放；当前仓库没有独立 Outcome store，
因此该跨进程门仍是外部集成验收项，不能用 MemorySystem 的进程内 proposal 缓存冒充完成。

### Phase 5：按冻结公式重做 Recall 排序

主要文件：

- `infrastructure/persistence/memory/sqlite_retrieval_store.py`
- `infrastructure/persistence/memory/sqlite_graph_store.py`
- `elfie/brain/reasoning/memory_context.py`

实现：

- 每个 Recall 请求只取一次 `now`，统一计算所有候选的 `F`；
- 先用全文、实体、关系、情绪、感官和时间索引生成有界候选，再以固定 oversample 上限进入
  v2 排序，避免旧 `I/C` 预排序提前丢掉高相关或高 `F` 候选；
- 按记录类型使用冻结公式与独立配额，最终以稳定 ID 破同分；
- 普通召回排除 `F<0.1` 的 archived；冲突/`superseded` 使用独立通道，不受低 `C` 二次压制；
- 移除 `relevance=importance` 别名；`R` 必须来自实际查询匹配；
- RecallBundle 对 Reasoning 暴露 `R/I/F` 和适用时的 `C`，`D` 只用于诊断和维护。

验证：构造 `R/I/F/C` 对抗样例、分型配额、同分稳定性、归档隔离、情绪/感官/关系召回及候选上限；
确认 Reasoning 不把 Episode 合成 `C`，也不把数值分数降级成字符串 certainty。

退出条件：排序计算只有一个权威实现；SQL 候选裁剪不会改变冻结公式的可观察语义。

### Phase 6：用 `F` 驱动 Lifecycle

主要文件：

- `infrastructure/persistence/memory/sqlite_lifecycle_store.py`
- Maintenance 调度与生命周期测试

实现：

- 用逆函数计算下一阈值到期时间，而不是固定 7/30/60/90 天：

  ```text
  due(F_threshold) = last_reinforced_at
      + D * ((1 / F_threshold - 1) / 9) ^ (1 / 2.6)
  ```

- `F<=0.4` 压缩、`F<=0.2` 摘要、`F<0.1` 归档；每次事务最多推进一个阶段；
- `F<=0.01`、`I<=0.1`、归档满 90 天且依赖安全时逻辑遗忘；
- Lifecycle 只改详情层级、状态、`lifecycle_changed_at` 和下次到期时间，禁止修改
  `I/D/C/last_reinforced_at`；
- 未成功投影 Episode、唯一 Evidence 来源、Genesis 核心依赖和仍被引用记录不得遗忘；
- 保留现有租约、批量上限、检查点、重试和重启恢复；没有 pending Episode 时仍运行到期扫描；
- `F<0.1` 的重新学习走新 Episode/Evidence，不复活旧 D。

验证：阈值精确边界、离线跨过多阈值、一次一阶段、无新 Episode 的维护、租约竞争、故障恢复、
依赖保护、高重要性长期归档但不遗忘、低置信冲突历史不被误删。

退出条件：全仓不存在生命周期修改 `I/D/C/锚点` 的路径；到期行为仅由派生 `F` 决定。

### Phase 7：迁移 Genesis、Consolidation、Lab 与诊断调用方

实现：

- 在 Memory 准入策略中统一识别 Genesis 来源并写 `D0=3650`；批量提交语义保持逐批事务原子，
  Genesis 无需知道 Memory 内部的分批或评分细节；
- Consolidation 模型输出从任意浮点 importance 改成受限事件等级，由策略验证和映射；
- Genesis 可以提交显式初始 `I/C`，其中 Episode 只提交 `I`，Node/Assertion 的 `C` 进入
  seed Evidence；
- Lab 的只读 `memory_inspection_snapshot` 投影和 mock 模型输出适配新类型；当前不存在
  `FakeMemoryStore`，不得为测试重新引入，也不得恢复旧 Node/Edge API；
- DevTools 和诊断明确显示 `I/D/F/C`，Episode 的 `C` 显示为“不适用”而不是默认值；
- 更新所有 fixture、formatter 和序列化消费者，确保不存在 v1 隐式默认。

验证：Genesis 批量原子性与幂等、所有 Genesis 记录 3650 天、普通准入 2/7/30 天、Lab 隔离、
Reasoning 只消费类型化 RecallBundle、Schema v6 新库完整重启。

退出条件：调用方零 v1 字段/默认值；Genesis 10 年规则只有一个实现位置。

### Phase 8：整体评测、真实模型验收和关闭台账

按顺序执行，避免昂贵验证掩盖基础错误：

1. Retention 纯策略黄金向量；
2. Schema、Repository、幂等与故障注入测试；
3. Recall、Lifecycle、Maintenance 集成测试；
4. Reasoning、Genesis、Lab 受影响测试；
5. Memory/Brain/Genesis 受影响完整测试与持久化治理扫描；
6. Ruff、类型检查、`git diff --check` 和相关架构测试；
7. OPT-003 以 Fake Model 重放 10k/50k/200k 数据，验证容量、P95、归档、重启和无模型调用；
8. 使用本地火山引擎配置执行一次受控真实模型垂直验收；若只验证 Recall→回答，必须明确标注
   尚未覆盖权威 Outcome→receipt 的真实应用场景。

完整真实模型场景必须同时证明：

- 用户信息先形成 Episode，再投影 Node/Assertion/Evidence；
- 后续对话确实从 RecallBundle 读取该记忆并影响回答；
- 模型返回的 adopted memory ID 被校验但不会自动强化；后续显式确认产生唯一使用回执；
- `D` 按公式增长、锚点更新，而仅候选或失败回答不增长；
- 纠正旧事实后，旧 Assertion 的 `C` 降低/`superseded`，但其 `D` 可以因纠正事件增长；
- 重启后仍能召回并保持相同物化分数；日志和报告不包含 API Key 或未脱敏用户数据。

本轮真实 Ark 已证明 RecallBundle 进入提示并影响回答，但报告仍因负责人体验确认以及跨进程
Outcome/outbox 边界未在本仓库实现而保持 BLOCKED。关闭 `MEM-012` 前必须登记：目标设计、完整影响
清单、引用清零、可重放验证、剩余限制五类证据，并补齐或明确批准上述外部 Outcome 验收边界。
OPT-003 性能证据随新 Schema/排序刷新；Pattern/Abstraction 仍保持 `OPT-005 deferred`，不得混称完成。

## 6. 精细化审查结论

### 6.1 已封闭的主要漏洞

| 风险 | 计划中的封闭措施 |
|---|---|
| 把 `D` 当半衰期导致公式语义错误 | 统一命名 `retention_days`，以 `F(D)=0.1` 做黄金向量 |
| 生命周期再次主动“降低清晰度” | `F` 纯派生；Lifecycle 只消费 `F` 并改变状态/详情 |
| 普通召回形成自我强化循环 | 只接受独立权威结果后的准确强化回执；候选/Prompt/回答完成/失败均排除 |
| 高频情绪/感官节点永不遗忘 | 图邻居和批量召回不强化；仅明确采用的具体记录获得回执 |
| Evidence 既提高可信度又随意提高重要性 | `C`、`I`、`D` 三条更新通道彻底分离 |
| 重复或相关证据虚增可信度 | `independence_key` 去相关，全量重算、顺序无关 |
| 乱序事件造成不同结果 | 按 `(occurred_at,event_id)` 重放；物化值可重建 |
| 跨数据库崩溃留下半闭环 | Outcome 先落账、回执幂等补投，不声称跨库原子 |
| SQL 预裁剪使最终公式失真 | 索引候选 + 有界 oversample + 统一最终排序，并做对抗测试 |
| `F=0.1` 边界含混 | 强化条件 `F>=0.1`，归档条件 `F<0.1` |
| 高重要性核心事实被时间删除 | 逻辑遗忘同时要求极低 `F`、低 `I`、归档时长和依赖安全 |
| 低置信历史被误删 | `C` 不参与遗忘条件；冲突/纠正保留历史通道 |
| archived 后无法复用语义身份 | 写入侧按既有指纹有界查找并重学；普通 Recall 仍隔离归档记录 |
| 使用/重要性收据无界增长 | 安全窗口后折叠为可审计检查点；水位前迟到事件拒绝并进入有界诊断 |
| Genesis 魔数散落 | 统一准入策略按来源强制 3650 天 |
| Episode 又出现伪 confidence | Schema、类型、序列化、UI 四层负向测试 |
| 快照 freshness 与记忆 freshness 混名 | 前者迁为 `snapshot_freshness`，后者始终是 `[0,1]` 数值并做类型测试 |
| 升级顺手制造长期兼容壳 | fresh-store Schema v6；旧库明确拒绝并由开发者显式重建 |
| 10k 测试误调用真实模型 | OPT-003 固定 Fake Model；真实模型只做一个受控小场景 |

### 6.2 仍需在实现 Phase 1 冻结、但不改变设计语义的参数

以下是实现级参数，不允许模型自由输出，也不影响 `I/D/C/F` 的职责划分：

- Evidence 来源可靠性枚举到权重的固定映射；
- 普通来源类别的置信先验/权重，以及 Genesis 显式先验的验证范围；
- 允许的未来 UTC 时钟偏差上限；
- receipt 迟到安全窗口、检查点批次和 reconciliation 上限；
- Recall 各类型配额、oversample 倍数和硬上限；
- Maintenance 单批大小、租约时间和调度周期。

这些参数必须用版本化常量和测试固定；若实测需要调整，只能通过策略版本和评测证据修改，
不得修改 Schema 语义或另建评分系统。

### 6.3 执行顺序审查

顺序必须保持：

```text
纯策略与黄金向量
→ 类型/Schema
→ 写入与事件重放
→ 实际使用提案与权威结果反馈
→ Recall
→ Lifecycle
→ Genesis/调用方迁移
→ 规模评测与真实模型验收
```

理由：Schema 依赖已冻结的数值语义；反馈闭环依赖可幂等持久化；Recall 和 Lifecycle 共同依赖
相同 `F`；调用方迁移必须面对最终 typed API；规模与真实模型测试只能验证已收敛候选。
交换这些阶段会产生临时字段、双写、伪反馈或重复评分实现。

## 7. 完成标准

只有同时满足以下条件，才能宣称 Retention v2 完成：

- 权威设计中的全部 `I/D/C/F` 规则有唯一生产实现和边界测试；
- 所有写入路径、召回、Reasoning、Genesis、Lab 和维护调用方已迁移；
- 全仓无固定 `I-0.05`、固定 7/30/60/90 生命周期、`relevance=importance`、Episode confidence、
  Evidence→Importance 或图端点评分传播；
- 幂等、乱序、崩溃恢复、纠正、归档、重学和依赖保护可重放；
- OPT-003 和一次真实火山引擎对话给出可审计证据；
- `MEM-012` 五类关闭证据完整，且所有未验证条件明确标记为阻塞或剩余项。

达到这些条件后停止；不在本计划内顺手实现 Pattern/Abstraction、物理删除、生产迁移或第二套
Retriever。
