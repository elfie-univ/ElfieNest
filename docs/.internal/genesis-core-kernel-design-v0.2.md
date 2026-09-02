# Genesis 核心内核设计 v0.2：从世界骨架到初始记忆

> 状态：内部现行目标设计；受 ADR-0033 与 Elfie 2.3 / Brain 1.5 契约约束
>
> 版本定位：本文经确认后成为 Genesis 唯一现行目标设计，并取代
> [OPT-001 Genesis v0.1](./genesis-core-kernel-design-v0.1.md) 作为后续设计依据。v0.1 保留为已落地
> OPT-001 的冻结历史基线；本文不表示当前代码已经实现，也不授权修改既有 Elfie 数据
>
> 上游世界资料：
> [Elfaria 自底向上世界设定](./elfaria-bottom-up-world-design-v0.1.md)、
> [Elfaria 世界公共知识总览](./elfaria-public-knowledge-overview-v0.1.md)

## 1. 目标与不可变原则

Genesis 的目标不是让模型临场编出一个角色，而是把已经确认的世界、用户领养选择和受控随机性，
在一次创建事务中编译成一只内部一致、可以校验且提交后自足的 Elfie：

```text
造物者世界骨架
→ 居民公共知识
→ 机器可读的 Genesis 静态目录
→ 单只 Elfie 的 LifeContext
→ 单只 Elfie 的 PersonalGenesisPlan
→ GenesisBundle 一次性发布至 Profile / Selfhood / Memory
→ 销毁问卷、LifeContext、计划、资料绑定与 Seed
```

全流程遵守以下原则：

1. 世界事实由人工确认的世界资料定义；程序和模型都不能新增 Canon。
2. 居民可知知识与生成器专用事实严格隔离；人口密度、底层物理参数和精确采样坐标不能泄漏给 Elfie。
3. 用户选择是 Genesis 的正式输入；`any` 等偏好必须先解析为实际候选值，不能成为 Elfie 的真实身份。
4. 身份、地点、人物、时间线、知识接触、关系变化和事件结果由确定性程序生成；模型只实现语言表达。
5. 相同创建输入、时间锚点、目录版本、生成策略版本和 Seed，在同一次未完成创建事务中必须得到相同结构化结果；这个确定性只服务候选生成、失败恢复和测试，不授权提交后重造同一 Elfie。
6. 问卷、领养选择、资料包绑定、Seed、LifeContext 与 PersonalGenesisPlan 都是创建期临时输入或中间产物；成功提交或终止失败后必须删除。
7. 提交后事实只归 Profile、Selfhood 和 Memory 最终所有者；普通 Brain 运行只读取 Selfhood、Memory 与当前 Brain 状态，不读取 Profile、Canon、Genesis 资料包或创建回执。
8. Canon 或生成规则升级只影响未来创建；既有 Elfie 的学习、修复或迁移必须以最终所有者为输入另行设计，不能重放 Genesis。
9. 年龄采用一对一的地球年龄口径：Elfaria 生活了几岁，来到地球后就按几岁理解和显示。这个简化只用于年龄与生命周期，不改写 Elfaria 的昼夜、季节和天文设定。

范围只覆盖新领养 Elfie 的世界资料编译、LifeContext、领养前人物与经历、初始 Memory 和一次性发布。
运行期持续学习与压缩、真实 Nest/Godot 观测和身体、实时天气与活动、多 Elfie 共享关系、向量数据库、
第二套存储及既有 Elfie 数据迁移均不属于本文；需要时分别立项，不能借 Genesis 顺带实现。

本设计不规定具体概率和评分数值。它们必须作为阶段 2 的版本化策略数据存在，由程序校验，不能散落在代码或模型提示词中。

### 1.1 与 Genesis v0.1 的版本关系

v0.1 是已关闭 OPT-001 的实施与验收快照，不再随新设计更新；历史 E1/E2/E3 证据只证明 v0.1。
v0.2 是它的直接继任，不是平行管线，也不能复用 OPT-001 的 `closed` 状态宣称已经落地。实施 v0.2
必须另立工作项，迁移现有入口和合同，并重新建立受影响门禁。

| 处置 | v0.1 | v0.2 |
| --- | --- | --- |
| 保留 | Profile / Selfhood / Memory 分工，三类 Seed，3～5 段经历、10～20 个关系、创建期幂等和 source-first Recall | 延续最终所有者分工与唯一运行时知识路径；不保留可重建人生的长期 Manifest |
| 扩展 | 从版本化 Canon 直接进入个体化 | 补全世界骨架、居民知识、静态目录、LifeContext 和 PersonalGenesisPlan |
| 替换 | 八个主题和 40～80 条是首版内容与评测规模 | 以四部分人读知识、双向覆盖和问题覆盖判断完整性，不设固定条目数 |
| 替换 | 模型可以提出结构化候选 | 结构化事实由确定性程序生成，模型只做非权威语言投影 |
| 替换 | “原子导入 Profile/Selfhood/Memory”未区分存储边界 | Memory 内原子提交，App 通过可恢复 Admission 状态机协调发布 |
| 替换 | 三类 Seed 机械共享 certainty 等字段 | Confidence、Importance 按最终记录类型生成；Retention 由 Memory 准入策略解析，Episode 没有 Confidence |
| 替换 | `custom/CFHO` 作为通用扩展输入 | 只接受注册的 AdoptionSelection 字段或版本化类型扩展；自由文本不能影响结构化事实 |

负责人确认后，后续设计只维护 v0.2；v0.1 保持冻结。实施不得保留长期双写、旧新随机分流、兼容
fallback 或第二套 Memory 路径；未来若形成 v0.3，v0.2 同样转为冻结历史快照。

## 2. 六阶段主流程与数据归属

世界资料到个人记忆不是一条单线。居民知识来自居民可观察层；出生点、人口权重和生活原型可以读取
造物者资料中的生成器专用层，但不能绕过居民知识进入个人认知：

```text
阶段 0 造物者世界骨架 ──→ 阶段 1 居民公共知识 ──→ 阶段 2 KnowledgeCatalog
           │
           └──────────────────────────────→ 阶段 2 生成器专用目录

用户领养输入 ──→ 阶段 3 LifeContext
阶段 2 + 阶段 3 ──→ 阶段 4 PersonalGenesisPlan
阶段 4 ──→ 阶段 5 GenesisBundle 与最终所有者
```

