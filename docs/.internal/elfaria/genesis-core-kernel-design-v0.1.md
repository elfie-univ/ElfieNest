# Genesis 核心内核设计：Elfaria 世界知识衍生与个体初始化 v0.1

> 状态：总设计基线。本文件只定义“从世界设定产生哪些产物，以及 Genesis 如何使用它们”；它不是世界事实源、居民知识正文、执行计划或验收清单。
>
> 唯一的作者侧上游是[《Elfaria 自底向上世界设定》](elfaria-bottom-up-world-design-v0.1.md)。运行时不直接读取 Markdown，而是读取由它编译、审阅并校验后的机器知识包。

## 1. 核心目标

把一个上游世界设定稳定地转换成两类东西：

1. 人能读、能审查的居民知识；
2. 机器能加载、能检索、能供 Genesis 选择的结构化知识卡片。

然后，Genesis 从这些机器产物中选择一只具体 Elfie 在出生地、物种、家庭、经历和学习范围内真正应该知道的部分，生成它的 Profile、Selfhood 和初始 Memory。

总链路只有这一条：

```text
自底向上世界设定（唯一作者源）
        ↓
审阅、抽取、归一化（编译边界，不产生第二事实源）
        ├── 居民可读的公共知识文档
        ├── World Knowledge Cards（多个世界知识 YAML）
        ├── Species Knowledge Cards（物种知识 YAML）
        ├── 地图卡片与地图生成产物
        └── Genesis 可用的生成参数
                         ↓
              Genesis 个体化与确定性校验
                         ↓
       ProfileDraft + SelfhoodSeed + Memory Seeds
```

“抽取、归一化”是编译过程，不是一个需要人工继续维护的中间文档。它可以拆分、过滤、标注和拒绝内容，但不能凭空添加世界事实。

## 2. 权威边界与文档关系

### 2.1 四种不同的“权威”

| 层 | 作用 | 能否直接作为事实来源 |
|---|---|---|
| 自底向上世界设定 | 作者从宇宙、星球、环境、生物、物种、社会到聚落逐层推导完整世界；包含居民不知道的底层机制 | 是，唯一作者侧内容源 |
| 机器知识包 | 从上游设定编译出的、经校验的运行时输入；按文件和卡片组织 | 是运行时读取的权威产物，但不能脱离上游独立改设定 |
| 居民公共知识文档 | 机器卡片的居民视角投影，供人审阅、写作和检查 | 否，是派生阅读稿 |
| Genesis 个体包 | 某一只 Elfie 的身份、自我、已学知识、亲历和关系 | 否，只是个体化结果 |

因此：

- 不再维护一份与自底向上设定并列的叙述版 World Canon；
- 不从居民可读文档反向生成机器事实；
- 不把某只 Elfie 的故事、Profile 或 Prompt 反写成世界事实；
- 被上游删除或否定的能力、地点和规则，不能从旧卡片、旧合并结果或模型记忆中恢复；
- 当前已有的聚合文件只是实现现状，不改变这个目标关系。

### 2.2 底层设定不等于居民知识

自底向上文档中的第一层物理化学、能量机制、因果解释和数值参数，是造物者/作者侧知识。它们只在生成、校验和世界内部一致性需要时进入机器配置，不能自动变成居民记忆。

居民知识只保留居民能够：

- 亲眼看到、亲身经历、反复观察到的现象；
- 从家庭、师徒、公共记录或机构中学到的内容；
- 在本地社会中形成的解释、习惯和边界。

例如，底层可以有蒸发、凝结、守恒等作者机制；居民卡片可以写“看到下雨、河湖涨落、地面变干，并据此安排取水和出行”，不能因此写成居民知道完整水循环。类似地，“与地球遵循相同物理化学规律”是作者校验语句，不是居民知识。

## 3. 产物总览

### 3.1 World Knowledge Cards

世界知识卡片回答“Elfaria 的公共世界是什么”，但不是一个大 YAML 文件。它按数据形态和消费者拆成少数几个包：

| 卡片类别 | 主要内容 | 是否进入居民知识 |
|---|---|---|
| 世界与自然卡 | 世界身份、Solara、时间、昼夜、季节、天气、能量、生命环境和自然现象 | 只有可观察、可学习的部分进入 |
| 地理与地点卡 | 星球—区域—聚落—地点层级、地点关系、道路、方向、可达性和生活范围 | 地方事实按区域和经历进入 |
| 地图卡 | 每张地图的范围、比例/分辨率、坐标语义、图层、锚点、覆盖边界和地图资源 | 地图中的公共记录、方向和旅行信息可进入；生成算法不进入 |
| 社会与历史卡 | 家庭、治理、劳动、交换、技术、文化、集体历史和跨世界事件 | 公共事实按普及程度进入；公共事件不自动变成个人回忆 |
| 知识边界卡 | 常识/地方/专业/受限级别、观察限制、未知范围和适用条件 | 用于决定知道、听说、部分知道或不知道 |

