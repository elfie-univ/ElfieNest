# OPT-001 执行计划（修订候选）：Elfaria 知识与个体初始化

> **状态：OPT-001 实现与 E2/E3 机器门已关闭；负责人体验复核归 MEM-008**
> **目标基线：** `origin/codex/memory-source-first`，`1aa51264`（2026-08-27）
> **目标：** 让新领养的 Elfie 从第一次对话起，能从自身 Memory 连续回答 Elfaria、物种、迷雾镇、过去、人物和赴地经历；未知处明确说不知道。
>
> **历史边界：** 本文是已关闭 OPT-001 的执行与证据快照，不是现行 Genesis 设计。本文中的
> 长期 Manifest、Profile 来源字段、旧 worktree 路径和提交后重放写法已被 ADR-0033、Elfie 2.3、
> Brain 1.5 与 [Genesis v0.2](./genesis-core-kernel-design-v0.2.md) 取代；后续实现不得复制这些旧边界。

当前 worktree 另有本地 `16547111`（OPT-002 连续学习提交，领先 origin 一步）；它不是本计划范围，必须保留但不纳入 OPT-001 的变更或验收。实现前以目标基线与当前提交分别做差异盘点，不得混入或反向修改该提交。

<<<<<<<< HEAD:docs/.internal/elfaria/opt-001-genesis-knowledge-story-execution-plan-v0.1.md
本计划把已保存的 [Genesis 核心设计](genesis-core-kernel-design-v0.1.md)落成执行顺序；旧阶段总计划中的历史 SHA 不覆盖本基线。
========
本计划把已保存的 [Genesis 核心设计](./genesis-core-kernel-design-v0.1.md)落成执行顺序；旧阶段总计划中的历史 SHA 不覆盖本基线。
>>>>>>>> origin/main:docs/.internal/drafts/opt-001-genesis-knowledge-story-execution-plan-v0.1.md

本次修订补回实施所需的字段、引用、时间、导入、读取和评测契约；不增加新的世界设定。第一版按本计划的最小垂直切片落地；后续只处理本文件列出的验收残余，不在本阶段发散。

## 1. 当前结论

> 下表保留开工时的差距记录，用来说明为什么形成当前链路；当前完成状态以本文后面的冻结判定、现行代码和验证证据为准。

| 已有 | 今天缺的 | 处理判断 |
|---|---|---|
| source-first SQLite、`ClosedEpisode`、来源证据、FTS/别名、`RecallBundle`、重启/幂等基础 | 公共 World Canon 没有注册的结构化配置；知识仍散落在硬编码/Profile/Prompt | 先建立唯一 `config/` Canon 总源，再编译个人知识 |
| Genesis 有通用 `MemorySeed`、`SelfModelSeed` 和标记，但不是三类 Seed 合同 | 没有 `KnowledgeSeed[]`、结构化 3–5 Episode、可引用的 Relationship 图 | 扩展现有 Genesis，不另造存储 |
| 领养适配器只生成五条泛化记忆和一个主人关系；历史时间写成 `now` | 没有家乡、重复人物、因果链、赴地经历、历史时间/写入时间分离 | 用真实人生图替换泛化卡片 |
| Reasoning 可读 `RecallBundle` | 来源链和未知边界需要独立证明；Prompt 不应重复丰富世界事实 | 已通过 Memory 召回断言，并移除 Prompt 中重复的 Selfhood 身份事实 |
| Elfaria Canon v0.1 只确认 Elfaria、迷雾镇和有限边界；Saevi/灵狐、Tovren/灵犬 published，Myelle/灵猫 draft | 旧 E1 fixture 使用未入 Canon 的“雾谷”等词，不能作为 OPT-001 证据 | 已将 E1 fixture 冻结为 `stage1-e1.v2` 并走正式 typed Genesis；不把未批准故事默认为 Canon |

现有 E1/Memory 证据只能证明基础链路，不能证明 OPT-001 的知识密度或传记完成；`MEM-008` 的 owner review 也不替代本批验收。

事实盘点入口：[`genesis/contracts.py`](../../../elfie/genesis/contracts.py)、[`genesis/initializer.py`](../../../elfie/genesis/initializer.py)、[`adoption_profiles.py`](../../../infrastructure/persistence/elfie_workspace/adoption_profiles.py) 和 [`config/species/catalog.yaml`](../../../config/species/catalog.yaml)。