| 阶段 | 权威产物 | 保存形式 | 产生者 | 完成后的用途 |
| --- | --- | --- | --- | --- |
| 0. 造物者世界骨架 | `CreatorWorldSkeleton` | 人读 Markdown、地图及受控附件 | 人工设计、人工确认 | 世界因果与生成器事实的上游来源 |
| 1. 居民公共知识 | `ResidentKnowledgeBaseline` | 人读 Markdown | 人工提取、人工确认；AI 只能辅助整理 | 确认居民能如何理解和表达世界 |
| 2. Genesis 静态目录 | 已发布的 `GenesisSourcePackage` | `config/` 下版本化 YAML 与引用资产，经 Infrastructure 加载为强类型对象 | 人工配置、人工发布、程序校验 | 为未来创建提供统一且可校验的机器输入 |
| 3. 个体生活上下文 | `AcceptedGenesisReservation`、`GenesisCompileEnvelope`、`LifeContext` | 未发布私有创建工作区中的临时类型对象 | 用户输入 + App 分配的身份与锚点 + Genesis 确定性算法 | 在一次未完成创建事务内冻结候选和生活条件 |
| 4. 个体创生计划 | `PersonalGenesisPlan` | 未发布私有创建工作区中的临时类型对象 | Elfie Genesis 编译器；模型只生成受限措辞 | 形成最终所有者写入计划 |
| 5. 最终提交 | `GenesisBundle`、`GenesisCommitReceipt` | Profile、Selfhood、source-first Memory；另存最小技术回执 | Genesis 校验最终值，App 只编排一次性发布 | 最终值归各所有者，创建输入随后销毁 |

阶段 3、4 的完整 JSON 只能在未发布私有创建工作区中支持本次事务恢复。成功提交或终止失败后，
`AcceptedGenesisReservation`、`GenesisCompileEnvelope`、LifeContext、Plan、问卷答案、资料包绑定和全部
Seed 必须清理。长期保留的 `GenesisCommitReceipt` 只能包含最终 Elfie/预约 ID、幂等键摘要、最终所有者
Schema 修订、输出对象 ID/摘要、编译器修订、完成状态和时间；不得包含问卷、世界知识、资料包/策略绑定、
Seed、完整 LifeContext/Plan 或足以重建人生的字段。

模块职责随数据生命周期固定：`elfie/genesis` 独占 LifeContext、知识过滤、人物关系、Episode 与三个最终
所有者草稿的语义编译；`app/features` 收集领养输入，`app/orchestration/resident_admission` 只协调预约、
提交、恢复和清理；`infrastructure` 只加载/校验资料包的技术结构并保存 Genesis 已生成的强类型值，不能
选择知识、推导人格或编造人物与故事。Profile 是给外部消费者看的冻结客观档案，不是 Brain 输入或创建
溯源容器。

### 2.1 阶段 0：造物者世界骨架

阶段 0 从造物者角度描述世界如何成立，包括底层参数、因果链、生态、地理、人口、社会、技术和历史。
每项设定必须属于以下一种可审查类别：

- **居民可观察**：居民能够通过生活、教育、记录或传闻接触；可以进入阶段 1。
- **生成器专用**：只用于保证世界和随机生成一致，例如精确人口权重、适生网格和深层机制；不能进入阶段 1。
- **尚未确定**：不得由阶段 1、配置作者、程序或模型补写。

每项设定使用稳定 `creator_fact_id`。所有居民可观察项必须映射到阶段 1 的知识锚点，或带理由标为
`deferred`；生成器专用和尚未确定项不得进入居民知识。这张覆盖关系用于发现遗漏，不进入 Elfie 记忆。

地图同时具有两种表达：居民能使用的地名、路线与相对远近属于可观察层；精确采样坐标、密度权重和
尚未公开区域属于生成器专用层。

### 2.2 阶段 1：居民公共知识

阶段 1 只整理公共知识，不描述任何具体 Elfie 的家庭、职业、熟人或个人故事。正文保持当前四部分结构：

1. 全体共通知识；
2. 地方与空间知识；
3. 群体与专业知识；
4. 公共认知边界。

这四部分只负责人的阅读顺序和传播范围，不是机器目录的四个大标签。完整性由阶段 0→1→2 的双向覆盖、
居民问题覆盖和未知边界共同证明，不沿用 v0.1 的八主题或 40～80 条数量门。

每个知识点用居民能够理解的现象、经验、制度或传闻表达，不使用“系统设置”“当前未定义”“参数值决定”
等造物者语言。地图知识只写居民可能知道的地点、方向、通行条件和相对时间，不写生成器坐标或人口底数。

每个列表知识点具有简短稳定的 `resident_knowledge_id`；可以用不影响正文阅读的 Markdown 锚点保存。
每个 ID 都必须回指一个或多个阶段 0 的 `creator_fact_id`。居民制度、传统和公共记录也必须先在阶段 0
成立；阶段 1 不能成为新增世界事实的旁路。

阶段 1 的一条列表项不等于一张机器知识卡。阶段 2 可以把一条概述拆成公共概况、地方细节、专业操作
和受限解释等多个原子知识，但每个原子都必须追溯到阶段 1 的明确段落；发现新事实时先回到阶段 0、1
审阅，不能直接写入 YAML。

### 2.3 阶段 2：Genesis 静态目录

`GenesisSourcePackage` 是一个逻辑包，可以拆分为多个配置文件，但必须由 `SourcePackageManifest` 固定
全部成员、版本、来源哈希、相互引用和发布状态。Genesis 只接受 `published` 包；一个包只需在仍被发布
渠道或未完成创建事务引用时可用。已经提交的 Elfie 不再引用它，不能因为审计或恢复旧 Elfie 而长期保留
旧包。逻辑包至少包含：

| 目录 | 内容 | 可否进入模型或 Elfie 记忆 |
| --- | --- | --- |
| `KnowledgeCatalog` | 居民可知的原子知识、表达层级、接触条件和来源 | 只有通过个体编译后的安全变体可以进入 |
| `PlaceCatalog` | 稳定地点 ID、层级、居民称呼和语义类型 | 居民可见字段可以进入 |
| `RouteCatalog` | 稳定路线 ID、居民称呼、连接地点、通行条件和通常旅行时间 | 居民可见字段可以进入 |
| `SpatialPopulationModel` | 适生单元、密度权重、聚落权重、隐藏几何、路线成本和设施覆盖 | 生成器专用，不得直接进入 |
| `SpeciesLifeRules` | 地球年龄口径下的生命周期、物种分布、成长和生活约束 | 只输出居民可知结果，不输出隐藏权重 |
| `LifeArchetypeRules` | 家庭、学习、职业、居住和迁移原型及条件权重 | 原型 ID 不进入；生成后的个人事实可以进入 |
| `NameRules` | 物种命名词库、音系和去重规则 | 只输出生成后的名字 |
| `RelationshipArchetypes` | 家庭、朋友、邻居、导师、同业和赴地联系人槽位 | 只输出生成后的具体关系 |
| `EpisodeThemeCatalog` | 经历主题、前置条件、角色需求、关系弧和禁止事实 | 只输出生成后的具体经历 |
| `EarthArrivalRules` | 可参加的物种/生命阶段、同意与照护条件、所有抵达者的必修培训及最低掌握要求 | 只输出个人资格、培训与相应知识 |
| `GenerationPolicy` | 概率表、评分映射、数量边界、子 Seed 和校验版本 | 永不进入模型或 Elfie 记忆 |

