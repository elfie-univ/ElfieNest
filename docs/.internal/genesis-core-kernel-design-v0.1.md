# OPT-001 最终设计：Elfaria 世界知识与 Elfie 个体初始化

> **状态：设计基线；第一版已按本文范围落地，未完成项见 OPT-001 执行计划。**
> 本文依据第一轮开工文档及现有 Elfaria、物种、Genesis、Memory 设计整理；后续实现不得超出本范围。

## 1. Scope

本阶段只打通一条链路：

```text
版本化的 Elfaria / 物种公共知识
        → Genesis 领养时个体化
        → Profile、Selfhood、初始 Memory
        → RecallBundle 支撑第一天的连续回答
```

结果应使新 Elfie 已有母星、物种、迷雾镇、生活、过去、人物和赴地经历；未知处明确说不知道，不用地球常识或临时编造补洞。

不做 OPT-002/003/004、真实巢观测、3D/身体、长期学习与压缩、向量库、多精灵共享或第二套存储。

## 2. 两层知识与权威

```text
World Canon + Species Canon
                ↓
             Genesis
                ↓
 Profile      Selfhood       Memory
                ↓
             RecallBundle
```

| 层 | 负责的事实 | 位置 |
|---|---|---|
| World/Species Canon | Elfaria 世界、迷雾镇和 Saevi/Tovren/Myelle 的公共设定及未知边界 | 源码 `config/`，版本化 |
| Profile | 姓名、物种、来源、外观及固定特质锚点；对外稳定 | 精灵运行目录配置 |
| Selfhood | 个体如何认识自己、价值、人格表达和行为倾向 | Brain 的自我初始化 |
| Memory | 这只 Elfie 实际学会的知识、Episode、关系及来源证据 | 现有 source-first SQLite |

Canon 不是个人记忆，Profile 不是百科，Prompt 不是事实源；Prompt 只保留必要身份锚点和防虚构规则。

## 3. 世界知识体系（公共总源）

世界知识回答“Elfaria 是什么”，不写某一只 Elfie 的私人传记。首版目标约 40–80 条可独立引用的原子事实，以覆盖为准。

| 主题 | 必须描述的方向 |
|---|---|
| 1. 世界总纲 | Elfaria 的身份、已知范围、世界与地球的总体关系 |
| 2. 运行与自然 | 物理基础、时间/昼夜/季节、自然规律、生态和生命共同规律 |
| 3. 地理与聚落 | 星球—区域—地点层级、地图、迷雾镇、设施和生活空间；明确三物种共居原因、聚落交往规则及未定义区域 |
| 4. 物种与生命 | Saevi、Tovren、Myelle 的共同身体、感知、需求、生命周期和共有常识 |
| 5. 社会与文明 | 家庭、族群、长老、礼仪、制度、经济、劳动、教育、技术和知识传播 |
| 6. 历史与文化 | 集体历史、语言、信仰/价值、食物、节庆、日常和文化差异 |
| 7. 地球与赴地 | 跨世界信号、地球侧建设、赴地计划、来地原因及两边文明差异 |
| 8. 知识边界 | common/可学习/受限等公共级别；已知、部分知道、听说、未知；来源、版本、别名和检索词 |

首版只冻结已有 Canon 能证明的 Elfaria 和迷雾镇内容；没有完整宇宙、全星球地图或未定义政治/天气等事实就保留未知，不能用故事生成填上。

每条公共知识至少有：稳定 `id`、`source`、`version`、`scope`、`topic`、`alias/search_terms`、`certainty`、`eligibility`，并可被检索和追溯。

## 4. 个体知识体系（单只 Elfie 的初始脑）

个体差异来自“固定身份 + 掌握的公共知识子集 + 自我模型 + 人生图 + 关系图 + 地球适应状态”，不是重新发明一套世界。

