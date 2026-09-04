# Genesis 核心内核 v0.2 迁移执行计划

> **状态：** v0.2 功能迁移执行基线已确认
> **目标设计：** [`genesis-core-kernel-design-v0.2.md`](genesis-core-kernel-design-v0.2.md)
> **当前基线：** `HEAD=24f2ae6d9db4c1c46c79e69af8074a9a359597d7`；该提交已包含当时的
> `origin/main=222268db89465b957b57af3813fb8ec5ee890a1b`
> **历史关系：** v0.1 是冻结历史，v0.2 是它的直接迁移目标；本文不是第三套设计，也不把
> v0.1 和 v0.2 变成两条可运行流水线。

## 1. 先给结论

这次应按“原位迁移”执行，不应从头新建一个 Genesis 系统再与今天的实现并存。当前代码已经
有可以保留的骨架：

- `elfie/genesis/engine.py` 中的确定性候选生成、人格和外貌算法；
- `elfie/genesis/initializer.py` 中的 Memory `genesis_submission` Unit of Work、来源优先
  写入和现有 Retention 解析；
- `app/features/adoption/` 中的候选会话、领养输入校验和配额 Port；
- `app/orchestration/resident_admission/` 中的跨边界编排接缝；
- `infrastructure/persistence/elfie_workspace/` 中已经存在的 Profile、Selfhood、Memory
  和资产保存 Adapter。

需要迁移的是这些职责的位置、数据生命周期和唯一入口，而不是再实现一份同功能代码。最终只
允许下面这条生产路径：

```text
CreatorWorldSkeleton
  -> ResidentKnowledgeBaseline
  -> published GenesisSourcePackage
  -> AdoptionSelection / AcceptedGenesisReservation
  -> LifeContext
  -> PersonalGenesisPlan
  -> GenesisBundle
  -> Profile + Selfhood + Memory
  -> committed Admission
  -> Runtime registration
```

其中前三项是创建前的资料链；`Profile`、`Selfhood` 和 `Memory` 是一次性提交后的最终所有者，
Admission 与 Runtime 只负责发布和注册。创建成功后，Elfie 不再从
世界资料、问卷、`LifeContext`、Plan 或 Seed 恢复；普通 Brain 只走 `Selfhood + Memory +
当前状态`。这是 v0.2 的核心效果，也是本计划的完成定义。

本次实现采用以下已经确认的开发假设：

1. 当前已经整理的阶段 0/1 世界资料作为 `v1` 输入冻结。实现只负责把它们补成稳定 ID、覆盖
   关系和机器目录，不临场新增世界事实；日后内容修订发布新的资料版本，影响未来创建，不回写
   已提交 Elfie。
2. 在 0.5 之前不做旧数据兼容、备份迁移或双 Schema。实现直接切换到新 Schema/新路径；旧开发
   数据可以重建并不再作为代码约束。实际数据根不在本次工作中被直接删除。

本轮计划文档已经写入；从这里开始按它执行功能迁移，不另立平行实现。

## 2. 不可违反的迁移规则

### 2.1 “不产生两个实现”具体指什么

下列情况才算真正的双实现或第二事实源，必须禁止：

- 同一候选、个人知识、关系或经历同时由旧函数和新函数决定；
- 同一身份同时由 Profile、`nest.db.elfies` 和某个 Genesis Manifest 作为可变权威；
- 同一创建请求可根据开关、随机分流或异常 fallback 走旧/新 Genesis；
- 同一对象同时双写旧表和新表，或先读新表失败再读旧表；
- 保留旧 `GenesisBundle` 校验分支、旧 Memory 提交器或旧 Workspace Materializer 让旧
  调用方继续工作；
- 测试只验证新建的“样板实现”，而产品入口仍调用旧实现。

下面这些并不构成竞争的运行时事实，但必须明确边界：

- 造物者文档、居民知识文档和机器目录可以同时存在，因为它们是有方向的上游产物；只有
  已发布的 `GenesisSourcePackage` 能被创建运行时读取，覆盖关系只用于审查；
- Profile 与 Selfhood 在创建时可以共同保存最低限度的身份快照，但提交后不互相同步，也不
  互相派生；
- 未完成事务可以有一个受限的暂存输出和最小技术回执，但回执不能重建人生，事务结束后输入
  必须销毁。

### 2.2 每个迁移批次的硬退出条件

每个批次都必须在同一个可交付检查点完成以下动作：

1. 盘点旧符号、路径、Schema 字段和所有直接/动态调用方；
2. 把现有实现移动或收窄到目标 owner，必要时只做等价搬迁；
3. 切换所有生产调用方、装配点和测试夹具；
4. 删除旧符号、旧路径、旧字段和兼容分支；
5. 用递归引用扫描证明旧入口已无生产引用；
6. 只对当前唯一生产路径运行聚焦测试。

凡是改变可观察行为、持久化或跨边界契约的批次，先在现有接缝上写出能准确失败的测试，再做
最小迁移；纯搬移/重命名可以复用现有测试，但不能借此跳过边界扫描。

不允许先把新系统做完、保留旧系统兜底，再拖到以后删除。需要暂存配置或中间输出时，只能
放在根 `build/` 或未发布事务工作区，不能登记为运行时配置、共享事实或第二入口；进入下一个
可交付检查点前必须被消费或删除。

大批次可以拆成多个本地提交，但每个提交都必须是单路径可运行的迁移检查点：若需要新类型，
它必须在同一切换中接管旧类型并删除旧导出；若需要新 Schema，空开发数据上的新 Schema、
全部调用方和旧字段删除必须一起切换。测试阶段可以短暂处于未完成的工作树，但不能把“新旧
同时可运行”的状态交付、部署或作为下一批次的基线。