`SourcePackageManifest` 同时保存双向 `CoverageManifest`：每个阶段 1 知识 ID 必须映射到一个或多个
`KnowledgeCatalog` 原子，或带理由标为 `deferred/excluded`；每个原子也必须回指阶段 1。任何未分类项、
孤立原子或未审阅成员都会阻止发布。这样既能防止 YAML 多写，也能发现知识漏转。

`SpatialPopulationModel` 只描述 Elfaria 领养前来源的历史生成空间。它引用阶段 0 已确认的地图资产、
稳定 ID 和内容哈希，不复制一份地图几何；它既不是当前 Nest 的生活语义，也不是 Godot 的坐标、导航
或碰撞权威。初始化结束后，运行时不能用它回答“我现在在哪里”或制造巢内经历。未来若要把某个
Elfaria 地点映射为可运行场景，必须另建经过批准的显式映射，不能因为名字相同就默认是同一空间实体。

知识目录采用“分组默认值 + 原子覆盖”，避免每条重复低密度元数据。逻辑结构如下：

```yaml
group:
  id: geography.mistyville
  defaults:
    scope_kind: regional
    topic_ids: [geography, local_routes]
    epistemic_kind: lived_observation
    acquisition_channels: [home_life, local_teaching]
    certainty_class: established
    importance_class: ordinary
  atoms:
    - id: geography.mistyville.route_example
      statements:
        full: "居民能够完整说明的版本"
        partial: "只保留亲历概况的版本"
      retrieval:
        aliases: ["居民使用的别称"]
      access:
        any_of:
          - all_of: [resident_of_region]
          - all_of: [visited_region, learned_local_routes]
      exposure:
        channels: [daily_route, local_guide]
        weight_class: frequent
      prerequisite_ids: []
      related_ids: []
      source_ref: "居民知识文档中的稳定锚点"
```

约束如下：

- `access` 只使用注册过的条件 ID 和有限的 `any_of/all_of`，不允许可执行表达式。
- `access` 表示“是否可能知道”；`exposure` 表示“实际接触机会和深度”，两者不能合并。
- `full/partial` 是逐级删减细节的安全变体，不能只给完整文本贴一个较低掌握标签；不适用的
  变体可以省略，但编译器不得选择未显式提供的掌握状态。
- “亲历、受教、查阅、听说、神话、未知边界”属于独立的 `epistemic_kind`，不能与掌握多少混成一个状态。
- 公共概况、地方细节、专业操作和受限机制必须拆成不同原子；普通居民不能因知道概况而获得专业步骤。
- 未知边界使用居民语言单独建原子；不能把造物者尚未设计的内容伪装成居民确定知道“不存在”。
- 每个原子必须有注册的 `topic_ids`；`aliases` 只记录居民真实使用的别称，不为凑字段制造同义词。
  发布器为每个 statement 变体分别从该变体、主题和允许的别称生成 `compiled_search_terms` 与索引哈希，
  作者不手写第二份检索文本；`partial` 变体不得继承只出现在 `full` 变体中的关键词。
- `KnowledgeCatalog` 不得包含任何生成器专用字段；引用只能指向居民知识锚点。

`EarthArrivalRules` 是赴地资格的前置条件。只有规则列出的物种和生命阶段可以进入候选；需要照护或共同
同意的阶段必须满足相应条件。不存在 `participated: false` 的已抵达 Elfie：所有抵达者都完成必修培训，
但强制参加只保证最低掌握，不保证扩展内容完全相同。培训只能引用 `KnowledgeCatalog` 中已经审阅的知识
和程序，不得自行发明新的地球事实或世界设定。

## 3. LifeContext：确定一只 Elfie 的生活条件

### 3.1 输入与格式

阶段 3 包含“生成候选—冻结接受结果—生成生活背景”三个连续动作。候选集由 `AdoptionSelection`、一个
已发布的 `GenesisSourcePackage`、`master_seed` 和策略版本生成。它们只在候选请求和未完成创建事务中
存在；不能在用户看到候选后改用新目录重新解释同一候选，也不能在成功提交后继续保留。

- `AdoptionSelection`：用户选择的物种、生命阶段偏好、性别偏好、外貌方向、外貌优先项、五个相处情境答案及已注册扩展选项 ID；
- `CandidateCoreResolution`：程序生成有限候选，每个候选拥有实际物种、实际生命阶段、年龄、性别、外貌基因、人格锚点和原生名；
- `AdoptionDecision`：用户选择的候选 ID、最终显示名、领养家庭引用、可选邀请证据引用，以及应用补入的 `adoption_anchor_at`；
- `AcceptedGenesisReservation`：App 以一次 compare-and-set 冻结被接受候选的最终身份、领养家庭引用、`elfie_id`、私人命名空间、预约 ID、幂等键、领养时间和事务状态。它不保存原始答案；资料包、策略、Seed 与必要输入摘要放在同一私有工作区的 `GenesisCompileEnvelope`，只服务未完成事务。一个候选会话只能成功接受一次；事务内重试返回同一预约。

v0.1 的 `custom/CFHO` 不再作为独立的开放输入通道。既有调用方必须把值映射为注册、类型化、版本化的
选项 ID；无法映射就明确拒绝。扩展字段必须进入创建期规范化输入，只能影响声明过的个体差异，不能携带
模型指令、覆盖 Canon、改变已接受身份或绕过资格规则。

只有有效的 `AcceptedGenesisReservation + GenesisCompileEnvelope` 可以继续生成 LifeContext。配置更新、
进程重启或重复请求都不能改变本次事务中的身份和输入；预约过期或引用包不可用时明确失败，不换用模型
或其他版本补齐。成功提交或终止失败后，两者都必须删除；以后恢复 Elfie 不得再次需要它们。