## 2. 范围与完成定义

### 本批唯一主线

```text
版本化 Elfaria/物种公共知识
  → Genesis 领养时个体化
  → Profile + Selfhood + 初始 Memory
  → RecallBundle → Reasoning
```

必须完成：一个可追溯、可检索、可幂等重放的初始化包；公共知识与个人知识分层；新领养、改写、重启后核心事实一致；没有真实巢观测时不编造当天位置、天气、动作或巢内事件。

明确不做：OPT-002 持续学习/消歧/纠正，OPT-003 压缩/遗忘，OPT-004 真实巢/身体/多精灵互动，向量库、第二记忆库、全宇宙扩写、长期兼容层、既有生产 Elfie 回填，以及 3D/外壳工作。

## 3. 冻结的目标合同

### 3.1 来源与存储权威

| 层 | 只负责什么 | 目标位置/读取 |
|---|---|---|
| World/Species Canon | Elfaria、迷雾镇、物种公共事实和未知边界 | `config/world/elfaria.yaml` 与 `config/species/`，版本化且唯一 |
| Profile | 姓名、物种、出生/来源、外观、Big Five/固定特质锚点 | 精灵运行目录配置；对外稳定，不作百科 |
| Selfhood | 自我认识、价值、人格表达、边界和当前目标 | Brain 自我模型；不作公共事实总源 |
| Memory | 这只 Elfie 实际掌握的知识、亲历 Episode、关系及证据 | 现有 source-first SQLite → `RecallBundle`；不直接读 Profile、聊天历史或运行时巢状态 |
| Prompt | 身份锚点、版本提示、硬未知/防虚构规则 | 仅保留必要约束；不再承载丰富事实 |

不得直接写 Profile 代替 Memory，不得把百科只塞 Prompt，不得写无来源图节点。每条重要事实、经历和关系都要回到版本化 Canon、approved seed 或 Episode 证据。

World Canon 的叙事层级固定为：`Elfaria(world) → 已知区域/迷雾镇(region/settlement) → 已批准地点与设施(place)`。地图只保存父子关系、相对方向、用途、别名和交往边界，不保存 Godot 坐标、碰撞、导航或实时位置；迷雾镇的分散居住/有限交往规则必须能解释不同离线 Elfie 不会自动互相认识。Bundled Canon 只读、无用户 overlay，运行目录不得反向改写它。

公共故事主线也属于 World Canon 的事件簇，而不是某只 Elfie 的私人经历：**跨世界信号 → 初次接触并确认彼此存在 → 地球侧基站与 Elfaria 赴地计划 → Elfie 抵达 ElfieNest**。每个公共事件有自己的稳定 ID、版本和时间标签；个体 Episode 只能引用它并说明“亲历/听闻/未参与”，不能把公共故事直接冒充个人回忆。抵达之后的共同探索属于后续发展，不在本批预写成每只 Elfie 已发生的事实。

配置分层保持单一方向：源码 `config/` 只存 Bundled World/Species Canon 及注册信息；领养时由 Genesis 读取并生成个体包；运行目录沿用现有 resolver 保存 Profile、Selfhood、Memory 和 Manifest。运行目录不回写源码 Canon，也不另建一份公共知识库。

### 3.2 公共 World Canon 首版

只冻结当前文档已批准的 **Elfaria → 迷雾镇** 范围；没有证据的全星球地图、政治、天气、经济细节保持 unknown。首版以约 40–80 条可独立引用原子事实为容量目标，不以数量替代覆盖；每一类都要形成可追问的事实簇，不能只塞一句总括话。

八个主题必须都有内容和未知边界：

1. 世界身份、已知范围及与地球的关系；
2. 物理/自然、时间、昼夜、季节、生态和生命规律；
3. 星球—区域—地点层级、迷雾镇地图/设施/生活空间、分散居住/交往边界及三物种共居解释；
4. Saevi/灵狐、Tovren/灵犬、Myelle/灵猫的共同身体、感知、需求和常识；
5. 家庭、族群、长老、礼仪、信任、劳动、教育、经济和知识传播；
6. 历史、语言/价值、食物、日常和文化；
7. 跨世界信号、赴地计划、地球差异和适应边界；
8. 公共知识级别与未知表：人人常识、部分人掌握、听说、未定义/未亲历。

