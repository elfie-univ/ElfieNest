# Genesis 核心内核设计：世界知识与个体初始化（OPT-001）

> **版本状态：Version 1 snapshot（待审阅）**
> 本文件先保存当时讨论形成的设计版本，作为后续逐项对照的基线；它不是已批准的实现契约，也不表示当前代码已经具备下述能力。
>
> **已取代：** 现行目标是 [Genesis v0.2](./genesis-core-kernel-design-v0.2.md)，并受 ADR-0033、
> Elfie 2.3 与 Brain 1.5 约束。本文中的 Profile 来源/版本字段、长期 Manifest 和提交后重放
> 设想只保留为历史草稿，不能用于新实现。

## 1. 文档定位与范围

本设计只覆盖 Genesis 的“核心内核”：

```text
源码中的 Elfaria / 物种世界 Canon
        ↓
Genesis：从世界设定生成一只具体 Elfie 的初始化材料
        ↓
Profile（外部稳定身份） + Selfhood（内部自我模型） + Memory（可追溯知识/故事/关系）
```

本阶段的目标是让新领养的 Elfie 在第一次对话时已经有可追问、可连续、可溯源的世界知识和个人过去；不是从当天第一句话才开始存在。

明确包含：

- 世界级 Canon、物种级共同知识、个体级已学知识的分层与组织；
- 3–5 段有关联的领养前个人经历，以及来地球/加入赴地计划的经历；
- 个体的自我认知、偏好、技能熟悉度、重要人物和地点关系骨架；
- Genesis 输入、输出、确定性、版本固定和导入 source-first Memory 的路径；
- Profile、Selfhood、Memory 三者的职责边界及初始目录布局；
- 未知边界、没有真实巢内观测时的防虚构规则和验收矩阵。

明确不包含：真实精灵巢观测、Godot/3D 外形与物理、长期记忆压缩、向量数据库、多精灵互动、推理模块重构、模型选型或新的持久化系统。

## 2. 不可破坏的核心原则

1. **Canon 是世界事实源。** 世界和物种的稳定设定只从源码 `config/` 的版本化内容读取；运行目录的用户配置不反向改写世界 Canon。
2. **Genesis 是生成边界。** Genesis 读取世界/物种设定和受控的领养输入，产生一组有稳定 ID、来源和版本的初始化材料；它不直接把丰富世界资料塞进 Prompt 或 Profile。
3. **Memory 是个人可检索事实源。** 个体“知道什么、经历过什么、认识谁”必须经正式 Memory 写入路径保存，并能在 `RecallBundle` 中被 Reasoning 读取。
4. **Profile 只保存外部稳定身份。** 它保存客观、不可随意改写的身份与外观锚点；不承担传记、关系网或世界百科。
5. **Selfhood 不是世界 Canon。** Selfhood 保存该个体对自己的认知、人格倾向、价值、偏好和表达习惯；这些是个体种子，不替代来源记忆。
6. **历史时间与写入时间分开。** 事件发生在过去的哪个 life stage/temporal label，与记录何时写入数据库是两个字段；未知精确日期时不伪造日期。
7. **未知必须保持未知。** 没有来源的细节不能因为故事需要而被补全；尤其没有真实巢内观测时，不能生成当天巢内活动、天气、位置或动作。
8. **同一镇不等于共享社交图。** 每次离线领养生成独立的个体命名空间和关系图；共同生活地点只提供潜在的世界背景，不自动让两只精灵相互认识。

## 3. 四层数据与权威边界

| 层 | 主要内容 | 权威/存放位置 | 不能承担的内容 |
|---|---|---|---|
| World Canon | Elfaria 的世界规律、历史、地理拓扑、社会与文化、已知未知 | 源码 `config/world/`（发行副本 `resources/config/`） | 某一只 Elfie 的私人经历 |
| Species Canon | Saevi/Tovren/Myelle 的共同身体、感知、习性和共同常识 | 源码 `config/species/` 及其世界知识扩展 | 个体人格、出生点和私人关系 |
| Profile / Selfhood | 外部稳定身份；内部自我模型、人格和表达 | 每只 Elfie 的运行目录 `Config`/Brain 约定位置 | 世界百科、可追溯事件原文 |
| Memory | 个体学过的知识、过去 Episode、关系与证据投影 | source-first Memory Store（现有 SQLite/RecallBundle） | 取代 World Canon 或记录无来源的实时巢状态 |

建议的每只 Elfie 运行目录语义（具体文件名服从现有装配代码）：

```text
<elfie-home>/
  profile/                 # Profile：稳定身份/外观/来源锚点
  brain/                   # Selfhood 与认知初始化材料
  memory/                  # source-first Memory（Episode、知识、关系、证据）
```