这些类别共享同一个 `canon_version`、稳定 ID 和引用关系。卡片可以互相引用地点、物种、地图和事件，但不能复制另一张卡片的正文作为第二份事实。

### 3.2 Species Knowledge Cards

物种知识卡片回答“某种 Elfaria 生命共有的身体、感知、生命周期、生活经验和能力边界是什么”。它们由自底向上设定的生物演化层、物种能力层、社会层和聚落层共同推导。

物种卡只提供物种范围和群体先验，不能直接生成：

- 某只 Elfie 的人格、价值观或固定喜好；
- 某只 Elfie 的出生点、朋友或私人事件；
- 未经上游设定支持的新能力；
- 把地球上的狐狸、狗、猫常识强行套用到 Elfaria 物种上的结论。

物种机器包与生成参数要分开：

```text
config/species/catalog.yaml       # 注册表、版本和 published/draft 状态
config/species/<package>/
  species.yaml                     # 物种知识卡：共有事实和边界
  appearance.yaml                  # 外观生成控制、范围和相关性
  genesis.yaml                     # 个体化先验、阶段范围和偏好参数
```

`appearance.yaml` 和 `genesis.yaml` 是生成配置，不是居民百科，也不能作为独立世界事实源。人类可读的物种说明如果保留，只能是 `species.yaml` 的派生阅读稿。

### 3.3 其它派生产物

除世界卡和物种卡外，完整链路还会产生：

- **居民公共知识文档**：把可公开、可观察、可用居民语言表达的卡片渲染给人审阅；
- **地图资源**：地图图像、拓扑/路线数据和地图索引；地图资源必须有对应地图卡，不能靠图片本身充当事实源；
- **Genesis 输入视图**：按物种、区域、生活阶段、角色和知识级别建立可选择索引；这是编译索引，不是新知识；
- **个体初始化包**：`ProfileDraft`、`SelfhoodSeed`、`KnowledgeSeed[]`、`EpisodeSeed[]`、`RelationshipSeed[]` 和 `InitializationManifest`。

执行计划、执行清单、审查记录和临时证据不属于上述产物，不放进这条知识链，也不放进本设计文档。

## 4. World 包的目标文件结构

这是目标组织，不代表当前文件已经完成拆分。它遵守“按事实职责和数据形态拆分，不能为了拆分而拆分”的原则：

```text
config/world/
└── elfaria/
    ├── elfaria.yaml              # 世界包清单：ID、版本、包含哪些文件；不承载大段知识
    ├── world.yaml                # 世界身份、Solara、时间/昼夜和全球范围基线
    ├── nature.yaml               # 环境、季节、天气、水、能量、生命环境和可观察自然现象
    ├── geography.yaml             # 区域、聚落、地点、道路、方向、可达性和旅行关系
    ├── maps.yaml                  # 地图登记表、每张地图的范围、图层和生成来源
    ├── society-history.yaml       # 社会、文化、经济、技术、集体历史和跨世界事件
    └── knowledge-boundaries.yaml  # 知识级别、观察限制、未知边界和适用资格
```

每个文件的职责固定如下：

- `elfaria.yaml` 是包索引，不再成为所有世界知识的单一“大杂烩”；它声明文件集合、版本和兼容关系。
- `world.yaml` 放世界身份和全局基线，例如 Elfaria、Solara、本地日、本地年和已知范围。居民可读内容仍要经过观察视角过滤。
- `nature.yaml` 放自然环境和现象。作者机制、科学解释与居民能够说出的现象必须分字段或分可见性处理。
- `geography.yaml` 放语义空间关系：区域、聚落、地点、父子关系、相对方向、道路、旅行时间、访问条件和居住范围。
- `maps.yaml` 只放地图这种有范围、有图层、有资源的结构化产物；地图所表示的地点事实仍引用 `geography.yaml`。
- `society-history.yaml` 放社会和共同历史。公共事件与个人亲历必须有不同的卡片类型，不能混写。
- `knowledge-boundaries.yaml` 放“谁在什么条件下能知道什么”以及明确未知；它不能用来偷偷填补上游没有定义的内容。

当前代码中的 `config/world/elfaria.yaml` 仍是聚合形态时，它只能被视为过渡性的机器包。目标设计不允许再新增第二份聚合 World Canon；后续拆分必须保持同一版本、同一稳定 ID 和同一来源链。