每条记录必须带稳定 ID、来源、版本、范围、主题、别名/检索词、确定性和适用资格；不得出现未批准的新地名或把个人经历写成公共事实。`level` 表示社会普及程度，`certainty` 表示来源确定性，`mastery` 只属于个体 Seed；`source_ref` 必须可追溯到 Canon、approved seed 或 Episode。旧 E1 的“雾谷”必须替换或单独批准，不能静默沿用。

| 条目字段 | 约束 |
|---|---|
| `id` / `version` | 稳定条目 ID；随 Canon 版本冻结 |
| `scope` / `topic` | 世界、区域、聚落、地点或物种；归属八类主题 |
| `statement` | 一条可独立回答的原子陈述 |
| `aliases` / `retrieval_terms` | 用户称呼、稀有词和改写检索词 |
| `level` / `certainty` | 社会普及程度 / 来源确定性，二者不混用 |
| `status` / `source_ref` | active 或 unknown-boundary；可追溯的 Canon/approved seed 来源 |
| `related_ids` / `eligibility` | 关联地点/物种/事件；适用物种、区域、生活阶段或角色 |

物种合同与范围固定为：所有 `published` 物种使用同一 Genesis/Memory 字段、来源和验证规则；当前只把 `fox/Saevi`、`dog/Tovren` 纳入公开领养门禁，`cat/Myelle` 保持 draft。物种包只提供共同身体、感知、生活语境、别名和边界，不能决定个体 Big Five、朋友或人生经历。

### 3.3 个体初始化包

Genesis 输入为已冻结的 Canon 版本、物种状态、领养上下文、确定性 seed，以及现有受控 custom/CFHO 输入；custom/CFHO 只能影响个体化，不能越过 Canon、来源或 unknown 约束。

Genesis 输出固定为：

```text
ProfileDraft
SelfhoodSeed
KnowledgeSeed[]
EpisodeSeed[]
RelationshipSeed[]
InitializationManifest
```

| 层 | 初始化事实 | 不得承担 |
|---|---|---|
| Profile | `elfie_id`、姓名、物种/版本、出生或来源世界/区域/地点、外观、Big Five 数值、固定特质锚点 | 世界百科、事件正文、关系网、当前状态 |
| Selfhood | 自我认知、价值/边界、人格表达、技能/熟悉度、习惯、偏好、情绪触发、当前目标、地球适应的自我描述 | 公共事实的第二权威、未经来源的传记 |
| Memory | 个人掌握的公共知识、亲历 Episode、人物/地点关系、地球经历和来源证据 | Profile 身份替代、实时巢状态 |
| Prompt | 身份锚点、版本提示、硬 unknown/防虚构规则 | 丰富世界资料和个人事实 |

Big Five 数值只在 Profile 保留一个权威副本；Selfhood 只保存由它派生的表达/行为含义。Profile 的出生/来源是客观锚点，Memory 保存“在那里生活过什么”。

Genesis 选择规则：人人应掌握的 eligible `common` 知识进入 `mastery=known`；居住区域、物种和个人经历相关知识按资格进入 `known/partial`；`specialist` 只能在有对应角色/经历时进入，其他内容保持 `heard/unknown`。公共 Canon 不会整体复制给每只 Elfie。

三类 Seed 的必备字段和数量如下：

| Seed | 必备内容 |
|---|---|
| `KnowledgeSeed[]` | 稳定 ID、Canon/Species `source_ref`、陈述、`scope/topic`、别名/检索词、来源/版本、`certainty`、公共 `level`、个体 `mastery`、`eligibility`；每个主题有可用知识或明确 unknown |
| `EpisodeSeed[3..5]` | 稳定 ID、正文/摘要、`scope/topic`、别名/检索词、`life_stage`/`temporal_label`（可选有依据的发生范围）、地点 ID、人物 ID、结果、感受、长期影响、前后/因果引用、来源/版本/certainty |
| `RelationshipSeed[]` | 稳定关系 ID、主体/对象 ID（人或地点）、`scope/topic`、别名/检索词、角色、方向、熟悉度、信任、共同 Episode、已知/未知字段、来源/版本/certainty；约 10–20 人，其中 3–5 个高显著、1–2 个反复出现，并含领养家庭/地球侧关系 |

最小人生图还必须有一个已批准的家乡/生活地点、一段离开 Elfaria/赴地/抵达地球经历和至少一条“过去经历→当前性格/选择”的因果边；出生/早期生活点按确定性 seed 从已批准地点选择，不生成未定义公共地点。不同 Elfie 使用独立命名空间，不因共同迷雾镇共享人物或记忆。