五个相处问题只参与候选人格的受控推导。候选被接受后，Genesis 只接收冻结的人格锚点，不把原始答案
复制进 LifeContext；成功提交后答案不再属于这只 Elfie 的任何持久记录。它们不能直接决定出生地、家庭
条件或社会阶层。邀请原文若由产品另行保存，仍归领养互动证据所有；Genesis 只能接收“邀请已被接受”
这一创建期结构化事实，不能把原文用作生成指令、世界事实或领养前人生依据，也不能暴露给叙事模型。
显示名按长度、字符和保留词规则校验；所有用户字符串都作为结构化数据传递，不能拼进系统指令。

LifeContext 的逻辑结构为：

```text
LifeContext
├── identity
│   ├── species_id / gender / life_stage
│   ├── age_years_at_adoption / adoption_anchor_at
│   ├── original_name / display_name
│   ├── appearance_ref
│   └── personality_anchor
├── origin
│   ├── birth_region_id / birth_settlement_id / birth_cell_id
│   ├── childhood_home_place_id
│   └── predeparture_home_place_id
├── household
│   ├── archetype_id / member_roles
│   └── care_and_trade_context
├── learning
│   ├── path_id / institution_ids
│   └── apprenticeship_ids
├── vocation
│   ├── vocation_id / proficiency_band
│   └── workplace_place_id
├── mobility
│   ├── visited_place_ids
│   └── familiar_route_ids
├── earth_transition
│   ├── curriculum_version / completed_module_ids
│   ├── departure_place_id / route_id
│   └── earth_household_ref / invitation_accepted
└── content_hash
```

`GenesisCompileEnvelope` 单独保存本次事务需要的 `reservation_id/candidate_id/idempotency_key`、规范化选项
摘要、SourcePackage/策略绑定、`master_seed`、命名子 Seed 和中间输出哈希。它不是 LifeContext 的一部分，
不会进入 Profile、Selfhood、Memory 或长期回执。

`birth_cell_id` 等精确采样字段只供生成和校验，不会原样写入精灵记忆。Profile 只接收契约白名单内的
客观身份、稳定年龄/出生锚点、不可变个人来源 ID/冻结标签与最终虚拟外貌；附近地点、熟悉路线、迁居、
培训、出发、抵达和领养经历分别进入 Memory。

LifeContext 的 `content_hash` 对不可变语义字段的规范序列化内容计算。规范格式固定 UTF-8、Unicode
正规化、键顺序、集合排序、数值与时间编码；不得包含本机绝对路径、遍历顺序或隐式系统时间。
Plan 和 Bundle 遵循同一规则。哈希排除哈希字段自身，以及 `status`、校验诊断、`committed_at` 等
事务字段，避免自引用和恢复漂移；这些字段只在创建工作区审计，不改变同一次创建的语义哈希。
模型生成的 `narrative_projection` 同样不进入事实语义哈希；它单独记录 `projection_hash`、模型与投影
策略版本，并反向绑定不可变的 `plan_hash`。稳定 ID、幂等键和事实节点只能由结构化创建输入派生，不能由
措辞派生；成功提交后只保留最终对象 ID 与摘要，不保留可重算这些对象的输入。

年龄直接使用地球年龄口径。程序按物种生命周期生成整数 `age_years_at_adoption`：在 Elfaria 生活了 5 年，
就按 5 岁理解，不再把 196 个本地日、40 小时本地日换算成另一套年龄。候选展示的年龄在接受后保持不变；
以后每经过一个地球年增加一岁。`adoption_anchor_at` 只用于稳定计算当前年龄。界面需要生日时可以从年龄
生成明确标注为“年龄投影”的日期，但它不是 Elfaria 的精确历史生日，也不能写进个人亲历。

### 3.2 确定性生成顺序

程序按以下因果顺序生成，后一步只能读取前一步已经确定的事实：

1. 根据用户偏好生成候选核心；用户已选物种必须保持一致，生命阶段、性别或外貌若选择 `any`，则在各候选中确定实际值，不把 `any` 写入候选。
2. 在候选核心内按物种生命周期和年龄分布生成地球口径的 `age_years_at_adoption`、人格和外貌，用户接受后全部冻结在 `AcceptedGenesisReservation`。
3. 按物种、出生时期和区域人口权重选择出生宏观区域。
4. 按聚落占比、适生单元和密度权重选择出生聚落及有效地点；不得在整个多边形内均匀撒点。
5. 在出生地和物种允许范围内生成家庭与照护结构。
6. 按年龄、地点、家庭和设施可达性生成学习、学徒和知识接触路径。
7. 按年龄、学习经历、地方劳动结构和家庭传承生成职业；人格只能在已经可行的选项之间作有限权重调整，
   外貌不得参与；未到适龄者显式为学习或无职业状态。
8. 根据出生地、职业和路线成本生成迁居、当前居住地、常走路线和实际到访地点；出生地不等于出发前住处。
9. 对已经通过 `EarthArrivalRules` 资格门的候选，无条件加入必修培训、准备、出发和抵达上下文；个体只在培训细节、联系人和主观反应上存在差异。
10. 执行地点、年龄、职业、设施、时间和引用完整性校验，失败则整份 LifeContext 不得发布。

每一步只能从满足后续硬约束的可行集合中选择。若局部选择仍导致无解，使用稳定 `attempt_id` 做有界
回溯；穷尽后返回带理由码的 `UNSATISFIABLE`。同一未完成事务恢复得到同一结果或同一失败，不能无限换 Seed，
也不能让模型补造家庭、职业或地点。

所有条件关系都必须在阶段 2 明确声明。程序不能从模型常识或地球人口经验自行推断“某种性别、外貌、
物种或家庭更适合某种职业、阶层或地区”；未获世界资料支持的相关性一律不存在。外貌只影响虚拟形象，
人格也只能在已通过年龄、地点、学习和能力硬门的选项之间作有限权重调整。

公开区域、聚落和机构引用 `PlaceCatalog`，居民可理解的路线引用 `RouteCatalog`；隐藏路径、坐标和成本
不得写入 Memory。家庭住所、小作坊等只属于这只 Elfie 传记的地点，可以从
已批准原型确定性实例化为 `private_place_id`，但必须挂在一个公开父地点下，并使用预分配的 Genesis
私有命名空间；最终 ID 随对应 Memory 对象保存，最小 `GenesisCommitReceipt` 只记录输出对象 ID/摘要。
它们不是新的公共地理 Canon，也不能被另一只 Elfie 因同名自动共享。

所有随机选择使用从 `master_seed` 派生的命名子 Seed，例如：

```text
candidate / age / birth_region / birth_cell / household
learning / vocation / residence / mobility / relationships / episodes
```

