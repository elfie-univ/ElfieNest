# Elfie 顶级模块设计

> 状态：已确认设计
> 确认日期：2026-08-11
> 修订日期：2026-09-01；已与 Elfie 契约 2.3、ADR-0033 对齐
> 性质：跨版本目标目录和模块所有权设计，不代表当前源码已经完成迁移，也不是现行契约
> 暂不包含：模块通信协议、事件 Schema、调用时序和迁移实施方案

> 设计关系：**所属模块：**Elfie；**上级设计：**整个系统全局设计（独立的上级设计，本次未移动）；
> **下级设计：**Brain、Embodiment、Communication 和 Genesis；**规范性契约：**[系统架构契约](../../contracts/system.md)；
> **当前架构：**[当前架构](../../architecture/)；**一致性台账：**[一致性台账](../../conformance/)；
> **领域资料来源：**Product 与 Elfaria 稳定资料标识。

## 1. 设计目的

本文设计“一只完整 Elfie”在目标架构中的顶级目录、一级模块、数据所有权和禁止边界。

本文只回答：

1. 顶级模块有哪些；
2. 每个模块拥有什么；
3. 哪些概念不能再作为顶级模块；
4. Genesis、Factory 和 Elfie Facade 分别是什么；
5. 后续代码迁移必须遵守哪些前置条件。

模块之间的通信事件、输入输出契约、并发顺序和错误协议，等待相关设计合并后另行统一定稿。本文
不得用临时接口替代那份后续规约。

## 2. 目标顶级目录

```text
elfie/
├── profile/              # 不可变外部身份锚点与虚拟外貌
├── brain/                # 持续心理状态、认知、活动与自主治理
├── nervous_system/       # 具身感知、信号处理、反射与动作适配
├── body/                 # 虚拟/实体躯体、唯一身体权威与切换状态
├── communication/        # 数字联系人、渠道、会话、消息与回执
├── genesis/              # 一次性生命初始化规则与创建产物
├── elfie.py              # 一只完整 Elfie 的薄门面
└── factory.py            # 已有 Elfie 的技术装配与恢复
```

这是一份顶级职责结构，不在本阶段定义各目录内部的文件清单。

## 3. 五个运行期一级模块

### 3.1 Profile

Profile 保存这只 Elfie 创建后不再变化的外部客观档案。它是一级模块，但不是持续运行的
循环系统，也不是创建账本。

```text
ElfieProfile
├── Identity
│   ├── elfie_id
│   ├── name
│   ├── species
│   ├── 适用时的固定性别
│   ├── 稳定年龄 / 出生锚点
│   └── 不可变个人出身 ID 与冻结名称
├── VirtualAppearance
│   ├── appearance_genome
│   ├── morphology
│   ├── proportions
│   ├── face / fur / coat
│   └── Godot 可消费的语义外貌规格
└── schema_version        # 仅技术 envelope
```

Profile 不保存：

- 当前年龄；只保存出生时间，年龄动态推导；
- 大五人格、乐观或悲观、兴趣和表达倾向；
- 记忆、人生事件和人物关系；
- 自我认知和能力自我评价；
- 情绪、能量和驱力；
- 工具、数据、联系人和动作权限；
- 当前活动身体；
- 实体玩具型号、状态和外形；
- 当前通信渠道和会话。
- 世界知识/Canon、资料包引用；
- 生成器/模型/策略版本、生成 Seed、用户选项或问卷答案。

“不会变化”不是进入 Profile 的充分条件。一个已经发生的童年事件可能不会改变，但它仍然属于
Memory；母亲是谁可能不会改变，但仍然属于 Relationship；离开、培训、抵达与领养也都是
Memory 事件。Profile 只保存严格外部档案白名单。

### 3.2 Brain

Brain 拥有一只 Elfie 会持续变化、学习和成长的心理状态及认知活动，包括：

- Personality、Self Model 与稳定规范；
- Memory、Knowledge 与 Relationship；
- Emotion；
- Energy、Homeostasis 与 Circadian Rhythm；
- Motivation 与 Drive；
- Perception、Attention 与三类事件 Lane；
- Cortex、Planner、Skills、Tools 与受限 Worker；
- Executive 与跨回合 Activity；
- Offline Cognition / Night Work；
- Capability Envelope、预算与自主决策；
- 结构化决定、内部触发和执行回执反馈。