`personal_story` 之类的展示文本只能是由 Profile/Selfhood/Memory 派生的预览，不是新的事实来源。

## 4. 世界知识体系（World Canon）

### 4.1 组织方式

首版不试图一次完成整个宇宙，只建立 Elfaria 的可扩展骨架，并先把已确立的 `迷雾镇（Mistyville）` 作为当前可叙述区域。建议源文件组织如下：

```text
config/
  world/
    catalog.yaml                 # 世界包、版本、可用区域索引
    elfaria/
      world.yaml                # 世界身份、基础规律、已知边界
      map.yaml                  # 叙事地图/地点拓扑，不是 Godot 坐标
      knowledge.yaml             # 主题化知识条目
  species/
    catalog.yaml
    saevi.yaml / tovren.yaml / myelle.yaml
```

此处是目标组织；当前代码是否已有对应文档注册、装载器和测试，需在实现阶段按配置管理契约补齐，不能把目标路径当作现状。

### 4.2 世界知识的主题提纲

每个主题先有少量稳定、可回答的骨干事实，再逐步填充细节。首版主题如下：

1. **世界身份与边界**：Elfaria 的名称、已知范围、与地球的关系、当前叙事视角；哪些地区/时代尚未定义。
2. **基础物理与自然规律**：昼夜/季节等已确定的自然现象、能量和材料的常识、原生感知现象（如 Aethersense 仅记录已确认部分）；未定机制必须标未知。
3. **生态与生命环境**：主要环境类型、资源与生物之间的基本关系；不凭空扩展未定的大陆、森林或气候带。
4. **地理与叙事地图**：世界 → 已知区域 → 迷雾镇 → 已批准地点的层级、相对方向、距离/路径的叙事描述；不写 Godot 坐标。
5. **物种与身体**：Saevi（灵狐）、Tovren（灵犬）、Myelle（灵猫）的共同体征、感知偏向、生命周期与物种共有常识；物种设定不能直接决定人格。
6. **聚落、设施与生活地点**：迷雾镇是什么性质的聚落、公共设施和不同地点的用途；“在哪里生活”与“谁实际去过”分开。
7. **社会、族群、家庭与长老**：家庭/亲属/邻里/长老等关系类别、决策和传承的已知规律；未定义的政治制度、阶层规模不补写。
8. **历史与集体记忆**：已确认的时代顺序、跨世界信号、赴地计划、地球转移阵列建设/稳定等共同历史；历史事实与个体亲历分开。
9. **经济、工作与资源交换**：只定义足以解释日常生活的生产、交换、照护和工作概念；详细货币、产业统计和宏观制度在未定时保持未知。
10. **文化、语言、食物与日常**：问候、叙事习惯、食物/材料、休息与庆祝等可复用常识；具体偏好属于个体。
11. **教育、知识传播与知识分级**：知识如何从家庭、社区、长老、工作或专门场所获得；区分人人常识、区域常识和少数专长。
12. **技术、信息与赴地适应**：本地技术/记录方式、跨世界通信和赴地计划的公共事实；地球生活的适应规则不等于当天巢内观测。
13. **情绪与重要体验的文化语境**：哪些体验在该社会中被视为重要、如何表达安慰/害怕/思念；个体的真实情绪和回忆仍由 Selfhood/Memory 保存。
14. **明确未知与反事实边界**：尚无 Canon 的地点、人物、天气、政治细节、实时活动和个人隐私，统一列为 unknown boundary，并指导回答“我不知道/我只听说过”。

### 4.3 地图与迷雾镇规则

- `map.yaml` 只描述叙事拓扑：包含关系、方向、可达性、地点用途和已知别名；不承担渲染、碰撞、导航或实时位置。
- 当前 Canon 只保证 Elfaria、迷雾镇及已批准的地点关系；迷雾镇不是整个星球，也不宣称是首都或完整政治中心。
- 镇的空间和人口密度要足以解释：不同离线领养实例即使都来自迷雾镇，也可能生活在不同片区/家庭网络，彼此没有见过或没有建立关系。这个是生成约束，不凭空增加未在 Canon 中出现的地名。
- 具体出生点由个体 Genesis 在已批准地点集合中确定；它只能引用地图中存在的地点，且要标注是出生/居住/到访哪一种关系。
- 三种物种共存的原因应作为世界/聚落 Canon 的一条可回答事实（例如共同聚落、互补生活和赴地计划的共同背景）；具体人口比例、完整社会结构若尚未定稿则保持未知。

### 4.4 知识条目最小字段

每一条可被 Genesis 或 Memory 使用的知识，至少具有：