### 2.3 迁移中的责任边界

| Owner | 只做什么 | 明确不做什么 |
| --- | --- | --- |
| `elfie/genesis` | 读取强类型创建资料，确定性编译 LifeContext、知识、人物、关系、经历和最终草稿 | 不读写 SQLite/文件，不管理运行时会话 |
| `app/features/adoption` | 收集和规范化用户输入，管理候选会话和接受动作 | 不生成个人故事，不写 Profile/Memory |
| `app/orchestration/resident_admission` | 预约、提交、恢复、补偿、清理和 Runtime 最后注册 | 不选择知识、人格、地点、人物或故事 |
| `infrastructure` | 加载/校验已发布资料包，保存已经编译好的强类型结果 | 不编译生命语义，不补默认事实，不调用模型决定内容 |
| Profile | 对外可见的冻结客观身份档案 | 不存世界观、Canon、人格、能力、关系、经历、Seed 或来源账本 |
| Selfhood | 内部人格、自我认识和身份认同 | 不保存问卷、世界资料或完整个人经历 |
| Memory | 个人实际知道的知识、人物、关系、经历及证据 | 不保存生成权重、未选知识或可重放输入 |
| Nest/运行时目录 | 所有权、居住锚点、运行状态等巢内关系/状态 | 不重新拥有 Profile 身份事实 |

### 2.4 发现架构差异时的停工门

本计划只执行已经由 v0.2 设计、ADR-0033 和现有系统架构契约确定的 owner 与依赖方向。若实现
过程中发现必须改变顶层模块所有权、Runtime/Gateway authority、跨层依赖方向或系统级 Port
语义，不能把它悄悄塞进某个迁移批次；应先停在该批次，另立双语治理 ADR 和机器门禁变更，
再恢复产品迁移。普通类型收窄、文件拆分、调用方改名和等价 Adapter 搬移不触发这个门。

## 3. 当前实现到目标的映射

| 当前接缝 | 当前问题 | v0.2 迁移动作 | 迁移后唯一 owner |
| --- | --- | --- | --- |
| `GenesisEngine`、`personality.py`、`appearance.py`、`selection.py` | 算法可复用，但策略和部分常量硬编码，年龄仍以月为主要形状 | 保留算法并改为读取 `GenerationPolicy`，把候选核心和实际年龄收窄为类型化输出 | `elfie/genesis` |
| `AcceptedAdoptionReservation` | 携带人格、Seed、完整候选、故事和过多生成输入 | 原位收窄/重命名为 `AcceptedGenesisReservation`；原始答案只在事务内存在 | Adoption/Admission 临时事务 |
| `_candidate_registry.py` | 领养流程调用强模型生成名字和个人故事；临时构造 Profile | 名字由 `NameRules` 确定；候选回复不再让模型决定事实；删除临时 Profile 构造 | Adoption 收集输入；Genesis 编译 |
| `AdoptionService.prepare_accepted/publish_accepted` | `prepare` 产生宽预约，`publish` 直接写重复身份表 | `prepare` 只冻结接受结果；最终发布并入 Admission 状态机 | Admission + Adoption 关系记录 |
| `FinalElfieWorkspaceAdapter.materialize` | 在 Infrastructure 中加载 Canon、决定知识/名字/关系/经历并直接建最终目录 | 把现有语义 helper 逐个移动到 Genesis；Adapter 只暂存/校验/保存编译结果 | Genesis 编译器；Infrastructure 持久化 |
| `_selfhood_seed`、`_genesis_bundle`、`_initial_*_seeds` | 语义代码与文件写入耦合，且硬编码固定知识和五段故事 | 物理移动后改造成 `LifeContext`/`PersonalGenesisPlan` 编译步骤；旧 helper 同批删除 | `elfie/genesis` |
| `GenesisBundle.validate` 的 legacy/compatibility 分支 | 新旧 Bundle 可同时通过，形成第二条 Memory 入口 | 所有调用方改到 v0.2 typed Bundle 后删除旧类型和分支 | `elfie/genesis` + Memory Port |
| `GenesisMemoryCommitter` | 同时有 legacy 和 typed 提交路径；Manifest 记录可重放输入 | 保留现有 Memory UoW/Retention，合并为一个 typed source-first 路径；只留最小 receipt | Memory 提交边界 |
| `ElfieProfile`、`ProfileProvenance`、`EmbodimentProfile`、`ElfieOrigin` | Profile 保存生成来源、能力、抵达/培训和过宽世界字段 | 按 v0.2 白名单收窄；能力归 Body/运行资产，抵达/培训/历史归 Memory | Profile / Body / Memory 各自 owner |
| `elfie/profile/canon.py`、`ELFARIA_CANON` | 代码中有第二份世界/物种事实，配置 loader 还拿两者互校 | 创建资料改由 SourcePackage 自校验；所有运行期 Canon 引用迁移或删除后删除该文件 | SourcePackage（未来创建唯一来源） |
| `ProfileAnchorSnapshot`、`facade_operations.py` | Selfhood/Facade 以当前代码 Canon 动态刷新 Profile 投影 | 改为 Profile/App 拥有的稳定外部档案 View；不进入 Brain，不刷新 Canon | Profile/App observer |
| `ResidentAdmissionService` | 只有进程内 LRU，先注册 Runtime 再写领养关系，崩溃窗口不可恢复 | 原位改成持久状态机：暂存、重开校验、原子发布、`committed`、Runtime 最后注册 | App Admission |
| `nest.db.elfies` 与各 API 投影 | 重复保存 name/species/gender/birth/summary，页面直接读重复表 | 迁移为巢内目录/所有权记录；页面聚合 Profile、Selfhood、Memory 的 owner 投影；不加 fallback | Nest 关系 + App 聚合 |