`GenerationPolicy` 按 age、origin、household、learning、vocation、mobility、relationship、episode、
knowledge 等领域分别版本化。子 Seed 由稳定标签和对应领域策略版本派生，不依赖函数调用顺序；包的总
版本号不直接参与所有随机分支。以后新增一个职业选项不能改变已经确定的出生地、家庭或人格；只有相关
目录或领域策略版本变化时，对应分支才允许变化。

Seed 派生算法、伪随机算法和加权选择算法本身也必须有版本号；禁止使用进程随机哈希、无序容器遍历
或未记录的运行时默认行为。一次未完成事务的恢复必须复用预约中的 `adoption_anchor_at`，不能拿“现在”
替代；已提交 Elfie 不提供 Genesis 重放入口。

阶段 3 完成后必须满足：所有地点可居住、所有家庭和职业符合年龄、全部引用有效、没有把隐藏人口总数
或坐标变成个人知识，并且同一未完成事务恢复得到相同哈希。

## 4. PersonalGenesisPlan：编译个人知识、人物与经历

阶段 4 的创建期编译输出为：

```text
PersonalGenesisPlan
├── profile_plan
├── selfhood_plan
├── personal_knowledge_manifest
├── relationship_plan
├── episode_skeletons
└── final_owner_commit_plan
```

这些结构只在创建期决定最终值，本身不是提交后的事实所有者。`profile_plan` 只能复制契约白名单内的
客观身份、稳定年龄/出生锚点、不可变个人来源 ID/冻结标签和最终虚拟外貌；`selfhood_plan` 从已冻结人格
锚点生成受控表达、价值和自我认识。Episode 可以解释或强化某些倾向，但不能反向改写已被用户选中的
人格，也不能为每个性格特征强造一段决定性童年原因。

### 4.1 个人知识编译

知识编译器只接收 `KnowledgeCatalog + EarthArrivalRules + LifeContext + GenerationPolicy`，不接收
造物者世界全文。每个原子依次经过：

```text
居民可见性
→ access 硬门
→ exposure 接触机会
→ 掌握程度与安全表达变体
→ 获取来源
→ 最终 Memory 记录的参数
→ 前置知识闭包
→ 覆盖与泄漏校验
```

个人知识把“掌握多少”和“凭什么知道”分开：

| `mastery_level` | 允许进入 Memory 的内容 |
| --- | --- |
| `full` | 可以独立说明的安全完整版本 |
| `partial` | 只包含真实掌握部分的删减版本 |
| `reference_only` | 只知道应向谁、到哪里或查什么记录，不拥有答案本身 |
| `none` | 不生成语义 Memory，也不向模型暴露 |

`epistemic_kind` 另行记录 `lived_observation / taught / documented / hearsay / myth /
unknown_boundary`。因此可以同时表达“只听说了一部分”；未知边界是经过审阅的知识原子，不是掌握等级。
被 access 拒绝的 `none` 只留在临时 DecisionTrace。

`PersonalKnowledgeEntry` 至少记录：

```text
knowledge_id
mastery_level / epistemic_kind / statement_variant_id
topic_ids / aliases / compiled_search_terms / recall_eligible
acquired_via / acquired_stage / acquisition_ref
consultable_target_ids
confidence_class / initial_confidence
importance_class / initial_importance
memory_admission_kind / bounded_salience_signals
related_ids / prerequisite_ids
```

资料包版本、策略版本、`access_rule_id/exposure_rule_id/decision_reason_ids` 只属于临时
`KnowledgeDecisionTrace`，不得进入最终 Memory。

个人条目只携带已选 statement 变体对应的别称和检索词。它们仅供 Memory 建索引，不进入事实正文、
`RecallBundle` 或模型上下文，也不能让 `partial/reference_only` 间接获得完整答案。

`personal_knowledge_manifest` 可以在创建工作区保留临时 `KnowledgeDecisionTrace`，用于解释某个原子为何
被排除、降级或由 Episode 获得；成功提交或终止失败后必须和 Plan 一起删除，不成为精灵能够回忆的内容，
也不能进入长期技术回执。

语义记录的三个参数由版本化算法产生，但按最终记录类型归属：

- `Confidence` 只属于 Node 的身份解析和 Assertion 的命题可靠性，不属于 Episode；知道多少由 `mastery_level` 表示。
- `Importance` 来自身份、家乡、物种、职业、安全、关系和故事相关性，不由模型评价。
- `Retention` 不由 Genesis 或模型直接选择。Genesis 只提供已注册的记录类型、来源类别和有界
  显著性信号；Memory 的版本化准入策略据此解析 `retention_profile` 与初始
  `half_life_days`。

现行 Memory 策略中，经授权的 Genesis 记录统一获得 `retention_profile=genesis` 与
`half_life_days=3650`。这是十年半衰期，不是永久保存或预定删除日；运行时 Freshness 按
`F=2^(-t/H)` 派生，不在 Genesis 中另存会过期的分数。若未来要区分不同 Genesis 半衰期，必须先升级
Memory 准入策略及其契约，不能由 Genesis 绕过策略直接写数值。

全体常识表示所有居民都有接触资格，不表示每个人都完整掌握。身体固有经验、核心身份和赴地课程可以
设置初始掌握下限；普通常识仍由接触频率、年龄和学习路径产生差异。专业知识必须通过职业、学习、机构
或实际经历硬门，不能只靠较低概率随机获得。运行时硬安全规则不能依赖 Elfie 是否记得课程，由对应
Runtime 安全边界强制执行；Memory 只保存 Elfie 自己实际掌握的课程知识。

每个知识原子使用由 `master_seed + knowledge_id + policy_version` 派生的独立 Seed，目录排序或新增无关
知识不能重排已有选择。前置知识闭包只能补齐本来具备 access 或由同一合法经历获得的前置项；否则必须
取消高级知识，不能为了满足依赖而把不可接触知识强塞给个体。`reference_only` 必须带
`consultable_target_ids`，且目标人物、机构或记录真实可达。

个人知识不使用一个全局 Importance Top-N 截断。选择由 access、exposure、掌握下限和前置关系决定，
再用分范围覆盖门防止遗漏核心身份、安全与赴地边界；未选原子和无必要的未知项不写入 Memory。

传统和神话要把“居民确实流传这种说法”与“说法中的事件客观发生过”拆开：前者可以高置信，后者按
公共证据保持不确定。个人故事不能把传闻自动升级为亲历。

### 4.2 人物与关系计划