`InitializationManifest` 还必须记录 Elfie 命名空间、generator/schema/reference 版本、确定性 master seed、输入/输出 ID 列表、内容哈希、幂等键、状态、校验错误和提交时间。Canon 版本随 Manifest 固定，新 Canon 只影响新领养，不静默改写既有记忆。

## 4. 有序执行阶段

| 阶段 | 要做 | 进入/退出门 |
|---|---|---|
| 0. 冻结内容与范围 | 逐条核对 Elfaria/迷雾镇/三物种现有 Canon；建立八主题覆盖矩阵、未知/禁编表、公开物种表；重写 `devtools/evals/stage1_e1_scenarios.json` 中不合规的 E1 fixture | **退出：**用户确认首版事实、术语、published 范围（fox/Saevi、dog/Tovren；cat/Myelle 仍 draft） |
| 1. Canon 配置接线 | 在现有配置注册/校验机制下维护唯一机器 Canon：`config/world/elfaria.yaml` 与现有 `config/species/`；把硬编码 WorldCanon 收敛到该总源，不建平行知识源 | **退出：**版本、schema、来源、别名、unknown 和范围可加载；所有条目可定位 |
| 2. Genesis 类型化 | 将通用 `MemorySeed`/现有 `PersonalitySeed`/`SelfModelSeed` 收敛为三类 Seed 与 Selfhood 边界，移除“最多 5 段记忆”对 Knowledge 的限制；基于 Canon、领养上下文和确定性 seed 个体化，Genesis 只在领养时运行 | **退出：**确定性校验拒绝越界物种/地点/年龄/时间线/无引用/矛盾包；同输入生成同 Manifest |
| 3. 正式导入 | 把三类 Seed 映射到现有普通 Episode、Node、Assertion、Evidence 和 `RecallBundle`；补齐历史时间字段语义、稀有词/别名检索、来源回链、幂等和失败恢复。优先用现有 marker/manifest 与受控暂存实现可见性，不擅自跨库造新事务 | **退出：**整包成功后才可见；重放不复制；崩溃不留下半套 Profile/Selfhood/Memory。若必须新增表、系统 Port 或真实迁移，立即停并单独审批 |
| 4. 读取与 Prompt 收敛 | 用事实/主题/实体/关系/改写问题验证 typed `RecallBundle`；确认 Memory 独立支撑回答后，删除 Selfhood/Reasoning 中重复丰富世界事实，仅保留身份锚点和硬未知规则 | **退出：**不依赖 Prompt 重复注入仍能回答；未知与实时巢问题不被补写 |
| 5. 领养与门禁 | 新领养验证 published 物种同一合同、不同 Elfie 隔离、重启/重复初始化；跑 E2/E3 及 E1 回归，更新 `docs/developer/conformance/elfie-memory.md` 的 OPT-001 证据 | **退出：**指标达标、证据可重放、残余缺口逐条记录；未完成物种不宣称完成 |

拟修改面只限于：`config/` 与现有 configuration registry/schema、`elfie/genesis/` 合同/初始化器、领养 materialization、现有 Memory Adapter/Recall 接线、Selfhood/Reasoning 的重复事实、相关测试/eval 场景和 OPT-001 conformance。实现前先做调用方盘点；若出现新顶层包、系统级 Port、永久 schema/迁移或公开协议，立即停下确认。

执行触点按现有代码归位：Canon/config 与 registry → `elfie/genesis/contracts.py` 及生成/校验调用方 → `elfie/genesis/initializer.py` 和领养 materialization → Memory/Recall 与 `elfie/brain/reasoning` → 对应 `test/`、`devtools/evals/` 和 conformance 台账；每一步先有失败测试/证据，再进入下一步。

### 4.1 Genesis 输入、状态和校验

输入固定为 World/Species Canon 版本、物种 catalog 状态、领养上下文、确定性 master seed、候选身份和受控 custom/CFHO；后者只能影响允许的个体差异，不能覆盖 Canon、物种状态、来源或 unknown。

```text
draft/candidate → validated → staged → committed
                         └→ rejected/aborted（运行时不可见）
```