## 4. 六个设计阶段在实现中的数据与生产者

这张表是执行时的存储边界。阶段 0/1 的人读文档不是代码运行时的第二知识库；阶段 3/4 的
临时类型也不是已提交 Elfie 的恢复来源。

| 阶段 | 产物与建议格式 | 谁产生 | 何时存在 | 谁可读取 |
| --- | --- | --- | --- | --- |
| 0 | `CreatorWorldSkeleton`：人工确认的 Markdown、地图和受控附件，带 `creator_fact_id` | 人工设计/人工确认 | 长期设计资料 | 内容发布校验、Genesis 包发布流程 |
| 1 | `ResidentKnowledgeBaseline`：四部分人读 Markdown 列表，带 `resident_knowledge_id` | 人工提取/确认，AI 只辅助整理 | 长期设计资料 | 内容审查、目录发布流程 |
| 2 | `GenesisSourcePackage`：`SourcePackageManifest` 加 YAML 成员和引用资产 | 人工配置/发布，程序做 Schema、引用和双向覆盖校验 | 版本化创建资料；仅未来未完成创建使用 | Genesis 创建编译器、Infrastructure loader |
| 3 | `AdoptionSelection`、`AcceptedGenesisReservation`、`GenesisCompileEnvelope`、`LifeContext` | 用户输入 + App 预约 + Genesis 确定性算法 | 未发布创建事务 | Genesis、Admission 恢复器 |
| 4 | `PersonalGenesisPlan`、`NarrativeProjectionInput` | Genesis 编译器；模型只生成受限措辞 | 同一未发布创建事务 | Bundle 编译器、Memory 投影器 |
| 5 | `ProfileDraft`、`SelfhoodSeed`、`KnowledgeSeed[]`、`RelationshipSeed[]`、`EpisodeSeed[]`、`GenesisCommitReceipt` | Genesis 校验并生成；App 编排发布；Infrastructure 保存 | 最终 owner 长期存在；receipt 最小保留 | 对应 owner；Brain 仅经 Selfhood/Memory 正式链路读取 |

阶段 3/4 的完整对象如果需要崩溃恢复，只能保存在同一预约的私有未发布工作区，且结束时
清理。成功或终止失败后必须删除问卷答案、资料包绑定、Seed、LifeContext、Plan、模型草稿和
可重建人生的诊断信息。

## 5. 有序迁移批次

### M0：基线、事实源和数据变更门

**目的：** 在动代码前把“今天的真实调用链”和“允许变更的资料”冻结，避免用旧文档或旧测试
猜目标。

**执行项：**

- 固定当前基线，盘点 `GenesisEngine`、Adoption、Workspace、Memory、Profile、Nest DB、
  API/UI 和 Bootstrap 的直接、动态、脚本入口；
- 对 `docs/.internal/` 中的世界文档分类：只指定一个 CreatorWorldSkeleton 和一个
  ResidentKnowledgeBaseline；其他文档要么归并确认，要么标为历史参考，不能被 loader 注册；
- 不直接把冻结的 v0.1 历史文件当作新的活动事实源；由人工决定是原位升版还是建立明确的
  v0.2 successor，随后只登记一个活动版本。历史文件可以保留供追溯，但不能进入创建运行时；
- 为阶段 0/1 的每个事实补稳定 ID，建立双向 CoverageManifest；缺少人工决定的事实标为
  `deferred`，不由代码补齐；
- 将当前已整理的世界骨架、居民公共知识、季节/天气现象、公共信仰和物种/英雄对应关系视为
  `v1` 内容基线；只补稳定标识和机器映射，不借实现过程修改事实；
- 将旧开发数据视为可丢弃的外部状态：不设计备份迁移、兼容读取或双写；实现和测试直接针对
  新 Schema，实际数据根不由本批次命令删除。

**退出门：** 有一份 v1 活动事实源清单和当前调用方清单；没有新增运行时入口或第二配置源。
内容数值后续可以在新资料版本中修订，不阻塞本次功能实现。

### M1：把创建资料切到唯一的 `GenesisSourcePackage`

**目的：** 先消除代码 Canon 和混合配置，给后续算法提供唯一、可审计的机器输入。

**执行项：**

1. 将阶段 0/1 的稳定 ID 和覆盖关系发布规则落地。人读文档仍按“全体通用、地方与空间、群体
   与专业、公共认知边界”组织；这只是阅读结构，不直接等于机器知识卡片。
2. 优先原位演进已登记的 `config/world/elfaria.yaml`：把它变成 `SourcePackageManifest` 或
   manifest 入口，旧 flat `places/story_events/knowledge` 结构在同一切换中退出；如拆成员文件，
   旧平铺字段和旧 loader 必须同时删除，不能两者都登记。
3. 在现有 `config/` 体系内加入并注册 `KnowledgeCatalog`、`PlaceCatalog`、`RouteCatalog`、
   `SpatialPopulationModel`、`SpeciesLifeRules`、`LifeArchetypeRules`、`NameRules`、
   `RelationshipArchetypes`、`EpisodeThemeCatalog`、`EarthArrivalRules` 和 `GenerationPolicy`。
   `SpatialPopulationModel` 的隐藏坐标、密度/聚落权重和精确人口底数只能给生成器，不能进入居民
   文本或 Elfie；居民只能接触经审查的现象、约数、传闻或公共记录。