关系生成器先根据 LifeContext 确定槽位，再实例化人物。槽位来自家庭、邻里、学习、职业、地方公共生活、
赴地培训和地球领养关系；不是每只 Elfie 复制同一组固定角色。

`PersonPlan` 至少包含：

```text
person_id / generated_name / species_id / age_band_at_genesis
home_place_id / vocation_id / competency_ids
relationship_role / familiarity_at_genesis / trust_at_genesis / importance
shared_context_ids / eligible_episode_theme_ids
source_ref / version
```

名字由 `NameRules` 确定性生成并去重，模型不能创建或修改人物名。`GenerationPolicy` 按生命阶段规定
有意义的人物数量，通常为 10～20 个，其中 3～5 个高显著人物、1～2 个反复出现在多段经历中；不能为
凑数量制造不符合年龄的职业关系，弱关系也不强行写入 Episode。

领养前人物 ID 使用 `elfie_namespace + relationship_slot_id` 派生，只在本次 GenesisBundle 内表示同一人；
名字相同不能触发跨 Elfie 合并。领养家庭引用使用外部已存在的家庭/联系人 ID，不伪装成领养前人物。
只有未来经过批准、拥有独立权威 ID 的公共角色才可以跨 Elfie 引用；当前本地生成的亲友全部是私人角色。

每个关系槽位使用由稳定槽位 ID 派生的独立 Seed；增加一种无关关系原型不能重排已有家庭、导师和朋友。

校验必须证明人物与 Elfie 在相应时间和地点有接触可能，年龄与角色合理，导师具备相关知识，家庭关系
符合世界设定，并且不同人物没有因重名或复用 ID 被错误合并。

知识编译采用两遍确认：第一遍可以产生待解析的咨询槽位；关系和机构生成后，第二遍只保留能解析到
合格 `competency_ids` 或机构记录的 `reference_only` 条目，解析失败的条目降为 `none`。

### 4.3 经历骨架与知识回流

每只 Elfie 生成 3～5 段关键经历。主题从 `EpisodeThemeCatalog` 中按 LifeContext 选择，可以覆盖归属、
照护、第一次责任、学习与失败、合作、分歧与修复、职业里程碑、旅行、赴地决定、告别和抵达；不要求
每只 Elfie 使用同一组主题。

`EpisodeSkeleton` 至少包含：

```text
episode_id / episode_slot_id / theme_id / temporal_order / life_stage
age_years_at_event / duration_band
place_ids / person_ids
goal / obstacle_class / event_facts / outcome
feeling_range / long_term_impact
relationship_before / relationship_delta
knowledge_before_ids / knowledge_acquired_ids
predecessor_ids / causal_links / forbidden_fact_ids
source_ref / version
```

生成顺序固定为：

```text
基础个人知识
→ 人物与初始关系骨架
→ EpisodeSkeleton
→ 经历中真实获得的知识与关系变化
→ 最终个人知识清单和关系计划
→ 语言投影
```

这样避免“故事依赖尚未掌握的知识”和“为了补知识反向编故事”的循环。经历可以成为合法学习来源，
但必须具备相应人物、地点、年龄和事件；不能借一段故事越过专业知识硬门。

所有 Episode 必须发生在当前年龄之前或抵达时，`age_years_at_event` 必须落在对应生命阶段；
`duration_band` 与前后地点之间的路线时间必须相容。赴地培训与抵达是硬约束，
但它们可以合并进一段经历；离开 Elfaria 的阶段使用这只 Elfie 的实际阶段，不能固定写成成熟期。
全部经历至少形成一条“过去经历 → 后续选择或关系”的因果链，并复用至少一个高显著人物。

每个 `episode_slot_id` 分别派生主题选择和事实实例化子 Seed；增加一个无关主题不能重排已有经历。
Episode 中生成的人名、小地点、物件和局部事件只在该 Elfie 的私人记忆中成立，不能被提升为公共历史、
新地理、物种规律或另一只 Elfie 的共同过去。

Episode 使用版本化的 Importance 与 Retention；它本身没有 Confidence。Episode 中形成的事件命题和
最终关系分别物化为带来源 Evidence 的 Assertion，再计算各自的 Confidence、Importance 与 Retention。
关系 Trust 和经历中的情绪强度仍是独立语义，不能替代这些参数；模型措辞不参与评分。

### 4.4 模型的唯一职责：语言投影

程序先从 EpisodeSkeleton 生成确定性规范摘要，作为 Memory 的权威内容。模型只能接收专门的
`NarrativeProjectionInput`；这个白名单类型只容纳：

- 已选中的居民可见知识变体；
- 已确定的人物、地点、时间顺序、事件事实、结果、感受范围和影响；
- 明确允许的感官线索、措辞要求和可引用 `fact_id`；
- 禁止新增事实清单。

模型只能返回每段经历的自然叙述、感受表达和整体 `personal_story` 摘要，不能新增或改变名字、数字、
物种、地点、职业、技术、时间、事件、结果、关系变化和知识。模型看不到造物者骨架、人口权重、精确
坐标、Seed、未选知识、邀请原文或其他 Elfie 的计划；实现也不能把 LifeContext 或完整 Plan 直接序列化
给模型。

模型按 `episode_id/fact_id` 返回句子，程序校验实体、数字、引用和禁止项；任意自由文本都不能被证明与
结构化事实完全等价，因此它永远不是事实权威。通过校验的措辞若被采用，就作为对应 Episode 的第一人称
Memory 内容与结构化事实、Evidence 一起提交；否则直接使用规范摘要。它不形成独立的长期展示资产。
模型/投影版本和 `projection_hash` 只存在于未提交创建工作区；事务内重试复用已生成草稿，成功提交后
草稿随 Plan 删除，运行时只看到最终 Memory。

## 5. GenesisBundle、持久化与运行时边界

阶段 5 把已校验计划转换为现有 Genesis 语义边界：

```text
ProfileDraft
SelfhoodSeed
KnowledgeSeed[]
RelationshipSeed[]
EpisodeSeed[]
GenesisCommitReceipt（最小技术回执）
```

最终所有权固定为：

