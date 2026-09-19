# Elfie Memory Debug Workspace 最终设计

> 状态：设计基线（已完成本轮精细化审查；不代表当前源码已经符合）
> 版本：v1
> 更新时间：2026-09-18
> 所属模块：Elfie / Brain / Memory / Developer Tools
> 上级设计：[Brain 十系统架构](./elfie-brain-ten-system-architecture)
> 下级设计：无
> 规范性契约：[Memory 架构](./elfie-memory-architecture)、[Brain 契约](../../../contracts/brain)
> 当前架构：[认知信息流](../../../architecture/cognitive-flow)
> 一致性台账：[Memory 一致性](../../../conformance/elfie-memory)
> 领域资料来源：Memory source-first 设计、Brain 可观测链路、Memory Audit 历史讨论与当前 Developer Tools 实现。

> 设计关系：**所属模块：**Elfie / Brain / Memory / Developer Tools；**上级设计：**[Brain 十系统架构](./elfie-brain-ten-system-architecture.md)；**下级设计：**无；**规范性契约：**[Memory 架构](./elfie-memory-architecture.md)、[Brain 契约](../../../contracts/brain.md)；**当前架构：**[认知信息流](../../../architecture/cognitive-flow.md)；**一致性台账：**[Memory 一致性](../../../conformance/elfie-memory.md)；**领域资料来源：**Memory source-first 设计、Brain 可观测链路、Memory Audit 历史讨论与当前 Developer Tools 实现。

## 1. 设计结论

Memory Debug Workspace 是给开发者使用的记忆调试工作台，不是面向普通用户的记忆管理页面，也不是第二套 Memory 实现。

它只回答三个问题：

1. 当前整个知识库是什么状态，里面有哪些 Episode、Node、Assertion 和 Evidence。
2. 一个完整 Episode 是怎样被组织成知识，以及这次组织影响了哪些节点和关系。
3. 一次搜索为什么返回这些内容，候选是怎样被评分、筛选、裁剪并形成 RecallBundle 的。

最终形态是一个统一工作台：

- 左侧是全局记忆图，默认显示整个知识库的结构；
- 右侧是与左侧共享选择和高亮状态的详情、添加 Episode、搜索三个面板；
- 左侧负责看结构和变化，右侧负责看证据、操作和解释；
- 右侧操作涉及左侧哪些内容，左侧就高亮哪些节点、边和来源；
- Memory Debug Workspace 可以独立打开，也可以从 Elfie Lab 的 Turn Debug 中以弹窗、抽屉或子面板打开；
- Elfie Lab 继续拥有真实 Turn、Prompt Context 和最终上下文顺序；Memory 页面只解释 Memory 自己产生了什么、为什么产生。

本设计冻结的是语义、边界、交互和验收标准。它不冻结具体图形库、是否使用真正的 WebGL 3D，或某个单一前端组件实现。

## 2. 设计目标与非目标

### 2.1 目标

- 让开发者先看到整个 Memory，而不是先进入某个局部搜索结果。
- 让 Episode、Evidence、Node、Assertion 的来源关系可追溯。
- 让一次 Episode 写入和整理过程可重放、可暂停、可定位失败步骤。
- 让一次 Recall 的候选、评分、淘汰、保留和预算裁剪有逐候选解释。
- 让左侧全局图和右侧操作面板保持同一个选择、过滤和高亮上下文。
- 让真实观测、投影数据和 UI 推断严格区分。
- 复用现有 Memory source-first、持久化和观测边界，不建立第二事实源。

### 2.2 非目标

- 不把 Developer Tools 变成生产 Memory 的写入入口。
- 不在页面中重建 Brain、Model、Prompt 或 Elfie Lab 的 authority。
- 不把 Evidence 绘制成普通知识节点，不把 Assertion 绘制成独立实体节点。
- 不把召回排序顺序伪装成 Memory 图上的空间顺序；真正进入上下文的顺序由 Elfie Lab 的 Context/Turn Debug 展示。
- 不用动画替代真实事件；没有观测证据的步骤必须显示为未知或不可用。
- 不以“看起来像 3D”作为验收条件。图形渲染是实现选择，语义投影和交互行为才是契约。

## 3. 语义模型与显示边界

### 3.1 Memory 的五层显示模型

页面使用以下稳定语义，不允许因为 UI 方便而合并或重复建模：