4. 让 `infrastructure/persistence/configuration/world.py` 只负责成员解码、Schema、引用、
   hash、发布状态和双向覆盖校验；把语义类型归入现有 `elfie/genesis/world.py`，不在
   Infrastructure 再加一套语义模型。
5. 将现有物种配置拆成 Genesis 创建投影和运行资产/展示投影；二者可来自同一文件包，但不能把
   创建规则塞回 Profile，也不能让运行时资产 loader 反过来成为 Genesis 事实源。
6. 先切断 `ProfileAnchorSnapshot` 和 `facade_operations.py` 对 live `ELFARIA_CANON` 的引用，
   让外部观察面读取稳定档案 View；确认无创建期调用方后删除 `elfie/profile/canon.py`、
   `WORLD_CANON_VERSION` 对照和所有导出。创建期若需事实只能读 package，运行期不能以 package
   替代 Canon 继续刷新旧 Elfie。

**退出门：**

- 只有 `published` SourcePackage 能被候选/Genesis loader 读取；旧 flat loader、代码 Canon、
  旧 hard-coded 校验和旧配置登记均无生产引用；
- 每个阶段 1 ID 与每个目录原子项都有双向映射，未分类项阻止发布；
- 删除/改名创建资料包后，已提交 Elfie 的恢复测试不受影响（该测试在后续 M6 完成，但本阶段
  必须先保留断源设计）；
- 通过配置、Genesis 和架构边界测试后，才允许进入 M2。

### M2：原位收窄候选与接受预约

**目的：** 保留今天稳定的候选算法，把用户输入、随机结果和最终接受结果分成一次性、可冻结的
类型；停止模型在候选阶段决定事实。

**执行项：**

- 保留 `GenesisEngine` 的确定性算法，移除其中重复的世界常量，改从 M1 的 `GenerationPolicy`、
  `SpeciesLifeRules` 和 `NameRules` 读取；不要新建第二个 candidate engine。
- 把 API/领养输入规范化为 `AdoptionSelection`：物种、生命阶段偏好、性别偏好、外貌方向、
  五个相处问题和已注册扩展选项 ID。`any` 只能作为输入偏好，候选输出必须是实际值；未注册
  扩展明确拒绝。
- 将年龄主值改为 `age_years_at_adoption`，按“一年在 Elfaria 生活了几岁，就按地球几岁”
  处理；不再以本地日、196 天或换算月份制造另一套年龄。旧 `age_months` 如仅为 UI 需要，
  只能由年龄投影，不能继续作为核心身份来源。
- 出生地不是从地图多边形内均匀撒点：先按物种允许范围、区域/聚落人口权重和适生单元逐级选择；
  这些权重只影响程序生成，不转成普通精灵知道的总人口或坐标。
- 把 `appearance_seed`、master Seed、原始答案和策略绑定限制在未完成事务；最终外貌保存的是
  已解析结果，不保存可重放生成的 Seed。
- 原位收窄 `AcceptedAdoptionReservation` 为 `AcceptedGenesisReservation`：只冻结接受的
  候选核心/最终显示名、owner、`elfie_id`、预约/幂等信息、领养锚点和事务状态；不携带
  `personal_story`、模型输出、完整 `GenesisCandidate`、Profile Provenance 或可重放输入。
- 候选名字由确定性 `NameRules` 生成，最终显示名由用户的 `AdoptionDecision` 校验。删除
  `_candidate_registry.py` 对 `AdoptionNarrativePort.reveal_many` 的生产调用；候选回复只
  展示结构化、已确定的候选信息和固定产品措辞。在这个切换中一并删除旧的
  `AdoptionNarrativePort`、模型 readiness gate 及其仅服务候选揭示的 Adapter/装配；不要留下
  一个无人调用、却仍可被重新接上的旧事实入口。M3 需要语言投影时，迁移现有模型请求能力到
  Genesis 的受限 Port，不恢复旧 Port 名称或签名。
- 同步切换 Adoption API 的 Python/TypeScript DTO、序列化和页面状态：删除依赖模型故事/揭示
  字段的消费者，避免后端已走新路径而前端仍把旧字段当成事实。
- 删除 `_runtime_appearance()` 为生成候选临时构造 `ElfieProfile` 的做法，直接使用 Genesis
  外貌值或候选展示投影。

**退出门：** 同一候选会话只能接受一次；重复接受返回同一预约或明确拒绝，不重新抽样。候选接口
不依赖模型可用性，模型不可用不会改变身份事实；预约中没有个人故事、Profile Provenance、
原始问卷或永久 Seed。

### M3：把语义编译从 Infrastructure 移到现有 Genesis 边界

**目的：** 这是本次迁移的核心。把今天已经存在的语义逻辑移动到正确 owner，再逐步补齐 v0.2
的 LifeContext、个人知识、人物、关系和经历约束；不复制 helper。

**执行顺序：**

1. 先将 `adoption_profiles.py` 中的 `_selfhood_seed`、`_genesis_bundle`、
   `_initial_knowledge_seeds`、名字/关系/经历 seed helper 按职责物理移动到 `elfie/genesis/`
   的现有合同/编译模块；移动后立刻更新唯一调用方并删除原函数。第一步可以保持行为等价，
   用于降低迁移风险，但不得在两个位置保留 wrapper。
2. 把这些函数继续收敛成一条 `AdoptionSelection -> LifeContext -> PersonalGenesisPlan ->
   GenesisBundle` 编译调用链。Infrastructure Adapter 接收已编译强类型结果，不再调用 world
   loader、选择知识或拼装故事。