Genesis 从同一个已校验创建 Bundle 并列物化 Profile 与 Brain 拥有的 Selfhood。Profile 仍是
不可变外层档案，但普通 Brain 运行期不再把它作为上下文来源。Selfhood 冻结的
`identity_core` 提供 Brain 身份，`adaptive_self` 表达这只 Elfie 缓慢稳定的自我理解与
表达方式。更早的运行时 Profile 锚点解释由聚焦的
[Selfhood 设计](./brain/elfie-selfhood-and-fixed-model-header.md)取代。

### 3.3 Nervous System

Nervous System 只属于具身线路，负责：

- 当前权威身体的传感器输入；
- 身体信号标准化、过滤和来源保留；
- 确定性的低延迟安全反射；
- 物理限制与动作可行性约束；
- 将大脑高层动作适配到当前身体；
- 身体动作的真实执行回执。

Nervous System 不处理数字聊天，不拥有人格和记忆，也不作开放式社会决策。

### 3.4 Body

Body 拥有两个可用躯体类型和唯一的具身权威：

- Godot 虚拟躯体；
- 实体玩具躯体；
- `selected_body`；
- `VIRTUAL_ACTIVE`；
- `SWITCHING_TO_PHYSICAL`；
- `PHYSICAL_ACTIVE`；
- `SWITCHING_TO_VIRTUAL`；
- 切换事务、代次、回滚和恢复；
- 身体能力、连接状态和动作执行状态。

虚拟与实体二选一，任何时刻只有一个动作权威。`Headless` 不能成为第三种产品身体或正常生命状态；
如果保留，只能作为测试或开发替身。

Body 不拥有 Profile 中的虚拟外貌。它读取 Profile 的 VirtualAppearance 并交给 Godot 呈现；实体
玩具外形是设备事实，不写回 Profile。

### 3.5 Communication

Communication 只属于数字通信线路，负责：

- 联系人与人物标识的渠道映射；
- 渠道注册、连接和可达性；
- 会话；
- 收件箱与发件箱；
- 文本、语音消息和附件的通信封装；
- 回复现有会话和主动建立新会话；
- 发送、失败、重试、去重、超时和回执。

Communication 不控制身体，不拥有人格、记忆或社会判断。大脑决定与谁、为何以及表达什么，
Communication 负责真正接通和传送。

## 4. Genesis：创建流程，不是第六个运行器官

`genesis/` 保存生命初始化的领域规则。它只在领养创建阶段运行，完成后不继续拥有生成出来的
数据。资料只有一个向下方向：`CreatorWorldSkeleton -> ResidentKnowledgeBaseline ->
GenesisSourcePackage -> Genesis`；已接受领养答案与受控随机源只在最后一步加入。

Genesis 形成临时 `GenesisBundle`：

```text
GenesisBundle
├── ProfileDraft
├── SelfhoodSeed
├── KnowledgeSeeds
├── RelationshipSeeds
├── EpisodeSeeds
├── 其他明确归属 owner 的启动 Seed
└── 最小技术提交回执草稿
```

完成一致性校验后分别提交：

| 生成产物 | 最终所有者 |
| --- | --- |
| 外部客观身份锚点与虚拟外貌 | Profile |
| 内部身份与初始人格 | Brain / Selfhood |
| 初始已知世界/专业/地方知识 | Brain / Memory |
| 不超过 5 个关键领养前事件 | Brain / Memory |
| 初始人物关系 | Brain / Relationship |
| 最小 Schema/输出摘要、完成状态和幂等结果 | Profile 之外的技术提交回执 |

身份解析、生活上下文、个人知识资格/掌握、人物、关系、经历和 owner 专属 Seed 策略只由
确定性 Genesis 编译器决定，不能由 App、Infrastructure 或模型决定。模型只能在事实冻结后
渲染受限、非权威措辞。以下内容同样不由生成模型自由创造：

- Capability Envelope；
- 工具、文件和联系人权限；
- 真实设备能力；
- 实际可用通信渠道；
- 模型和工具预算；
- 安全边界；
- 本机主人账户的真实绑定。

这些来自产品配置、真实设备和应用用例，并在初始化时被确定性绑定。

### 4.1 创建输入清理与后续学习