| 层 | 语义 | 页面表现 |
| --- | --- | --- |
| Event / Turn | 运行时发生的事实或一次 Brain Turn | 在详情或嵌入 Elfie Lab 的上下文中显示，不直接当作知识图节点 |
| ClosedEpisode | 已完成、可持久化、可追溯的经验来源 | 左侧最上方的 Episode 来源带；显示时间、摘要、状态和关联范围 |
| Evidence | Node/Assertion 对 Episode 或其他来源的出处证明 | 作为来源连接、边上的 provenance 和右侧证据详情显示，不作为普通节点 |
| Node | 被 Memory 维护的实体、概念或知识单元 | 左侧全局知识图中的节点 |
| Assertion | Node 与 Node 之间的有向语义关系 | 左侧知识图中的有向边；关系类型、置信度和生命周期在右侧显示 |

RecallBundle 是一次搜索的输出，不是图上的第六类永久节点。它在右侧搜索过程和左侧临时高亮中显示。

### 3.2 Source-first 原则

ClosedEpisode 是持久来源，Node、Assertion 和 Evidence 是可重建、可解释的投影。页面必须能够从任意 Node 或 Assertion 回到其 Evidence，再回到来源 Episode。

任何“当前知识”都必须能够回答：

- 它来自哪些 Episode；
- 是哪条 Evidence 支持它；
- 它当前是什么生命周期状态；
- 它的置信度、重要性、保留策略和冲突状态分别是什么；
- 当前 Recall 是否选中了它，若没有，原因是什么。

生命周期、重要性、保留、置信度、冲突和 supersedes 是不同语义，不能在 UI 中合成一个“权重”字段。

## 4. 总体布局

### 4.1 左右面板

默认采用左大右小布局：

- 左侧约三分之二到四分之三宽度：全局记忆图；
- 右侧约四分之一到三分之一宽度：详情和操作面板；
- 小屏幕时右侧可变成抽屉或覆盖层，但共享状态和交互语义不变。

左侧的职责是“看整体结构、来源和受影响范围”。右侧的职责是“看选中对象的完整事实、运行一个调试操作、解释一次过程”。

### 4.2 左侧结构

左侧从上到下包含三层：

1. Episode 来源带：按时间或当前操作上下文排列完整 Episode。Episode 是来源层，不与下方知识图中的 Node 重复。
2. 全局知识图：显示 Node 和 Assertion。Evidence 用连接线、边标记或详情关联表示。
3. 状态栏：显示节点数、关系数、Episode 数、Evidence 数，以及当前过滤、选中和操作状态。

默认打开页面时展示整个知识库，不展示初始化过程，也不默认只显示某次搜索结果。开发者可以通过类型、生命周期、时间、来源、置信度和操作范围过滤；过滤默认采用“弱化不相关内容”，而不是立即删除全部上下文。

### 4.3 图形交互

全局图必须支持：

- 拖拽画布、缩放、平移；
- 拖拽节点和稳定布局；
- 点击 Node、Assertion、Episode 或 Evidence 关联；
- 选择后高亮直接关联对象，其他对象降噪；
- 从右侧操作结果反向定位左侧对象；
- 长文本在图上显示短标签，在右侧显示完整内容；
- 大规模数据使用分层细节、聚类、按需展开和视口裁剪。

图形可以是 2D、2.5D 或 3D。第一阶段只要达到“可拖拽、可缩放、可查找、结构清楚、不会因节点多而失控”，不要求接入 Godot 或把 Memory 图交给物理世界 authority。

## 5. 右侧三个面板

### 5.1 详情面板

详情面板由左侧选择驱动，不自行产生第二份数据。

支持的选择对象：

- Episode：完整来源内容、时间、来源、状态、摘要、关联 Node/Assertion、处理结果和失败信息；
- Node：类型、名称、描述、置信度、重要性、生命周期、来源 Evidence、相关 Assertion、冲突和 supersedes；
- Assertion：主语、关系、宾语、谓词、置信度、状态、Evidence、创建和更新过程；
- Evidence：引用的 Episode、证据片段、提取位置、证据类型、支持对象和可信状态；
- 操作步骤：输入、输出、耗时、观察事件、错误和受影响对象。

详情中可以继续点击关联对象，左侧同步聚焦。详情显示的是证据和状态，不使用无法由投影证明的“模型一定看到了”“系统已经理解”等表述。

### 5.2 添加 Episode 面板

输入必须是完整 Episode，而不是一条短消息。面板至少包含：

- Episode 内容和元数据；
- 预览模式、数据范围和当前数据版本；
- 校验结果；
- 操作步骤时间线；
- 新建、更新、重复、冲突、跳过和失败结果；
- 受影响 Node、Assertion、Evidence 的数量和列表。

标准过程为：