3. 以程序固定顺序生成 LifeContext：候选身份/年龄 → 出生区域/聚落/有效地点 → 家庭照护 →
   学习/学徒 → 职业 → 迁居/路线/到访 → 必修地球培训/出发/抵达 → 全量约束校验。所有抵达者
   都必须参加 `earth_program` 的必修培训并达到最低掌握要求；不允许生成
   `participated: false` 的抵达者。物种和年龄只在已发布规则允许的出生地、生活原型和抵达资格
   范围内起作用，不能由实现者用地球常识补相关性。
4. 实现有限候选集、稳定子 Seed、可行性检查和有界回溯；失败返回可诊断的
   `UNSATISFIABLE`，不能让模型补造地点、家庭、职业或关系。
5. 用 `access` 与 `exposure` 两轴过滤 `KnowledgeCatalog`。掌握深度、亲历/受教/查阅/听说/
   神话/未知边界分开保存；专业知识、咨询目标和前置闭包逐项校验；禁止使用全局 Importance
   Top-N，也禁止把生成器权重或精确人口/坐标带入 Memory。
6. 先按 LifeContext 生成关系槽位和人物，再生成 3～5 段 `EpisodeSkeleton`；经历中合法获得的
   知识和关系变化回流到最终计划。人物 ID、命名、年龄、地点、职业和跨 Episode 复用全部由程序
   固定，不能让模型新造人物。
7. 将现有模型请求能力迁移到 Genesis 的 `NarrativeProjectionInput` 语言投影边界：模型只
   看已选事实、允许的居民知识变体、感受范围和禁止项；程序先生成规范摘要，模型失败或越界时
   使用该摘要。模型不能改名字、数字、地点、职业、时间、关系、结果或 Memory 参数；这一
   迁移不保留 M2 已删除的 Adoption 叙事 Port。
8. 如果当前 `_energy_limits` 属于身体/运行初始化而非人格语义，把它迁到现有 Body/Runtime
   owner 的 typed seed；不能为了方便继续塞进 Profile，也不能在 Genesis 外复制一套身体初始化。
9. 在本批次内把 `GenesisMemoryCommitter` 的 legacy/typed 分支合并成唯一 typed source-first
   提交路径，迁移所有调用方后立即删除 `GenesisBundle.validate` 的 compatibility branch、
   `_legacy_submission_hash` 和可重放型 `InitializationManifest`。不能把旧提交器留到 M4 再切。

**退出门：**

- `infrastructure/persistence/elfie_workspace/adoption_profiles.py` 不再包含任何个人知识、名字、
  人物、关系、Episode、人格或 LifeContext 决策 helper；它只保存强类型结果；
- 同一语义字段只有 Genesis 一个写入决定点；模型调用是可选的语言投影，不是事实生成器；
- Plan 的事实 hash 与模型 projection hash 分离，模型草稿不进入最终 owner；
- 固定 Seed、固定 package、固定预约重跑得到相同 LifeContext/Plan，约束失败也相同；
- 旧 Genesis 合同分支、旧提交器路径和语义 helper 已在本批次删除；编译测试和 Infrastructure
  依赖架构测试证明没有遗留生产引用。

### M4：收窄最终 owner，并合并 Genesis 的唯一 Memory 提交路径

**目的：** 让 Profile 真正成为外部冻结档案，并让 Selfhood/Memory 成为创建后唯一的认知来源。

**执行项：**

- `ElfieProfile` 只保留：`elfie_id`、最终名字、正式物种、适用时的固定性别、领养时稳定年龄
  与年龄锚点、不可变个人出生地点 ID/冻结名称、最终虚拟外貌和必要 Schema revision。
- 删除 `ProfileProvenance`、生成器/模型/策略版本、Seed、用户选择、资料包 hash、抵达/培训
  方式、人格、世界观、能力/权限/预算、关系、传记和运行态。`AppearanceGenome` 只保存最终
  外貌结果，不保留可重放生成 Seed；形态/能力引用归 Body 或运行资产投影。
- `birth_date` 若只是旧界面需要，改为 App 层明确标注的年龄投影；不能把推导日期写成 Elfaria
  的精确出生亲历或继续作为第二年龄事实。
- 将人格锚点、价值、表达和自我认识写入 Selfhood Seed；将公共/地方/专业知识、人物关系、
  领养前历史、培训和抵达事实写入 Memory。Profile 与 Selfhood 的最低身份重复只发生在初始
  并列快照，提交后不互相刷新。
- 验证 M3 已经完成的唯一 typed source-first Genesis 提交路径，继续复用现有 Memory Unit of
  Work 和 Memory 自己的 Retention 解析；Genesis 不直接改 Retention 数值，也不重新引入旧
  `MemorySeed`/人格兼容形状、`InitializationManifest` 或 alias/fallback。
- 删除会暴露生成来源、Canon、物种规则、master Seed 或完整输入的旧 Genesis 完成节点内容，
  只保留最小 `GenesisCommitReceipt`：对象 ID/摘要、幂等键摘要、Schema/编译器修订、状态和
  时间。Receipt 不能重建个人生活。
- 保持记录级 Memory 参数边界：Knowledge/Relationship 的 Node/Assertion 各自有 C/I；
  Episode 只有 Importance；Episode 事件命题产生带 Evidence 的 Assertion；所有 R/H 由
  Memory 策略解析，物化层不猜默认值。