| 内容 | 最终所有者 | 不得混入 |
| --- | --- | --- |
| 技术 Schema 修订、稳定 ID、最终名字、正式物种、适用时的固定性别、稳定年龄/出生锚点、不可变个人来源 ID/冻结标签、最终虚拟外貌 | Profile | 世界知识、资料包/生成来源、问卷、Seed、人物关系、传记、人格、能力/权限/预算、当前身体或运行态 |
| 人格锚点、价值、表达、身份认同和自我认识 | Selfhood | 问卷答案、资料包/策略/Seed 绑定、世界知识、个人 Episode 全文 |
| 个人已知知识、人物关系、领养前经历及来源证据 | Memory | 生成器权重、未选知识、模型猜测 |
| Elfie/预约 ID、幂等键摘要、最终所有者 Schema 修订、输出对象 ID/摘要、编译器修订、完成状态和时间 | GenesisCommitReceipt（Profile 外） | 问卷、世界知识、资料包/策略绑定、Seed、LifeContext、Plan、模型草稿或可重建人生的信息 |
| 最终采用的第一人称叙述 | 对应 Episode Memory | 独立展示资产或第二份事实副本 |
| 候选接受、额度和发布状态 | Adoption / Admission 持久记录 | 精灵记忆和模型 Prompt |

`master_seed`、子 Seed、问卷/选项、资料包与策略绑定没有提交后的所有者。当前 Profile 或其他持久对象
若仍保存这些字段，属于实现偏差，必须迁移删除，不能把旧 Schema 当作继续保留它们的理由。

Memory 的一次 Genesis submission 在自己的 Unit of Work 内原子提交，但 Profile、Selfhood、Memory、
领养关系和 Runtime 不伪装成一个跨存储事务。App 使用可恢复的发布状态机：

1. `AcceptedGenesisReservation` 以 `reserved` 状态冻结最终候选身份、额度和幂等键；资料包、策略、Seed 与输入摘要只在同一私有创建工作区的 `GenesisCompileEnvelope` 中存在。
2. 在同父目录的未发布工作区构建 Profile、Selfhood 和 Memory；Memory 只在全部预期记录与 completion marker 同一提交成功后可见。
3. 重开整包并校验引用、年龄、因果、知识权限和输出哈希；成功后把临时工作区原子改名为最终工作区，并把 Admission 状态推进为 `committed`。
4. 只有 `committed` 记录可以被产品入口列出和恢复；Runtime 注册在持久提交之后执行，失败时只从 Profile、Selfhood、Memory 和必要运行态恢复。
5. 崩溃恢复只处理仍未完成的同一预约；有效最终工作区可以补完 `committed`，无效结果必须清理并释放预约额度；不同摘要复用同一幂等键必须拒绝。
6. `committed` 或终止失败落定后，删除预约、CompileEnvelope、LifeContext、Plan、问卷、Seed、资料绑定和模型草稿，只留下最终所有者与最小 `GenesisCommitReceipt`。

Memory 参数按最终记录类型传递，不能给三类 Seed 机械套同一字段：

| 输入 | 最终参数 |
| --- | --- |
| `KnowledgeSeed` | 知识 Node/Assertion 各自的 Confidence、Importance；Memory 解析 Retention |
| `RelationshipSeed` | 人物 Node 与关系 Assertion 各自的 Confidence、Importance；Trust 单独保存；Memory 解析 Retention |
| `EpisodeSeed` | Episode 的 Importance；Episode 本身没有 Confidence；Memory 解析 Retention |
| Episode 内事件命题 | 派生 Assertion 的 Confidence、Importance，并保留 Episode Evidence；Memory 解析 Retention |

物化层只能校验和保存编译结果，不能用 Trust、情绪强度或任意默认值重新猜测。Memory 返回的
`half_life_days` 使用 UTC 24 小时日，与 Elfaria 年龄口径无关。

这里的 `genesis` 是 Memory 的事件来源类别，不等于可重建创建过程的资料绑定、永久保留承诺或预定删除日期。Memory 的准入合同必须接收经过范围校验的逐项
类型、来源类别与有界显著性信号，同时继续标记 Genesis 来源；`retention_profile` 和
`half_life_days` 只由 Memory 返回并持久化，Genesis 不得绕过 Memory 直接改库。Profile 正式承载
`age_years_at_adoption + adoption_anchor_at`；若旧界面仍需要 `birth_at`，只能把它作为年龄显示投影，
不能把投影日期写成 Elfaria 的精确亲历。

规范化领养选择、原始问题答案、被接受候选的生成输入、资料包/策略绑定和 Seed 均不进入 Profile、
Selfhood、Memory 或长期回执。若邀请原文由产品另行保存，它仍归领养/通信证据所有；Memory 只保存实际
发生的邀请、接受、抵达或领养事件，不复制创建参数。已提交 Elfie 不要求保留旧
`GenesisSourcePackage`，也没有“按旧包重放人生”的恢复路径。

### 5.1 运行时知识路径

Genesis 提交后，Reasoning 只能通过正式链路获得初始知识：

```text
Selfhood ───────────────────────────────┐
source-first Memory → bounded RecallBundle ├→ Brain / Reasoning
当前 Brain 状态与本轮权威输入 ──────────────┘
```

只有 `recall_eligible` 的 Episode、Node、Assertion 与 Evidence 可以进入 `RecallBundle`。创建回执、
CompileEnvelope、Seed、生成权重、DecisionTrace、未采用草稿和未选知识都不可召回。普通 Brain 不读取
Profile、GenesisSourcePackage、造物者骨架或居民公共知识文档；Reasoning 也不能用模型
训练中的地球常识补写 Recall 中缺失的 Elfaria 事实；没有可靠召回时按未知、听闻或需要请教回答。

Genesis 只提供领养前历史和已经完成的抵达事实。没有当前 Orientation、感知、工具结果或动作/通信回执时，
当前位置、天气、当天活动、正在进行的动作以及其他 Elfie 的状态一律未知；历史地点和旧 Episode 不能被
推断成当前状态，模型也不能补写。

## 6. 完成门与系统性校验

设计实现后必须以全部已发布的“物种 × 允许生命阶段”和多个固定 Seed 组成生成矩阵。以下门禁全部是硬门：