## 5. 地图卡片与地图生成

地图是世界知识的一等派生产物，不是 `geography.yaml` 里随便加一段图片路径，也不是 Godot 物理地图的替代品。

### 5.1 每张地图必须独立登记范围

`maps.yaml` 中每张地图至少有以下信息：

```yaml
map_id: mistyville-town-center
version: 0.1
parent_map_id: mistyville-macro
scope: settlement
coverage: approved | partial | unknown
extent:
  coordinate_system: local_km
  bounds: {west: ..., east: ..., south: ..., north: ...}
  anchors: [skyreach_square, earthbound_station]
scale_or_resolution: "按地图类型定义"
layers: [terrain, places, roads, access]
asset_refs: [".../town-map.png"]
source_refs: ["bottom-up:...", "geography:..."]
generator_version: map-generator.v0.1
status: active | draft | unknown-boundary
```

`extent` 是这张地图自己的覆盖范围，不得用父地图范围代替。地图还必须说明：

- 它是宏观地形图、聚落图、部落中心图还是局部地点图；
- 它覆盖哪些已批准区域，哪些区域没有画出；
- 图上的锚点、地点和道路对应哪些稳定实体 ID；
- 图像是示意图还是可以支持路线/距离查询；
- 地图坐标、道路距离和旅行时间的关系；
- 地图版本和生成来源。

按当前自底向上设定，首版至少要能登记迷雾镇宏观图，以及迷雾镇中心、Saevi 部落中心、Tovren 部落中心、Myelle 部落中心四张局部图。未收敛的图保持 `draft`，不能被 Genesis 当成已确定的地点事实。

### 5.2 地图生成方法的边界

地图生成从自底向上设定的环境/资源层和聚落层取得输入，顺序是：

```text
自然锚点与已批准地点
        ↓
区域层级、空间关系和道路拓扑
        ↓
地图范围、坐标语义、图层和路线数据
        ↓
地图资源渲染与一致性校验
        ↓
地图卡片 + 地图资源 + 可引用的地点/路线事实
```

地图生成算法、网格划分、渲染参数和 Godot 坐标不是居民知识。居民只能获得被允许公开的方向、地点关系、道路、距离范围和旅行经验。Godot 仍然拥有房屋、几何、碰撞、导航和运行时位置；World Map 只拥有叙事/语义空间，不复制 Godot 的物理事实。

## 6. 卡片的共同结构与知识视角

所有可被 Genesis 或公共知识渲染器使用的原子卡片，至少具备：

```yaml
id: stable-card-id
version: 0.1
card_kind: resident_fact | public_record | generator_constraint | unknown_boundary
scope: world | region | settlement | place | species | event
topic: world | nature | geography | map | species | society | history | earth_relation
statement: "一条可独立引用的陈述"
aliases: ["居民或地球人可能使用的称呼"]
retrieval_terms: ["改写问法", "稀有词"]
level: common | regional | group | specialist | restricted
certainty: high | bounded | provisional
status: active | draft | unknown-boundary
source_ref: "bottom-up 的稳定章节/条目引用"
related_ids: []
eligibility: [all | species:saevi | region:mistyville | role:healer]
```

其中：

- `card_kind` 决定它是居民能知道的事实、公共档案、只给生成器的约束，还是明确未知；
- `level` 是社会传播程度，不是模型置信度；`certainty` 是来源确定性；
- `scope` 限制适用范围，区域事实不能升级成整颗星球事实；
- `source_ref` 必须能回到自底向上设定，不能只写“模型生成”；
- `generator_constraint` 可以被 Genesis、地图生成器或校验器使用，但不能进入居民 `KnowledgeSeed`；
- `unknown_boundary` 是有效结果，不是缺陷，不得被地球常识、模型补全或故事需要覆盖。

### 6.1 居民公共知识文档

居民可读文档与机器卡片是同一编译结果的两种投影；实现上通常由机器卡片过滤、翻译而来，但二者都不能成为上游事实源。规则是：

1. 只选择居民能观察、经历、听闻或从公共记录学到的卡片；
2. 采用古代/前工业居民能理解的语言；现代科学术语只可在作者审校注释中出现；
3. 保留区域、群体、专业、受限和未知标签；
4. 地球常识只用于说明差异，不能替换 Elfaria 自己的事实；
5. 同一稳定卡片 ID 必须能从人读文档追溯到机器卡和上游章节。

所以，“一年有多少本地日、当地只有雨季和旱季、迷雾镇可以有雾但没有霜雪”可以成为公共知识；“蒸发的分子过程”和“Elfaria 遵循与地球相同物理化学规律”不能因为出现在底层设定中就成为居民记忆。