```yaml
id: world.elfaria.mistyville.<stable-id>
version: 0.1.0
scope: world | region | settlement | place | species
topic: physical | ecology | geography | species | society | history | economy | culture | education | technology | adaptation | unknown
statement: "可独立回答的一条事实"
aliases: ["用户可能使用的称呼"]
retrieval_terms: ["稀有词", "同义问法"]
level: common | regional | specialist
certainty: canonical | bounded | provisional
status: active | unknown-boundary
source_ref: "Elfaria Canon 文档/条目 ID"
related_ids: []
```

`level` 描述该知识在 Elfaria 社会中的普及程度，不描述模型置信度；`certainty` 描述 Canon 的确定性。个体初始化时再把它投影为 `known`、`partial`、`heard` 或 `unknown`，不能把社会上“有人知道”自动变成该个体亲身知道。

## 5. 物种合同

所有公开可领养物种必须遵守同一套 Genesis/Memory 合同：

- 物种包提供共同事实、共同感知/身体约束、常见生活语境、别名和未知边界；
- 个体包另行提供人格、出生/居住地点、已学知识子集、Episode 和关系；
- 物种不能决定 Big Five、价值观、具体朋友或完整人生；
- 当前公开范围必须以 `config/species/catalog.yaml` 和发布状态为准。基线事实是 Saevi、Tovren 已发布，Myelle 仍是 draft；不得把 draft 或未列入目录的物种宣传为已完成。

## 6. 个体初始化知识（Individual Knowledge）

个体知识不是一张“随机故事卡”，而是由以下相互关联的部分组成。

### 6.1 个体固定身份（Profile）

Profile 只放外部需要稳定读取的客观锚点：稳定 ID、姓名、物种、出生/来源地点引用、外观/虚拟形象所需的不可变字段、来源和版本。它不放丰富世界知识、Big Five、关系网、事件正文或当前状态。

### 6.2 内部自我模型（Selfhood）

Selfhood 是精灵对“我是谁”的内部认知：Big Five 或等价人格种子、行为锚点、价值/边界、偏好、重要体验的情绪意义、语言/表达风格、对自己物种和赴地身份的定位。它可以影响回答方式，但每个可验证事实仍需回到 Memory/Canon。

### 6.3 已学世界知识子集（KnowledgeSeed[]）

Genesis 从 World/Species Canon 按个体经历、教育、生活地点和能力抽取一个子集：

- 人人应掌握的常识通常为 `known`；
- 区域性或工作相关知识可为 `known`/`partial`；
- 长老/专门人员掌握的知识可为 `heard` 或 `unknown`；
- 每条种子保留原始 `source_ref`、`level`、`certainty`、别名和检索词；
- 世界事实的“知道”与个人的“亲历”分开，不能用一条知识种子代替 Episode。

### 6.4 最小人生图（EpisodeSeed[]）

首版为每只精灵生成 3–5 个有顺序的领养前 Episode：

- 一个明确的家乡/生活地点引用；
- 1–2 个反复出现的重要人物；
- 3–5 个有先后关系的关键事件；
- 至少一条“过去经历 → 当前性格/选择”的因果联系；
- 至少一个加入赴地计划、准备来地球或抵达 ElfieNest 的事件；
- 事件时间用 `life_stage`/`temporal_label` 或有依据的范围表达，另存 Memory 写入时间；
- 每个 Episode 有稳定 ID、摘要/原文、前后关系、参与者/地点引用、结果、因果效果和 `source_ref`。

### 6.5 关系骨架（RelationshipSeed[]）

关系不是只保存一个主人节点，而是初始化的社会记忆：

- 建议每个个体有约 10–20 个“认识过的人”的可扩展集合；
- 其中 3–5 个是高显著人物，1–2 个在故事中反复出现；
- 关系类型至少能区分家庭/亲属、朋友/邻居、长老/老师、赴地计划相关者和地球主人；
- 每条关系记录熟悉程度、情感/信任方向、共同 Episode、最后已知状态和未知边界；
- 离线模式下只在本个体命名空间写入关系，不创建跨实例共享人物事实；主人关系与 Elfaria 过去关系分开。

### 6.6 其他个体差异

除知识、Episode 和关系外，Genesis 可以为个体初始化以下可追溯差异：出生/居住/到访地点，技能与熟悉度，日常习惯，喜欢/不喜欢的食物和活动，语言能力与表达习惯，对地球环境的适应状态，尚未解决的问题和明确不知道的内容。它们分别归 Selfhood、Knowledge 或 Memory，不得混成 Profile 的自由文本。

## 7. Genesis 输入、输出与过程

### 7.1 输入