**退出门：** `Profile` 递归字段/引用扫描通过严格白名单；普通 Reasoning 的输入仍只有
`SelfhoodPromptProjection`、Memory `RecallBundle` 和当前状态；删除创建资料包、问卷和 Seed
后，最终 owner 仍可重开。

### M5：把现有 Resident Admission 原位改成可恢复的一次性发布状态机

**目的：** 不新增第二个 Admission 服务，而是把当前 `ResidentAdmissionService` 的进程内补偿
逻辑升级为持久、可重开的发布协议，并保证 Runtime 注册最后发生。

**状态和数据：**

```text
reserved -> compiling -> staged -> publishing -> committed
    |
    +-> aborted (from any pre-commit state)
```

- `reserved`：一次 compare-and-set 冻结候选、owner、配额和幂等键；未 `committed` 前不在产品
  列表中，也不算已入住 Elfie；但活动预约要暂时占住相应容量，避免并发超额，终止后释放。
- `compiling`：`GenesisCompileEnvelope` 和必要的中间输出只在同一私有事务工作区存在。
- `staged`：同父目录的未发布 sibling workspace 中已有 Profile/Selfhood/Memory 强类型输出，
  Memory completion marker 与其记录同一 UoW 提交；暂存目录不被普通入口发现。
- `publishing`：持久记录写入发布意图和输出摘要；重开时先验证摘要、引用、年龄、空间、知识
  权限和因果，不根据新 package 重算。
- `committed`：暂存目录以同文件系统原子 rename 变成最终目录，并在可恢复的后续持久步骤中落定
  领养/所有权关系和最小 receipt；只有所有这些步骤完成后才把状态标为 `committed`，可列出和
  恢复。这里不宣称文件系统、SQLite、Memory 和 Runtime 构成一个跨存储原子事务。
- `aborted`：删除暂存输出和所有创建输入，释放预约容量；不能留下半只 Elfie。

**执行项：**

1. 将 `ResidentWorkspacePort.materialize/release` 原位演进为 typed stage/reopen/publish/
   abort 操作；不另建并行 workspace adapter。`ensure_final_elfie_layout` 改为先创建 sibling
   staging layout，最终目录只能由 Admission 发布。
2. 将当前 `FinalElfieWorkspaceAdapter` 的文件写入保留为技术 Adapter，但输入改为已校验的
   `GenesisBundle`/commit plan；它不能再加载世界 Canon 或调用 Genesis 语义函数。
3. 把当前 `ResidentAdmissionService._completed` 的内存 LRU 换成持久幂等状态。可以增加一个
   只保存预约状态、摘要和恢复信息的技术 Admission 记录，但不能用它复制 Profile 身份或
   Genesis 输入；终态只留下最小 receipt。
4. 将配额和 Nest 容量检查纳入预约状态的 compare-and-set。暂存/失败预约不计为可见居民，
   `committed` 才计入最终占用；重复幂等键若摘要不同必须拒绝。
5. 重新排列当前调用链：编译/暂存 → 重开校验 → 发布最终目录 → 落定 committed/领养关系 →
   Runtime restore/register。Runtime 注册失败不能回滚已提交的 Profile/Selfhood/Memory；
   应留下可重试的离线状态，由既有生命周期机制再次注册。
   Admission 的返回值和产品状态要明确区分“已持久提交”和“当前 Runtime 是否已注册”，不能把
   Runtime 暂时不可用误报成整次 Genesis 失败，也不能让调用方为此重新编译。
6. 为“rename 后、关系提交前”“关系提交后、Runtime 注册前”“进程重启”“重复请求”“旧
   package 不可用”分别定义恢复动作。恢复不得盲目删除合法最终目录，也不得重新生成一个不同
   Elfie。

**数据变更约束：** 当前版本直接采用新 Schema 和新状态记录，不提供旧字段读取、双表双写或
fallback。旧开发数据可以重建；本次不执行真实数据根的删除、备份或迁移，也不让其限制代码设计。

**退出门：** 任一崩溃点都能得到“继续同一预约”或“完整终止”，不会出现半套初始化、重复扣额、
孤儿最终目录或 Runtime 先于持久提交注册；Admission 只有一个服务和一个状态机。

### M6：切换所有外部读取，并证明提交后断源

**目的：** 删除最后一批“看起来只是页面读取、实际上又拥有身份事实”的旁路。

**执行项：**

- 将 `infrastructure/persistence/elfie_workspace/elfies.py`、API、管理页和前端 fixture 的
  身份读取改成 App 授权的聚合 View：身份来自 Profile，内部人格/摘要来自 Selfhood，知识/经历
  来自 Memory，Nest DB 只提供 owner、居住锚点、领养关系和运行状态等自身字段。
- 在一次 Schema/调用方切换中移除 `nest.db.elfies` 的重复 `name`、`original_name`、`species`、
  `gender`、`birth_date`、`summary` 事实字段（只有经确认仍属于 Nest 的关系/状态字段可以保留）。
  所有 quota、Food、Body、通信和 Nest state 消费者改用 `elfie_id` 及其 owner 数据，不保留旧
  身份读路径。
- 移除 Selfhood 对 `ProfileAnchorSnapshot` 的所有权；Observer 只能读取稳定 Profile/App
  dossier，不能刷新当前 Canon，不能把档案 View 注入 Brain。
- 构造“创建资料目录不可用/已删除”的重开测试：已提交 Elfie 只从 Profile、Selfhood、Memory
  和必要运行态恢复；普通推理看不到 SourcePackage、Creator 文档、receipt、未选知识或地球
  训练先验。
- 检查日志、异常、诊断和备份索引，不得留下原始问卷、邀请原文、Seed、完整 LifeContext/Plan
  或可重建人生的路径/提示词。