居民文档不是机器卡的完整转储。地图生成参数、作者机制、Godot 坐标、未公开设施细节和个体记忆都必须被过滤掉。

## 7. Genesis 个体化合同

### 7.1 输入

Genesis 只读取已编译、已校验的机器输入：

- World 包及其固定 `canon_version`；
- Species 包及 `catalog.yaml` 的发布状态；
- `appearance.yaml`、`genesis.yaml` 等生成参数；
- 领养上下文：物种、生活区域、年龄/阶段、语言和受控个体偏好；
- 确定性的生成 seed。

Genesis 不直接读取自底向上 Markdown、居民知识文档、旧物种卡、聊天内容或 Godot 场景来创造世界事实。

### 7.2 选择规则

```text
World/Species Cards + 生成参数 + 领养上下文
                         ↓
             按 scope / level / eligibility 选择
                         ↓
              Profile / Selfhood / Memory Seeds
```

- `common` 且对该个体适用的居民事实，通常进入 `KnowledgeSeed(mastery=known)`；
- 区域、物种、群体和生活阶段相关内容，按出生地、经历和学习条件进入 `known`、`partial` 或 `heard`；
- 专业或受限内容必须有角色、教育、工作或亲历依据；
- 地图卡通常提供出生/居住地点、路线和公共方向，不把整张地图图片或生成算法塞入 Memory；
- 共同历史可以进入公共知识；只有个体确实参与、见过或被可靠人物告知的部分，才能进入个人 Episode；
- `unknown_boundary` 必须保留为不知道/只知道范围，不能通过“故事完整性”强行补齐；
- 物种先验可以约束身体和常见感知倾向，但不能决定人格、朋友、职业或具体记忆；
- 任何被上游标记为删除、否定或未批准的能力，均不得进入 Profile、Selfhood、Memory、地图或生成参数。

### 7.3 固定输出

```text
ProfileDraft
SelfhoodSeed
KnowledgeSeed[]
EpisodeSeed[]
RelationshipSeed[]
InitializationManifest
```

边界如下：

| 输出 | 来源和作用 | 不负责什么 |
|---|---|---|
| `ProfileDraft` | 姓名、物种、来源地点、外观和固定身份锚点 | 世界百科、完整人生、关系网 |
| `SelfhoodSeed` | 个体如何理解自己、价值、边界、表达和人格倾向 | 公共事实第二副本 |
| `KnowledgeSeed[]` | 个体实际掌握的 World/Species 卡片子集 | 个人亲历故事 |
| `EpisodeSeed[]` | 个人曾经经历的事件及其地点、人物、结果和影响 | 把公共历史冒充亲身经历 |
| `RelationshipSeed[]` | 个体认识的人、地点和关系骨架 | 让同镇 Elfie 自动共享社交图 |
| `InitializationManifest` | 输入版本、seed、输出 ID、哈希和提交状态 | 新的世界设定 |

Genesis 只能在已批准卡片上做个体化；模型可以提出候选，确定性校验负责物种、地点、时间、来源、未知边界和因果关系。失败时整包拒绝，不能留下半套 Profile 或 Memory。

## 8. 不可破坏的总原则

1. **单一上游**：所有世界、物种、地图和共同历史事实最终都能回到自底向上设定；没有第二份叙述事实源。
2. **编译而非再创作**：抽取器、地图生成器和 Genesis 可以转换结构、生成索引和做个体化，但不能偷偷增加设定。
3. **机器/人读一一对应**：人读文档与机器卡片是同一批经过筛选的事实的两种表达，不是两套内容。
4. **机制/知识分开**：作者知道的机制、生成算法、渲染参数和 Godot 物理事实，不能自动升级为居民知识。
5. **范围不可扩大**：世界、区域、地点、物种、群体和个体的适用范围必须显式标注。
6. **未知优先保留**：没有观测、记录或上游依据时，结果就是未知；不能用地球常识或模型流畅性补洞。
7. **删除具有传递性**：上游删除/否定的内容必须从所有派生卡、索引、Seed 和提示词中消失，不能被旧文件或 Git 合并带回。
8. **运行时只吃机器包**：Genesis 和 Memory 不直接读取 Markdown；机器包的版本、来源和状态必须可校验、可追溯。
9. **个体不反写世界**：个体的新经历进入自己的 Memory，不修改 World/Species Cards；世界版本更新也不静默改写旧个体记忆。
10. **本文件不承载执行状态**：计划、清单、审查记录和临时证据另行管理，不混入总设计和知识产物。