1. 接收并校验完整 Episode；
2. 写入或模拟写入来源；
3. 提取候选知识；
4. 生成 Evidence；
5. 创建或更新 Node；
6. 创建或更新 Assertion；
7. 执行 consolidation；
8. 执行 maintenance、生命周期更新和冲突处理；
9. 生成本次操作的结果快照。

每一步都必须有可追溯的 operation id、输入版本、输出版本和观测状态。左侧按步骤高亮新建、更新、受影响和被跳过的对象；右侧显示当前步骤详情，支持暂停、继续、重放和跳到失败步骤。

默认只能在隔离数据或 dry-run 中执行。若未来提供真实提交，必须有明确的开发者确认、目标数据根、版本检查、幂等标识和可回滚边界；不得让 Developer Tools 直接写入生产 ELFIE_HOME。

### 5.3 搜索 / Recall 面板

搜索面板展示一次 Recall 的完整解释链：

1. 查询输入和归一化结果；
2. 候选来源及候选数量；
3. 每个候选的评分、命中词、匹配类型和排序位置；
4. 被保留或淘汰的决定；
5. 淘汰原因，例如低于阈值、超出 Top-K、超出类型上限、超出字符预算；
6. 最终 RecallBundle；
7. 关联 Episode、Node、Assertion、Evidence 在左侧的高亮。

右侧必须允许逐候选展开，不能只显示“返回了 N 条”。左侧显示“当前被召回的对象”和“与召回对象关联但未被返回的对象”两种不同高亮。

真正进入模型上下文的顺序、最终字符预算和实际 Prompt 片段属于 Elfie Lab 的 Context/Turn Debug。Memory 页面可以链接到该位置，但不能凭 Memory 自己的图顺序声称它就是 Prompt 顺序。

## 6. 左右联动状态

页面维护一个共享的 Debug View State：

~~~yaml
selection:
  kind: episode | node | assertion | evidence | operation-step | none
  id: string | null
filters:
  node_types: []
  lifecycle: []
  time_range: null
  source_ids: []
highlight:
  selected: []
  affected: []
  returned: []
  related: []
operation:
  run_id: string | null
  mode: idle | preview | running | paused | succeeded | partial | failed
  step_id: string | null
recall:
  query_id: string | null
  decision_id: string | null
  context_link: string | null
~~~

状态变化必须是可逆、可解释和可定位的：

- 点击左侧对象，右侧详情更新；
- 在右侧详情点击关系，左侧聚焦对应边和来源；
- 添加 Episode 的每一步更新左侧受影响对象；
- 搜索的每一个决定更新左侧 returned/related 高亮；
- 清除选择只清除选择，不清除过滤；
- 清除操作结果只清除临时高亮，不改变知识库快照。

## 7. 事实投影接口

页面需要消费稳定的只读投影，而不是自行拼 SQL 或解析任意日志。建议保持四类投影：

### 7.1 LibrarySnapshot

表示整个知识库的当前视图：

- snapshot id、生成时间和数据版本；
- Episode、Node、Assertion、Evidence 的计数；
- 节点、边、来源和关系类型；
- lifecycle、confidence、importance、conflict、supersedes；
- 图布局所需的最小几何提示，不保存为 Memory 语义事实。

### 7.2 DetailProjection

表示一个被选对象及其可追溯关联。它必须返回完整事实或明确的截断标记，不能用总数或 ID 伪装成完整内容。

### 7.3 OperationTrace

表示一次 Add Episode 或其他 Memory 操作：

- run id、输入 Episode、数据版本；
- 有序步骤；
- 每步输入、输出、观测事件、耗时和错误；
- affected、created、updated、skipped、conflicted、failed 对象；
- 最终 revision 和可继续/重放状态。

### 7.4 RecallExplanation

表示一次搜索：

- query 和 query id；
- candidates_seen；
- 每个候选的 score、matched terms、rank、kept 和 exclusion reason；
- per-kind limit、top-k、character budget；
- 最终 RecallBundle；
- 到 Context Workspace 或 Elfie Lab 的关联 id。

如果后端尚未提供某字段，前端显示“未观测到”而不是推测。图、详情和操作面板都只使用同一份投影。

## 8. 与 Elfie Lab 的关系

### 8.1 两个入口，一个工作台

工作台支持两个入口：

- 独立入口：默认打开整个知识库，适合检查整体现状和运行独立搜索；
- Elfie Lab 入口：从某次 Turn Debug 的 Memory/Recall 链接打开，带入 turn id、query id 或 operation id，并自动定位相关对象。

两者必须使用同一个 Memory Debug Workspace 组件和同一套投影契约，不复制一套“Lab 版 Memory 图”。

### 8.2 边界