**退出门：** 所有产品读取只有一个聚合方向；`git grep` 和运行时断源测试证明已提交 Elfie
不依赖创建资料。若某个页面还必须读旧身份列，先迁移该页面，再删除列，不能加兼容读取。

### M7：删除残余、收口测试和 Conformance 证据

**目的：** 把迁移中暂时保留的旧符号、测试夹具和登记项彻底收掉，确保仓库不会继续暗示两套实现。

**执行项：**

- 删除旧导出、旧 port 名称、旧 `materialize` 语义入口、`ProfileProvenance`、
  `elfie/profile/canon.py`、legacy Genesis 校验/哈希，以及 M3 迁移后仍残留的旧叙事实现；
- 删除仅服务旧路径的测试和 fixture，改写仍有价值的行为测试去调用当前唯一入口；不能保留一套
  “兼容行为”来让旧设计继续通过；
- 从配置 registry、发行清单和 Bootstrap 删除旧 world/species loader 登记；验证没有生成物、缓存
  或临时 package 被写回源码目录；
- 按 `ELF-010`、`ELF-013`、`CFG-005`、`SHD-002` 的五类证据要求同步更新英文和中文
  Conformance 台账，只记录真实通过的证据，不提前标 closed；
- 对代码、配置、动态入口、脚本、Schema、文档链接做一次递归 owner/authority 扫描。

**退出门：** 旧实现和旧事实源不再可调用；所有 v0.2 完成门通过；工作区无未分类残余。v0.1
执行计划仍作为历史快照保留，但不进入运行时、测试基线或当前实施入口。

## 6. 每批次的验证矩阵

验证只证明当前路径，不把新写的孤立模块当作完成。按受影响范围逐步扩大：

| 批次 | 必须验证的重点 | 直接相关范围 |
| --- | --- | --- |
| M0 | 当前行为基线、入口/引用/数据盘点、内容和数据门 | Git 状态、配置 registry、Adoption/Genesis/Admission 调用图 |
| M1 | manifest 成员、引用/hash、0→1→2 双向覆盖、单一资料源、无代码 Canon | configuration world/species tests、Genesis engine、配置架构测试、递归 import/literal scan |
| M2 | `any` 实际化、年龄一对一、候选确定性、接受幂等、无模型事实生成 | Genesis engine、Adoption facade/registry、API adoption routes、候选前端契约 |
| M3 | 空间/年龄/职业/知识权限/关系/经历硬约束、模型白名单和 fallback | Genesis contracts/compiler、Memory seed mapping、workspace boundary architecture tests |
| M4 | Profile 白名单、Selfhood/Memory owner、单 typed submission、C/I/R/H 边界、输入清理 | Profile models/store/generator、Selfhood、Memory initializer/schema/reopen |
| M5 | 每个崩溃窗口、原子暂存/发布、重复预约、容量、Runtime 最后注册 | Resident Admission、workspace layout/store、adoption persistence、Lifecycle integration |
| M6 | 页面聚合、无重复身份列、删除 SourcePackage 后恢复和推理断源 | Nest DB/API/UI、Profile observer、Reasoning/Recall、persistence reopen |
| M7 | 残余扫描、Conformance、聚焦质量门和最终候选 SHA | architecture/conformance tests、`git diff --check`、受影响测试包、Ruff/pre-commit |

### 6.1 必须有的行为场景

至少覆盖以下场景，而不是只比较最终节点数量：

1. 同一预约、同一 package revision、同一 Seed 重试，LifeContext、Plan、对象 ID 和语义 hash
   完全一致；不同摘要复用幂等键被拒绝。
2. 用户选择的物种、性别、年龄阶段和外貌与最终 Profile 一致；`any` 不出现在最终值中；年龄
   与地球年一对一。
3. 没有模型、模型返回越界实体、模型超时三种情况下，结构化事实都不改变，并使用规范摘要。
4. 普通居民只能得到有 access/exposure 的公共知识；地方、专业、`reference_only`、传闻和
   未知边界不会因模型或地球先验被越权补全。
5. 出生单元可居住，家庭/学校/职业/路线/人物接触在地图和通行成本上成立；不合年龄的职业、
   无资格抵达、未培训抵达、未到访地区知识和无解约束都被拒绝。
6. 人物 ID 不因重名合并，关系槽位数量有界，部分高显著人物能在经历中合法复现；Episode 有
   因果链，且 Episode 本身没有 Confidence。
7. Memory 内提交失败、工作区写入失败、最终 rename 前后、关系落定后和 Runtime 注册失败时，
   均得到明确可恢复状态，不产生半套可见 Elfie。
8. 删除/不可用创建资料包后，已提交 Elfie 能恢复；Brain 不读 Profile、SourcePackage、
   receipt、Seed、Creator 文档或训练集地球常识。
9. 原始问卷、邀请原文、资料绑定、Seed、完整 LifeContext/Plan 不在最终 Profile、Selfhood、
   Memory、长期 receipt、普通日志或数据库中。

### 6.2 代码级收口扫描

最终扫描应按实际符号而不是只按文件名执行，至少检查：

- `ELFARIA_CANON`、`WORLD_CANON_VERSION`、`ProfileProvenance`、旧 Genesis 完成节点、
  `_legacy_submission_hash`、legacy/compatibility Bundle 分支；
- `AcceptedAdoptionReservation`、`AdoptionNarrativePort`、旧 `materialize` 和
  `_initial_*_seeds` 的生产引用；