- 固定的 World Canon 包 ID/版本（Elfaria）；
- 物种包 ID/版本（仅目录中允许领养的物种）；
- 确定性的 master seed 或等价生成上下文；
- 领养上下文（赴地计划、抵达方式、主人/家庭的最小信息）；
- 已批准的 `custom_input`/CFHO 扩展输入（只影响允许的个体差异，不覆盖 Canon）；
- 可选的已生成身份候选（姓名、Profile 锚点等）。

### 7.2 输出

```text
GenesisBundle
├── ProfileDraft
├── SelfhoodSeed
├── KnowledgeSeed[]
├── EpisodeSeed[]
├── RelationshipSeed[]
└── InitializationManifest
```

Manifest 固定 World/Species Canon 版本、生成 seed、条目 ID 列表、来源、校验信息和导入幂等键，使重启或重复领养不会产生第二套事实。

### 7.3 生成顺序

1. 校验 World/Species 包版本、公开物种范围和 unknown boundary。
2. 确定个体身份/出生点候选，只从批准的地图地点和物种约束中选择。
3. 生成 Selfhood 与个体已学知识子集。
4. 生成连贯的 Episode 时间序列和至少一条因果影响。
5. 从 Episode/生活地点派生关系骨架，并加入赴地计划与主人关系。
6. 形成 ProfileDraft 与 Manifest；把展示用故事作为派生视图。
7. 通过正式 source-first Memory 路径提交，而不是直接写 Profile、Prompt 或无来源图节点。

## 8. Memory 导入与读取契约

- `KnowledgeSeed[]` 作为带 Canon/approved-seed 证据的个人知识记录进入现有 Memory Store；
- `EpisodeSeed[]` 先写 `ClosedEpisode`，再按现有投影规则生成事件/节点/断言/证据；
- `RelationshipSeed[]` 写关系节点、断言和共同 Episode 证据；
- 所有记录使用稳定 ID、来源版本、scope/topic/alias/certainty 和导入幂等键；
- 历史发生时间写 Episode 的时间字段，数据库 `created_at`/写入时间只表示导入时刻；
- 初始化成功后，RecallBundle 能同时返回 typed nodes、assertions、paths、episodes、evidence 和 conflicts，供 Reasoning 使用；
- 重启后按相同 manifest 重放应得到相同事实集合，不重复追加；Canon 新版本不会偷偷改写已有个体的历史记忆，需要显式迁移策略（本阶段只设计，不实施迁移）。

## 9. 未知与现实观测边界

回答应区分：

1. Canon 已知的世界事实；
2. 该个体从 Canon 学过的知识；
3. 该个体亲历并有 Episode 证据的过去；
4. 当前巢内真实观测（本阶段没有）。

没有第 4 类来源时，不能声称今天在巢里做了什么、巢内天气/位置如何、刚刚见过谁或发生了什么动作。对未知、反事实和超出 scope 的追问，返回不确定性或“不知道”，不能用流畅叙述掩盖缺证据。

## 10. 验收矩阵（设计目标）

对八类以上世界主题和个人主题分别准备：事实问法、改写/同义问法、关系问法、未知/反事实问法。验收至少覆盖：

- 新领养后可连续追问三个以上独立过去话题；
- 不同问法、进程重启后的事实和来源一致；
- 人物、地点、结果、因果都能追溯到 Episode、approved seed 或版本化 Canon；
- 罕见词可以从 Episode 文本召回；
- 无真实巢观测时当天活动/天气/位置/动作的伪事实数为零；
- 记录事实命中率、来源覆盖率、重启一致性、未知问题伪事实数和残余缺口；
- 至少对当前公开可领养物种逐一验证相同合同，明确 draft/未支持范围。

## 11. 本阶段的窄实施顺序（待批准后执行）

1. 以本设计为目标，先盘点 `config` 文档注册、Genesis 合同/初始化器、Memory Store/RecallBundle 和现有测试的事实差距。
2. 在不重建数据库的前提下补齐版本化 World/Species 配置骨架和最小内容切片。
3. 扩展 Genesis 合同，使 `KnowledgeSeed[]`、结构化 `EpisodeSeed[]`、`RelationshipSeed[]` 能携带来源、时间和因果字段。
4. 让初始化器沿现有 source-first 路径导入，并保持 Profile/Selfhood/Memory 隔离和幂等。
5. 补充覆盖矩阵与 E2/E3 相关确定性、重启、未知边界测试，再据证据更新执行计划和 conformance 台账。

本顺序不授权修改 OPT-003/OPT-004，不引入真实巢、长期压缩、向量库、多精灵互动或新的记忆存储。

## 12. 已知现状提醒

当前基线代码仍可能只有旧的五条通用 Memory seed、没有独立 `KnowledgeSeed` 和完整结构化事件时间/因果字段；本文件描述的是待实现的目标设计。任何“已支持/已通过”的结论必须以实际代码、测试和可重放证据为准。