- Memory Debug Workspace：解释 Memory 保存、整理、召回了什么以及为什么；
- Elfie Lab：解释一次 Brain Turn 的上下文、模型输入、实际使用和最终响应；
- Context Workspace：解释哪些材料实际进入了上下文及其最终顺序。

当开发者在 Recall 面板点击“查看本轮上下文”时，打开 Elfie Lab 的对应上下文详情；当开发者在 Elfie Lab 看到一条 Memory 结果时，可以回到本工作台查看其来源和召回原因。

## 9. 状态、失败与安全

页面必须显式区分以下状态：

- 空库、部分投影、完整投影；
- 正在运行、暂停、成功、部分成功、失败；
- 低置信度、冲突、已 superseded、已归档；
- 召回成功但被字符预算裁剪；
- 候选存在但全部被筛掉；
- 后端未提供详细观测；
- 数据版本过期或快照与当前库不一致。

失败不能只显示一个红色 Toast。至少要显示失败步骤、输入版本、已完成副作用、是否可以重放，以及是否需要人工处理。

Developer Tools 的默认安全边界：

- 只读查看生产数据；
- 写入实验必须使用隔离数据根或 dry-run；
- 详情中对隐私内容进行必要的脱敏或明确标记；
- 不在前端保存第二份知识库；
- 不在 UI 层绕过 Memory、Persistence 或 Lifecycle 的现有 authority。

## 10. 当前实现与目标的差距

当前实现已经具备可复用基础，但还不能作为最终设计的完成证明：

| 能力 | 当前已有 | 与目标的差距 |
| --- | --- | --- |
| 全局快照 | 有 Memory Audit inspect 投影和统计 | 图面仍是固定布局，缺少可扩展的全库导航和 LOD |
| 来源与图 | 有 Episode、Node、Assertion、Evidence 数据 | Evidence、来源追踪和关联高亮未形成完整交互闭环 |
| 详情 | 有详情 Tab，可看 Node 和关系 Evidence | 详情类型、版本、冲突、生命周期和完整证据还不完整 |
| 添加 Episode | 有输入占位和只读保护提示 | 还没有真实的可观测 dry-run/operation trace/replay |
| Recall | 可调用 recall API 并显示结果 | 未把 candidate scoring、淘汰原因和每个决定完整投影到 UI |
| 左右联动 | 有三个 Tab 的外壳 | 操作结果尚未稳定驱动图中 affected/returned/related 高亮 |
| Elfie Lab 集成 | 当前是独立 Memory Audit 路由 | 还没有统一组件、turn/query 上下文链接和双向跳转 |
| 运行安全 | 当前添加入口是只读的 | 目标需要明确隔离实验和未来真实提交的安全闸门 |

因此，当前实现的主要问题是“观察面和交互面没有完成”，不是 Memory 持久化模型需要删除重建。

## 11. 实现策略评估与决定

### 11.1 三种方案

| 方案 | 优点 | 主要风险 | 结论 |
| --- | --- | --- | --- |
| 从头另做一套 | 可以直接按新布局设计 | 重复事实源、重复 API、丢失已有测试和可运行边界，最后还要迁回现有产品 | 不采用 |
| 删除当前实现后重做 | 表面上没有旧 UI 包袱 | 破坏可复现基线，丢失现有只读保护和已验证投影；新实现仍需重新接回旧后端 | 不采用 |
| 保留基线、按目标渐进演进 | 保留真实数据契约、接口、测试和回退入口；可以逐步替换不合格的呈现层 | 需要明确哪些旧 UI 只作为过渡，避免继续在固定图布局上堆补丁 | 采用 |

### 11.2 最终决定

选择“保留当前 Memory 后端、投影和测试；通过独立的 `/elfie/memory-debug` 路由实现新工作台；旧 `/elfie/memory-audit` 页面和共享旧样式保持基线不变，待新工作台验收通过后再决定是否退役”。

这不是对当前效果的认可，而是对系统风险的控制：

- 当前已有 source-first Memory、只读 inspect/recall 边界、持久化数据和测试，删除它们没有设计收益；
- 当前 Add Episode 入口默认不写生产数据，因此不会因为保留旧页面而自动污染 Memory；
- 当前固定 SVG、缺少真实过程、缺少逐候选 Recall 解释，确实会误导开发者，必须把它标为过渡界面并尽快替换；
- 新页面应先复用真实投影和观测，再替换布局；不能为了追求视觉重做而建立第二套 Memory 逻辑。
- 新页面不能把旧路由改造成过渡实现；旧路由必须能够独立回归和截图对照。

### 11.3 推荐迁移顺序