| 部分 | 初始化内容 |
|---|---|
| 固定身份 | Profile 的姓名、物种、出生/来源、外观、固定特质；不可漂移 |
| 自我与人格 | Selfhood 的自我描述、价值、边界、表达方式、人格倾向 |
| 已学世界知识 | 从 World/Species Canon 选出的个人子集；每项标掌握程度（知道/部分/听说/未知） |
| 生活背景与偏好 | 家乡和生活地点、技能、习惯、喜好、情绪触发点、重要体验和当前目标 |
| 人生经历 | 有顺序、互相引用的领养前 Episode；含人物、地点、结果、感受和影响 |
| 人际关系 | 家庭、朋友、邻居、长老/老师、赴地相关者和地球家庭；含角色、方向、熟悉度、信任和共同经历 |
| 地球适应与边界 | 已知、亲历、正在学习的地球事物，以及个人不知道的部分；不伪造实时巢事实 |

最小人生图：

- 一个明确家乡/生活地点；
- 3–5 个有先后关系的关键 Episode，至少一条“过去经历影响当前性格或选择”的因果链；
- 一段离开 Elfaria、参加赴地计划或抵达地球的经历；
- 关系目标：约 10–20 个认识过的人，3–5 个高显著人物，1–2 个反复出现人物；私人关系不会因同住迷雾镇自动跨 Elfie 共享。

精确日期未知时使用 life stage/temporal label；历史发生时间与写入时间分开。

## 5. Genesis 初始化合同

**输入**：World Canon 版本、Species Canon 版本及 catalog 状态、领养上下文、确定性 seed、受控 custom/CFHO 输入。

**输出**：

```text
ProfileDraft
SelfhoodSeed
KnowledgeSeed[]
EpisodeSeed[]
RelationshipSeed[]
InitializationManifest
```

三类 Seed 的边界：

- `KnowledgeSeed`：这只 Elfie 实际掌握的公共知识，不是个人经历；
- `EpisodeSeed`：个人亲历的过去，必须能组成上述人生图；
- `RelationshipSeed`：人物、地点与家庭的关系骨架，必须引用相关 Episode/Canon。

每条 Seed 具备稳定 `id`、来源、版本、scope、topic、alias/检索信息和 certainty；Episode 另含发生时间标签，Relationship 另含角色/方向/熟悉度/信任及引用。`personal_story` 只能是派生展示摘要，不是第四事实源。

生成顺序：

```text
校验 Canon/范围
→ 选择个体身份、知识子集和地点
→ 生成 Selfhood、Episode、Relationship
→ 校验物种、地点、年龄、时间线、因果、来源和未知边界
→ 写入 Manifest 并原子导入 Profile/Selfhood/Memory
```

模型只提出候选，确定性校验拥有约束；失败整包不提交半套人生史。同一 Manifest 重放必须幂等，不得复制节点或经历；Canon 新版本不得静默改写已有个体记忆。

## 6. 存储、加载与本阶段交付

### 存储/读取

1. `config/` 保存版本化 World/Species Canon、地图/地点和知识覆盖矩阵。
2. Genesis 只在领养时运行，把公共 Canon 编译成个人 Seed；不直接把百科写进 Profile 或 Prompt。
3. Profile、Selfhood 与现有 source-first Memory 各归其所有者；Memory 通过正式 Episode/来源路径保存知识、故事和关系。
4. Reasoning 只能从 `RecallBundle` 读取带类型、来源、版本和不确定性的内容；Memory 不直接读取 Profile、聊天历史或实时巢状态。
5. 每只 Elfie 使用独立命名空间；没有真实巢观测时，当前位置、天气、当天活动、动作和其他精灵状态一律未知。

### 本阶段要完成

- 冻结首版 Elfaria/物种/迷雾镇 Canon、未知边界和覆盖矩阵；
- 实现 Canon → `KnowledgeSeed[]`、`EpisodeSeed[]`、`RelationshipSeed[]` 的 Genesis 编译与校验；
- 走现有 source-first Memory → RecallBundle 正式加载路径，并清掉重复的丰富世界 Prompt；
- 对当前公开物种执行同一合同，未进入 catalog 的范围明确标注未完成。

### 验收

覆盖矩阵同时准备事实、改写、关系、未知/反事实问题；验证新领养、重启、重复初始化、来源追溯、稀有词召回、至少三个独立过去话题和跨 Elfie 隔离。目标是世界知识命中、来源覆盖和一致性达门槛，未知/实时巢问题伪事实为零，并通过 E2/E3、回归 E1。