Genesis 必须在第一次醒来前完成最小完整个体：Profile、Selfhood、实际初始知识、关系骨架和
不超过 5 个关键历史事件。问卷答案、`LifeContext`、`PersonalGenesisPlan`、资料包绑定、生成
Seed 和模型投影输入只存在于未完成创建事务中，并在成功提交或终止失败后删除。

普通启动只恢复最终 owner 记录，不能重放 Genesis，也不要求旧资料包。后续知识或传记细节只能
通过另行批准的真实学习/Memory 路径进入；Night Work 不得使用遗留 Genesis Plan 发明历史、
修改 Profile 或成为永久后台编剧。

## 5. Factory、Facade 与 Bootstrap 的区别

### 5.1 Factory

Factory 负责从已存在的数据和外部依赖装配或恢复一只 Elfie。它不生成人生故事，不拥有任何生命
状态，也不重新实现 Brain、Body 或 Communication 的算法。

### 5.2 Elfie Facade

`elfie.py` 是一只完整 Elfie 的薄门面，不是独立系统。它负责：

- 保证内部模块绑定同一个 `elfie_id`；
- 暴露启动、停止和恢复入口；
- 提供身体事件、通信事件和身体切换的受控入口；
- 把操作委托给正确的内部模块；
- 防止外部调用者直接拼装出半只或身份不一致的 Elfie。

Facade 不调度 Activity，不组织记忆，不决定回复内容，也不实现身体切换状态机。

### 5.3 Bootstrap / App Orchestration

Bootstrap 负责依赖注入和进程启动；应用编排负责把 Elfie、Nest、Godot/设备、AI Runtime、通信接口
和持久化设施组合为产品运行态。它们位于 Elfie 之外，不能成为 Elfie 的人格或身体权威。

## 6. 不再作为顶级模块的概念

| 概念 | 目标归属 |
| --- | --- |
| Entity Identity | Profile / Identity |
| Virtual Appearance | Profile / VirtualAppearance |
| Personality、Self、Memory、Emotion、Energy | Brain |
| Skills、Planner、Tool Loop、Worker | Brain / Cortex；执行设施由 AI Runtime 注入 |
| Activity、内部触发和 Night Work | Brain |
| Embodiment Authority | Body |
| Lifecycle System | 不创建；保留薄 Elfie Facade |
| Profile Page | 产品层聚合视图，不是新的数据所有者 |
| Godot World、Nest、AI Runtime、Persistence | Elfie 外部边界 |

## 7. 当前阶段明确不做的事情

1. 不迁移现有源码目录；
2. 不移动 `skills/`、`initialization.py`、`cognitive_runtime.py` 等当前实现；
3. 不修改 Profile Schema 或持久化数据；
4. 不定义模块通信 Payload、事件类型或协议版本；
5. 不为了临时适配新增兼容层；
6. 不修改公开 Developer 文档，把目标设计冒充为已实现架构；
7. 不启动测试、构建或 Runtime 验证。

## 8. 后续迁移门槛

只有在相关通信设计提交并合并后，才进入下一阶段：

1. 同步合并后的当前代码事实；
2. 联合本文所有权边界，定稿模块通信与交互规约；
3. 对照目标目录审计现有调用方、数据所有者和持久化入口；
4. 形成分阶段迁移方案，分别处理目录、调用方和数据重建；
5. 明确每一阶段的验收条件后再开始代码迁移。

通信规约可以补充接口，但不得反向推翻本文的一级所有权；若确有冲突，必须先显式修订本规约，
不能通过实现细节悄悄改变模块职责。

## 9. 固定结论

1. Elfie 运行期一级模块固定为 Profile、Brain、Nervous System、Body、Communication；
2. Profile 只保存不可变外部身份/年龄/出身锚点、最终虚拟外貌和技术 Schema revision；
3. Brain 保存会成长的心理、自我、人格、记忆、关系和认知系统；
4. Body 内部拥有虚实二选一的 Embodiment Authority；
5. Genesis 是一次性跨模块创建流程，不是长期生命器官；已提交 Elfie 不依赖资料包、问卷或 Plan；
6. Factory 是装配器，Elfie Facade 是薄外部边界，二者都不调度领域行为；
7. Skills、Activity、Night Work 和自治治理归入 Brain；
8. 当前先固化目录与所有权，不提前固化通信协议，也不开始源码迁移。