| 校验域 | 必须证明 |
| --- | --- |
| 来源与覆盖 | 阶段 0→1→2 双向覆盖无未分类项；每条个人知识和每个生成权重都有已发布来源 |
| 隔离 | 生成器专用字段、未选知识、其他 Elfie 数据和未分配的赴地课程内容不会泄漏到模型或 Memory |
| Profile | 只含契约白名单内的冻结外部客观档案；不含世界观、问卷、Seed、生成来源、人格、能力、关系、经历或运行态 |
| 隐私 | 邀请原文和完整临时人生包不进入模型、最终所有者、长期回执或普通日志；诊断只暴露脱敏 ID、理由码和哈希 |
| 预约与确定性 | 候选接受只产生一个冻结预约；同预约、同版本和同 Seed 的 LifeContext、事实 Plan、输出 ID 和语义哈希完全一致 |
| 用户输入 | 物种、实际阶段、性别、外貌和人格与最终候选一致；`any` 不会成为身份值；未注册扩展输入会被拒绝 |
| 时间 | Elfaria 年龄与地球年龄一对一；Episode 年龄、持续时间以及出生、迁居、培训、出发和抵达顺序成立 |
| 空间 | 出生点可居住，家庭、学校、职业、路线和人物接触在地图与通行成本上成立 |
| 空间权威 | Elfaria 历史生成地图不成为 Nest/Godot 当前空间权威；私人地点只在本 Elfie 命名空间成立 |
| 条件公平 | 所有身份到地区、家庭、学习和职业的相关性均有显式规则来源；没有地球常识或模型偏见暗中参与 |
| 知识 | topic/alias 索引可重建，access、exposure、掌握/来源双轴、召回资格、前置闭包、咨询目标、专业硬门和赴地培训下限全部成立 |
| 关系 | 人物 ID 唯一、角色和年龄合理、1～2 人跨 Episode 复现、同名不合并、私人关系不跨 Elfie 共享 |
| 经历 | 3～5 段经历、至少一条因果链、结果与关系变化一致、没有固定模板强套全部年龄 |
| 记忆参数 | Episode 无 Confidence；Genesis 生成 Node/Assertion 的 C/I 与 Episode 的 I；Memory 策略独占解析全部 R/H，物化层不覆盖 |
| 模型 | 模型只接收白名单投影输入；失败时使用规范摘要；采用的措辞只附着于对应 Episode，不形成第二事实源或独立资产 |
| 运行时 | 身份人格只来自 Selfhood，初始知识只经 Memory → `RecallBundle` 进入 Reasoning；Profile、资料包、创建回执、排除知识和地球先验不能成为旁路；无当前权威时保持未知 |
| 提交 | Memory submission 原子，Admission 可恢复，半套初始化不可见，事务内重试幂等，目录升级不覆盖既有 Elfie；成功或终止失败后创建输入全部删除 |
| 断源恢复 | 删除创建工作区和被引用的旧资料包后，已提交 Elfie 仍能只靠 Profile、Selfhood、Memory 与必要运行态恢复；最小回执不能重建人生 |
| 模块所有权 | LifeContext、知识过滤、人物、关系与故事只由 `elfie/genesis` 生成；App 只协调，Infrastructure 只加载/保存强类型值 |

验收不能只比较节点数量。至少要直接检查生成的 LifeContext、个人知识选择理由、关系图、Episode 因果、
最终 Memory/Recall 内容和模型不可见字段，并用反事实输入验证硬门，例如不合年龄的职业、未到访地区知识、
无培训抵达、普通居民掌握受限技术、出生在不可居住单元、模型新增陌生人物、目录在候选展示后被替换，
以及进程在工作区发布各阶段崩溃后重试。

## 7. 精细化对抗审查结论

| 攻击点 | 如果不处理 | 本设计的收束 |
| --- | --- | --- |
| v0.1 与 v0.2 同时被当作基线 | 两份规范冲突且旧验收被冒充为新实现 | v0.1 冻结为历史快照，v0.2 是唯一现行目标；实施另立工作项 |
| 上游知识静默漏转 | 精灵知识看似合规但残缺 | 阶段 0→1→2 使用稳定 ID 和双向 CoverageManifest，未分类即不能发布 |
| 候选展示后目录或身份变化 | 用户选中的候选与最终人生错配 | Reservation 冻结最终候选；同一私有工作区的 CompileEnvelope 冻结资料包、策略、Seed 与时间，提交后两者一起删除 |
| 随机选择走入死路 | 同一 Seed 永远失败或被迫由模型补洞 | 只从可行集合选择，稳定有界回溯，穷尽后返回 `UNSATISFIABLE` |
| 异星年龄换算过度复杂 | UI、Profile 和故事年龄互相打架 | Elfaria 几岁就按地球几岁，保存领养时年龄与锚点，不换算本地日 |
| 隐藏地图或路线泄漏 | 精灵获得坐标、人口权重或求解成本 | Place/RouteCatalog 只给居民表达，SpatialPopulationModel 只供生成器 |
| Episode 被错误赋予 Confidence | “记得清楚”被当作“所有命题可靠” | Episode 只有 I；Node、Assertion 才有 C/I；全部记录的 R/H 由 Memory 策略解析，Trust 和情绪另存 |
| 模型看到完整 Plan 或直接写事实 | Seed、未选知识和新事实进入故事 | 白名单投影输入；规范事实为权威；采用的措辞只成为对应 Episode 的表达，不另存展示资产 |
| 跨存储发布中途崩溃 | 出现孤儿工作区、重复额度或半只 Elfie | Memory 内原子提交，App 用持久 Admission 状态机恢复，Runtime 最后注册 |
| Reasoning 绕过 Memory 使用地球先验 | 初始化正确但回答仍被训练常识污染 | 唯一知识路径为 Memory → `RecallBundle` → Reasoning，缺失即未知 |
| 新目录自动刷新旧 Elfie | 已有记忆被后台改写 | 已提交 Elfie 与资料包彻底断开；旧 Elfie 变更只能经最终所有者的独立行为 |
| 问卷、Seed 或资料绑定被长期保存 | Profile/回执变成第二份生命事实源，可以重造或改写同一 Elfie | 创建输入只在未发布工作区存在；提交或终止失败后销毁，最小回执不可重建人生 |
| Infrastructure 生成知识、人物或故事 | 技术 Adapter 夺取 Elfie 生命语义并形成第二条生成路径 | `elfie/genesis` 独占语义编译；App 只协调，Infrastructure 只加载/保存强类型值 |

按版本权威、身份冻结、知识完整性、模型权限、Memory 语义、发布恢复和运行时加载七个大面复审后，
本文没有保留会改变主流程的严重结构问题。物种/生命阶段资格、概率、评分、原型内容和数量权重仍需作为阶段 2 的
版本化数据人工确认；它们不能由模型或实现者临场决定，但不再改变六阶段结构。

实施前仍需更新受影响的实现类型：`SourcePackageManifest` 与 Knowledge 检索元数据、
`AdoptionSelection` 扩展注册、创建期 `AcceptedGenesisReservation/GenesisCompileEnvelope`、严格 Profile
白名单、各 Seed 到最终 Memory 记录的 C/I 映射、Memory Retention 准入元数据、最小 `GenesisCommitReceipt` 与
创建输入销毁协议。规范性合同已经由 ADR-0033、Elfie 2.3、Brain 1.5、Application 1.11 和
Configuration 1.4 冻结；本文不表示代码已经落地。