模型只提出候选；确定性校验负责 Canon 引用、物种/地点存在性、年龄与 life stage、事件顺序、人生图连通性、因果边、人物/地点引用、来源/别名、冲突和 unknown 边界。模型失败只允许有界重试，仍不合格就整包 rejected；Genesis 只在领养时运行，不增加后台补写人生路径；`personal_story` 由正式 Seed 派生。

### 4.2 Seed 到 Memory 的明确映射

| Seed | 写入语义 |
|---|---|
| `KnowledgeSeed` | 通过 source-first 的 Canon/approved-seed 来源记录，再投影带证据的知识节点/断言；不得直接写无来源节点 |
| `EpisodeSeed` | 写成运行期同样使用的普通 `ClosedEpisode`，再生成事件、人物/地点 mentions、断言和 evidence |
| `RelationshipSeed` | 写人物/地点节点和带来源的关系断言，必须引用 Episode、approved seed 或 Canon |
| `ProfileDraft` / `SelfhoodSeed` | 写各自所有者；不把它们反向当作 Memory 事实源 |
| `InitializationManifest` | 记录命名空间、版本、输出 ID/哈希和最后提交 marker；未 committed 的包不可召回 |

`source_kind`/`source_ref` 的语义（最小包括 Canon、approved seed、Episode、personal memory）必须落在现有 typed metadata/evidence 中，不能靠不可校验的自由文本或隐式约定。

先完成全包校验，再用现有 marker/manifest 与受控暂存发布；失败时清理暂存或标记 aborted，重放同一 Manifest 只做确定性 upsert。当前 Profile/Selfhood YAML 与 SQLite 分开提交，若不能在不新增 schema、系统 Port 或真实迁移的前提下满足整包可见和崩溃恢复，必须停下单独审批。

### 4.3 Recall 与未知回答

`RecallBundle` 必须返回独立 typed item，至少保留 `memory_id`、kind、内容、topics/entities、相关度、来源类型/ID/版本、certainty、status、发生时间/temporal label 和 source event IDs；不能把多条事实压成一个合成记忆。

- 事实、改写、关系和过去问题按主题/别名/实体/时间做有界检索；连续追问依靠稳定的 Seed/Memory ID 和 typed `RecallBundle`，不依靠模型临时编造；稀有词可从 Episode 文本命中。
- Profile 负责身份锚点，Canon 负责公共事实，KnowledgeSeed 负责个人掌握程度，Episode 负责亲历；冲突显式暴露，不现场圆谎。
- 没有合格来源就回答 unknown/只知道一部分；没有真实巢观测时不得回答当天巢内位置、天气、活动、动作或其他 Elfie 状态。
- 地球模型和通用语言常识只用于表达，不得升级为 Elfaria 事实或个人亲历。
- 只有确认 Memory 独立召回后，才删除 Selfhood/Reasoning 中重复的丰富世界资料；Prompt 只保留身份锚点和硬边界。

## 5. 验收与证据

### 覆盖矩阵

每条场景记录 `scenario_id`、物种/Manifest、主题、问题类型（事实/改写/关系/未知反事实）、问题文本、期望事实、允许来源 ID、禁止声明、预期 unknown、是否重启/重放。每个八主题准备四类问题，另准备三个独立过去角度（地点、人物、赴地/因果）。覆盖矩阵是测试旁证，不是运行时事实源。

最低题量沿用阶段评测口径：E2 每个主题至少 6 个事实问题、每题 2 个改写（八类合计至少 96 个问题），另有至少 20 个未知/反事实/地球实时或巢内挑战题和 6 条连续探索脚本；E3 对每个 `published` 物种覆盖 4 个 life stage、至少 3 个确定性生成 seed，并追问地点、人物、快乐/困难经历、赴地原因及当前影响。题量是下限，不能以少量示例替代覆盖。

### 必测行为

- 新领养立即可问母星、物种、迷雾镇、生活、过去和赴地；至少三个过去话题可连续追问。
- 换问法、进程重启、同一 Manifest 重放后，身份、人物、地点、结果、时间标签和因果一致。
- 稀有词和别名能从 Episode/Knowledge 命中；每个回答事实可回溯到 Canon/approved seed/Episode。
- 知识变多后仍遵守现有 `RecallBundle` 的条目/字符上限和类型配额，不新增隐式模型调用，不挤掉当前消息、身份锚点和必要关系；若预算确需调整，必须单独记录基线、理由和验证结果。
- 没有巢观测时，对当天巢内位置、天气、活动、动作、其他 Elfie 状态的未知/反事实问题伪事实数为零。
- 不同 Elfie 只读自己的命名空间；不得因共同迷雾镇自动认识彼此。