1. 冻结本设计和数据边界，明确 `/elfie/memory-audit` 为 legacy baseline，并先建立 `/elfie/memory-debug` 独立入口。
2. 抽出统一的 LibrarySnapshot、DetailProjection、OperationTrace、RecallExplanation 和共享选择状态。
3. 先替换左侧全局图：Episode 来源带、Node/Assertion 图、Evidence 追踪、过滤、缩放和高亮。
4. 保留并完善详情面板，使所有选择都能回到来源和证据。
5. 接入已有的 Recall selection observation，完成逐候选评分、淘汰原因、预算裁剪和左侧高亮。
6. 为 Add Episode 增加隔离 dry-run、真实步骤观测、失败/部分成功和重放；在没有安全闸门前不开放生产提交。
7. 将同一工作台嵌入 Elfie Lab Turn Debug，实现 Memory 与 Context 的双向跳转。
8. 通过验收后再删除或隐藏旧的固定图布局；删除是最后一步，不是第一步。

## 12. 设计效果评估

按开发者调试目标评估，这套设计比当前实现和“另起炉灶”都更合适：

| 目标 | 评估 | 原因 |
| --- | --- | --- |
| 了解整个知识库 | 9/10 | 默认全库、来源层和关系图同时可见，过滤只做降噪 |
| 理解 Episode 到知识 | 9/10 | 来源、Evidence、Node、Assertion 分层，右侧可重放，左侧显示影响范围 |
| 解释一次 Recall | 9/10 | 候选级评分、淘汰原因、预算裁剪与关联高亮明确分工 |
| 定位当前数据问题 | 9/10 | 详情、证据、生命周期、冲突、版本和失败步骤可追溯 |
| 左右联动效率 | 9/10 | 统一选择状态，操作不再是右侧孤立表单 |
| 与架构一致性 | 9/10 | 复用 Memory source-first 和现有 authority，不把 UI 变成第二事实源 |
| 大规模知识库 | 7/10 | 需要 LOD、聚类、虚拟化和稳定布局；这是明确的实现风险 |
| 真实过程可信度 | 8/10 | 目标要求真实观测；当前后端仍需补充 consolidation/lifecycle 的细粒度事件 |

综合评价：目标设计约 8.8/10，已经足够作为实现基线；当前实现约为“可运行的只读骨架”，不能按最终设计验收。最需要优先补齐的不是装饰，而是三项证据闭环：来源到知识、操作步骤到受影响对象、候选决定到 RecallBundle。

## 13. 验收标准

### A. 全局现状

- 打开工作台默认能看到当前知识库的 Episode、Node、Assertion 和统计；
- 可以过滤和降噪，但不会因一次过滤丢失当前结构上下文；
- 任意 Node/Assertion 都能回溯到 Evidence 和 Episode；
- 选中对象后，右侧事实完整，左侧关联对象高亮。

### B. Episode 过程

- 输入一个完整 Episode 后，可以在隔离数据或 dry-run 中重放；
- 页面显示校验、提取、Evidence、Node、Assertion、consolidation、maintenance 的真实步骤状态；
- 每一步都有可追溯 id、输入/输出版本和受影响对象；
- 成功、重复、更新、冲突、部分成功和失败均有明确显示；
- 过程结束后，左侧能够准确显示受影响节点和边。

### C. Recall 过程

- 输入查询后能看到候选、评分、排序和命中信息；
- 每个未返回候选都有明确淘汰原因；
- 能看到 Top-K、类型上限和字符预算造成的裁剪；
- 左侧区分 returned、related、candidate-but-excluded；
- 可以跳到 Elfie Lab 查看实际上下文及其顺序。

### D. 安全与架构

- 默认查看生产数据为只读；
- 实验写入默认隔离或 dry-run；
- UI 不直连 SQL、不创建第二事实源、不接管 Runtime 或 Godot authority；
- 没有观测到的事实明确标记为未知；
- 当前旧实现只有在新工作台通过上述验收后才允许退役。

## 14. 暂留决策

以下事项不阻塞本设计冻结，但实现前需要按当前仓库能力做最小选择：

- 第一版采用 2D、2.5D 还是真正 3D；建议先满足 2D/2.5D 的交互和性能验收；
- Add Episode 的隔离数据根具体采用复制数据库、临时数据根还是后端提供的事务预览；
- consolidation、lifecycle、conflict 和 supersedes 需要补充哪些结构化观测；
- Elfie Lab 采用弹窗、抽屉还是子路由承载工作台；
- 大图达到什么节点数后启用聚类和分层展开。

这些选择不能改变本设计的核心边界：一个工作台、一份事实投影、左右联动、来源可追溯、过程可解释、Recall 与真实上下文分工明确。