- Infrastructure 是否 import/构造 `LifeContext`、PersonPlan、EpisodeSkeleton 或选择知识；
- Profile/`elfies` 表是否重新出现 world/canon/seed/personality/story/capability/arrival 字段；
- 运行期是否仍通过 `config/`、Creator 文档或 Profile 重新编译已提交 Elfie；
- 是否存在第二个 Memory writer、第二个 Admission service、fallback read、dual write 或
  未登记的配置文件。

## 7. 对本计划的精细化反向审查

### 7.1 已主动封住的主要漏洞

| 攻击点 | 可能的错误 | 本计划的防线 |
| --- | --- | --- |
| “先写新实现，旧实现以后再删” | 两条 Genesis/Memory 路径长期共存 | 每批次同一检查点切换调用方并删除旧入口；M7 做递归扫描 |
| “把新资料包加上，旧 YAML 继续读” | 两份世界事实，结果随入口不同 | M1 原位切换 manifest/成员，旧 flat loader 同批退出 |
| “Profile 里先留着方便” | Profile 变成世界观、生成账本和 Brain 旁路 | M4 白名单硬门；M6 聚合读路径和断源测试 |
| “模型只是帮忙，但可以顺手起名/编故事” | 模型成为身份和事实 authority | M2 名字程序化；M3 模型只收白名单投影并由程序校验 |
| “跨文件都叫 atomic” | 文件、DB、Memory、Runtime 实际无法伪装成一个事务 | M5 明确只有 Memory UoW 原子；跨存储用持久状态机和恢复，不宣称假原子 |
| “Runtime 先注册，失败再补数据库” | 运行中出现无持久身份的半只 Elfie | M5 把 Runtime 注册放在 `committed` 之后，失败只重试运行注册 |
| “旧表先保留，页面慢慢迁” | DB 与 Profile 双事实源 | M6 同一 Schema/调用方切换，禁止 fallback/dual write |
| “为了确定性保留全部 Seed” | 回执/档案可重建人生，且新版本可能重放旧人 | M3/M4 将 Seed 限定为事务数据，receipt 只保留不可重建摘要 |
| “固定五段故事/固定总人口” | 实现把示例当成世界规则，过度设计 | M0 冻结内容，M3 从版本化规则生成有界结果，不写死示例数量之外的事实 |
| “删除资料包后旧 Elfie 需要重编译” | 新世界资料静默改写既有生命 | M6 断源恢复是硬门，创建资料只影响未来创建 |

### 7.2 仍然需要在实施前确认的边界

这两项不是计划结构漏洞，而是不能由编码代理替用户决定的外部状态：

1. **内容完整性：** 物种 × 允许生命阶段、空间密度和聚落权重、家庭/学习/职业原型、关系槽位、
   Episode 主题、命名词库和地球培训课程的具体值还必须由人工确认。没有这些值，M3 只能实现
   校验器，不能捏造最终世界。
2. **真实数据处理：** 本次明确不处理真实数据根。代码按新 Schema 直接开发，旧开发数据可重建；
   后续若在 0.5 之后需要保留数据，再另立数据迁移决策，不能为此在当前代码中加入兼容层。

### 7.3 不应再添加的“看似安全”方案

- 不添加 `GenesisV2`、`NewGenesisEngine`、`ProfileV2`、`MemoryV2` 或 `ResidentAdmissionV2`
  与旧类并存；必要的版本升级应直接迁移现有 owner 和调用方。
- 不添加 `LegacyReservationAdapter`、旧字段 alias、双写、fallback read、feature flag、
  随机百分比分流或“以后再删”的兼容层。
- 不把完整 LifeContext/Plan 放进 Profile、Selfhood、Memory、Nest DB、日志或长期任务队列。
- 不为了让旧测试继续通过而恢复 `Profile` 的 Canon、Provenance、人格/故事或能力字段；测试应
  迁移到新契约。
- 不把 `Genesis` 和 `Infrastructure` 重新抽象成对称的两个生成器：前者是生命语义编译器，后者
  是技术加载/保存边缘，两者不存在职责竞赛。

## 8. 完成定义与停工条件

只有同时满足以下条件，才可以说“v0.2 迁移完成”：

- 六阶段资料链、数据保存形式、生产者和销毁时机均与目标设计一致；
- 所有个人语义决定只来自 `elfie/genesis`，所有持久化只由对应 owner 和现有技术 Adapter
  完成；
- 只有一条候选→编译→提交路径，只有一个 Memory Genesis writer 和一个 Admission 状态机；
- Profile 没有世界观/Canon/生成来源/个人认知，Brain 没有 Profile/SourcePackage 旁路；
- 创建输入在提交或终止失败后被清理，最小 receipt 不可重建人生；
- Memory 参数、空间/时间/知识/关系/Episode 约束和模型投影门全部有行为证据；
- 崩溃恢复、幂等、提交后断源和新资料不刷新旧 Elfie 均通过；
- 旧实现、旧 Schema 事实字段、旧 loader、旧测试入口和未登记生成物已分类并按计划删除；
- `ELF-010`、`ELF-013`、`CFG-005`、`SHD-002` 的 Conformance 证据完整，未关闭项如实保留；
- 受影响测试、架构扫描、`git diff --check` 和仓库规定的质量门通过，且没有把环境/数据阻塞
  伪装成实现完成。

如果任一前置内容或真实数据门未通过，停止在对应批次，不创建第二套实现来“先跑起来”。这份
计划本身已经收敛为 v0.2 的迁移路线；后续执行应从 M0 的事实/数据门开始，沿现有接缝逐批替换，
而不是重新开发一套与今天代码平行的系统。