### 证据与指标

保存基线 SHA、Canon/Species/generator 版本、Manifest、Seed/Memory IDs、RecallBundle 来源和失败样例；报告世界知识 top-k 命中率（目标 ≥95%）、身份/物种/unknown 边界与必需来源覆盖（100%）、重启/重放一致性（100%）、重复导入重复数（0）、未知实时巢伪事实数（0）、E1/E2/E3 结果和残余缺口。更新 conformance 时按 `target/inventory/references/verification/residuals` 五类证据记录。旧 E1 报告中的“雾谷/老橡树/山林”只能作为待修复反例，不能计入通过数。

指标按场景的 Canon/Seed ID 计算：命中必须出现在允许的 typed `RecallBundle` 来源中；改写/重启/重放的一致性比较稳定事实 ID、时间标签和关系/因果引用，不以模型措辞相似代替。

验证顺序固定为：合同/配置 → Genesis 校验 → Memory 导入与重启 → 领养隔离 → E2/E3 → 稳定后 E1 回归；失败按“精确失败项→受影响模块”逐层扩大，不在计划阶段运行这些检查。

### 5.3 需求追踪（冻结后不可删）

| 原始目标 | 本计划位置 |
|---|---|
| 世界知识总源、八类主题、地图和未知边界 | §3.1–§3.2 |
| 个体已学知识、Profile/Selfhood 边界 | §3.3 |
| 3–5 段连续经历、人物/地点/因果/赴地 | §3.3、§4.1 |
| 关系数量、方向、熟悉度、信任和来源 | §3.3、§4.2 |
| Genesis→Memory 正式加载、时间、幂等和失败恢复 | §4.1–§4.2 |
| RecallBundle、改写/重启/未知和无巢观测防虚构 | §4.3、§5 |
| published 物种范围和不扩大到 OPT-002/003/004 | §2、§3.2、§4、§6 |

## 6. 多方面审查与停止条件

在每个阶段结束、提交实现前各做一次短审查：

1. **范围审查：**是否仍只有知识密度、故事结构和 Genesis 加载；发现 OPT-002/003/004、真实巢或向量库内容就删回计划。
2. **Canon 审查：**名称、地点、物种状态、地图层级和 unknown 是否来自现有文档；任何未在 Canon 定义的名称、地点或设定都不得进入事实源。
3. **权威审查：**Config 是公共总源，Profile 是固定外显，Selfhood 是自我模型，Memory 是可检索个人脑，Prompt 不藏事实。
4. **数据审查：**来源、版本、别名、certainty、稳定 ID、发生时间/写入时间、Episode/关系引用是否齐全；是否可能半提交或跨 Elfie 泄漏。
5. **实现审查：**是否复用现有 SQLite/RecallBundle/配置 registry；任何 schema、Port、迁移或生产数据影响都暂停请求确认。
6. **评测审查：**事实、改写、关系、未知/反事实、重启、隔离、稀有词和三条过去线是否都有可重放证据；不能用旧 E1 的薄 fixture 冒充 OPT-001。

本次修订已补回原设计中缺失的条目字段、地图层级、物种合同、个体差异、Seed/Manifest、导入映射、Recall/unknown 规则和可执行评测格式。OPT-001 已完成配置注册、类型化 Genesis、source-first 导入、重启/幂等、typed E1 fixture、发布失败清理、Prompt/Selfhood 去重及 E2/E3 机器门；负责人体验复核属于 MEM-008 的 Stage 1 门，不再作为 OPT-001 实现残余。

**冻结判定：**本阶段以当前首版切片作为冻结实现基线。若后续出现新 schema、系统 Port、真实迁移、未批准设定或范围外模块，立即暂停并报告；本计划不自行扩大。

## 7. 交付清单

- 一份冻结的 Elfaria World Canon、物种知识和未知边界配置/版本；
- 一条 Canon → Genesis 三类 Seed → source-first Memory → RecallBundle 的可重放链路；
- Profile、Selfhood、Memory 三者边界及初始化 Manifest 证据；
- 覆盖矩阵、E1/E2/E3 结果、conformance 更新和未完成物种/残余清单；
- 本阶段不改现有生产数据，不声称长期记忆或 OPT-002/003/004 已完成；当前分支未创建提交、PR 或远端变更。
