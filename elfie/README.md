# Elfie 模块结构

`elfie/` 描述一只完整精灵自身的稳定内核。它负责个体档案、大脑、脑体连接、
可替换身体、通信、技能和运行状态；房间、床位、多精灵调度、用户归属和产品
界面属于 `elfienest/`，模型供应商与底层工具执行属于 `runtime/`。

## 精灵个体刻画框架

一只完整精灵的状态由三部分组成,合起来完整刻画了这个精灵：

### 1. Profile (稳定身份) - "我是谁"

**作用**：初始化配置 + 稳定身份描述  
**持久化**：`profile.yaml`  
**分类**：外在 + 内在

#### 外在部分
- **身份元数据**：ID、名字、物种、生命阶段、领养时间
- **外貌基因**：身材、比例、脸型、毛色、花纹
- **具身形态**：运动形态（biped/quadruped）、骨架配置、能力配置

#### 内在部分
- **性格人格**：Big Five、气质、核心动机、关系倾向
- **出身背景**：领养前环境、形成性经历
- **偏好习惯**：食物、活动、感官、社交偏好
- **能力倾向**：认知能力、领养前技能、初始知识
- **表达风格**：口癖、说话风格、肢体表达倾向
- **三观/世界观**：价值观、信念、安全感基线（待完善）

#### 特点
- 领养后基本冻结，少数字段可缓慢成长
- 是精灵的"出厂配置"和"身份锚点"

### 2. State (当前状态) - "现在怎么样"

**作用**：运行时瞬时状态  
**持久化**：`state.yaml`（可选轻量持久化）  
**内容**：
- 能量、疲劳、睡眠状态
- 当前情绪和表情
- 姿势、位置、当前动作
- 注意力焦点、当前目标
- 运行时长、当前身体绑定

#### 特点
- 每个 tick 都在变化
- 重启后可能重置或恢复到最近快照

### 3. Memory (认知沉淀) - "经历了什么、理解了什么"

**作用**：成长轨迹 + 世界认知  
**持久化**：`graph_memory.db`（SQLite 图数据库）  
**内容**：
- **情节记忆**：历史事件流水（与主人互动、重要经历）
- **语义知识**：概念、规律、常识（"甜莓果是甜的"、"主人通常早上喂我"）
- **关系网络**：人际、概念、空间关系（信任度、熟悉度、概念层级）
- **世界模型**：对世界的整体理解（已知地点、人物、概念）

#### 特点
- 随着互动不断积累
- 从中可以提取出知识、关系、规律
- 是精灵"智慧"和"个性"的成长源泉

### 三者关系

```
初始化精灵 ← Profile (定义"我是谁")
     ↓
运行精灵 ← State (记录"现在怎么样")
     ↓
成长精灵 ← Memory (沉淀"经历了什么、理解了什么")
```

- **Profile** 初始化精灵，定义稳定身份
- **State** 记录运行时瞬时状态
- **Memory** 沉淀成长轨迹和世界认知

三者合起来，完整刻画了一个精灵：它是谁、它现在怎么样、它经历了什么、理解了什么。

## 最终稳定目录

```text
elfie/
├── elfie.py                   # 完整精灵聚合对象
├── factory.py                 # 创建、恢复和依赖装配
├── profile/                   # 稳定个体档案、物种外貌和默认模板
├── brain/                     # 大脑，现有内部结构保持稳定
│   ├── brain_types.py         # BrainContext、BrainDecision
│   ├── context_builder.py     # 丘脑上下文组装
│   ├── cognition/             # 认知、注意力、预测和 LLM 决策
│   ├── emotion/               # 情绪检测、累积、衰减和表达
│   ├── energy/                # 能量、疲劳、睡眠和唤醒
│   └── memory/                # 编码、检索、图存储、遗忘和巩固
├── nervous_system/            # 大脑与身体之间的传感、执行、过滤、限位和反射
│   ├── nervous_system.py      # 神经系统统一入口
│   ├── sensors/               # 看、听、环境等具体传感器
│   ├── actuators/             # 说话、碎碎念和身体动作执行器
│   ├── reflex/                # 绕过复杂认知的快速身体反射
│   ├── signal_filter.py
│   └── physical_limits.py
├── body/                      # 可替换身体及身体绑定
│   ├── port.py                # SensorPort、ActuatorPort、BodyPort
│   ├── types.py               # 身体事件、命令、结果和状态
│   ├── capabilities.py        # 身体支持的传感器、动作和限制
│   ├── registry.py            # 可用身体 Provider 注册
│   ├── binding.py             # 当前身体和切换关系
│   ├── headless/              # 调试、测试和无渲染运行
│   ├── native/                # 精灵本体和 Godot 传输
│   │   ├── body.py
│   │   ├── anatomy/
│   │   ├── gait.py
│   │   ├── sensors.py
│   │   ├── actuators.py
│   │   └── godot_transport.py
│   └── external/              # 母星代理、毛绒玩具和机器人协议
├── communication/             # 精灵自带的双向消息通信
├── skills/                    # 搜索、浏览器等思考过程中使用的技能
└── state/                     # 可恢复动态状态和身体绑定状态
```

稳定的顶层架构目录是 `profile/`、`brain/`、`nervous_system/`、`body/`、
`communication/`、`skills/` 和 `state/`。旧 `interface/`、源码级 `config/`、
旧 Body 路径和 `elfie_individual.py` 已完成迁移并删除。

## 模块边界

- `profile` 回答“这只精灵是谁”，不保存当前情绪、当前位置或真实经历。
- `brain` 负责思考以及情绪、能量、睡眠和记忆，现有内部结构保持稳定。
- `nervous_system` 接收具体传感信号并传给大脑，将大脑动作交给当前身体。
- `body` 负责身体输入和动作执行；大脑不能直接调用 Godot 或机器人驱动。
- `communication` 负责一轮交互前后的消息收发，不经过身体动作链路。
- `skills` 负责一轮思考过程中调用搜索、浏览器等工具。
- 顶层精灵对象只负责编排，不重新实现各子系统内部算法。

身体层的三个配套对象职责固定：`BodyCapabilities` 声明一副身体实际支持的感觉、
动作和限制；`BodyRegistry` 保存这只精灵已经拥有或可以连接的身体；
`BodyBinding` 只管理当前使用哪副身体以及切换生命周期。身体注册时已经携带能力
声明，不再另建一套平行的“能力注册表”。

依赖方向必须保持为：

```text
Profile ───────┐
Brain ← NervousSystem → Body
Brain ← Skills
Brain ← Communication
        └──────────────→ Elfie 聚合对象统一编排
```

外部平台和身体可以实现稳定协议，但不得让 Godot、微信、Telegram 或机器人
协议进入 `brain/`。

## 结构稳定规则

本目录结构从当前阶段起视为稳定架构。后续开发优先在已有职责目录内增加或修改
代码，不得因单个功能方便而新增平行顶层模块、改变模块含义或跨层堆放逻辑。

未经明确架构评审和项目负责人确认，禁止：

1. 重命名、移动或删除上述七个稳定顶层架构目录。
2. 将大脑逻辑移入身体、通信或底层 Runtime。
3. 将具体 Godot、社交平台或机器人协议写入大脑。
4. 重新引入已删除的旧目录或平行兼容入口。
5. 同时进行目录迁移和业务算法重写。

确需调整整体结构时，必须同时满足：先说明现有结构无法承载的具体原因；更新
本文和架构设计文档；提供兼容迁移方案；运行对应单元测试与跨模块测试；经明确
确认后再实施。普通功能开发不得顺手修改整体目录。

## 当前完成状态

当前阶段已完成目录归位、旧导入路径迁移和兼容目录清理：

- 原 `interface` 正式归入 `nervous_system`。
- 原社交连接器正式归入 `communication/channels`。
- 原解剖和步态正式归入 `body/native`。
- 原身体反射正式归入 `nervous_system/reflex`。
- 旧公开导入路径已删除，调用方统一使用规范模块。
- `BodyPort` 已拆分为传感器输入、动作执行和身体生命周期协议。
- `HeadlessBody` 已接入单精灵调试平台，可注入原始刺激并记录动作结果。
- `NativeBody` 已通过薄适配层复用现有 Godot 事件，不替换引擎、步态和认知逻辑。
- Factory 在获得 Godot 网关时会装配并连接 `NativeBody`。
- 正式 Engine 已将房间感觉转换为 `BodyEvent`，并通过当前身体执行动作。
- `BodyRegistry` 和 `BodyBinding` 已支持登记多副身体、切换当前身体和失败回滚。
- `ExternalBody` 已定义外部插件的传感输入、动作输出、能力声明和状态快照协议。
- `Elfie` 已成为唯一规范聚合类型，完整保留原有算法。
- `ElfieFactory` 已负责 Profile 校验、创建恢复和身体装配。
- `CommunicationHub` 已提供独立于身体的通道、收件箱、发件箱、路由和策略。
- `SkillManager` 已将每只精灵的技能策略与 Runtime 现有工具执行链连接起来。
- `profile.yaml` 已收纳性格、能力和系统限制；旧三份 YAML 在迁移期继续双写。
- `profile.yaml` 已显式保存 `embodiment.primary_morphology`；旧 `anatomy_type`
  只作为老配置、老测试和数据库迁移兼容字段。
- `state.yaml` 已保存能量、疲劳、睡眠、情绪、运行时间和当前身体绑定。
- 正式 Engine 主循环优先使用 `BodyEvent -> NervousSystem -> Brain ->
  BodyCommand -> BodyPort` 的链路，旧 `perceive_and_respond(raw_sensor_data)`
  保留为内部兼容入口。

无 Godot 网关的独立运行不会隐式创建 `NativeBody`；调试平台显式使用
`HeadlessBody`，外部载体显式使用 `ExternalBody`。后续功能应直接在稳定目录中
扩展，不再恢复已经删除的兼容路径。

## 后续计划

以下事项属于 Godot 角色资产和物理表现层，当前阶段只保留接口和计划，不在本轮
重构中实现：

1. 外貌实装：把 `AppearanceResolver` 输出的 `bone_scales`、
   `blend_shapes` 和 `material_parameters` 完整接入 Godot 角色控制器，并要求
   狗、狐狸等物种资产提供同名骨骼缩放点、Shape Key 和材质参数。
2. 精细碰撞：在现有 `CharacterBody3D + CapsuleShape3D` 的基础上，设计随骨骼
   或关键部位变化的碰撞层，解决伸胳膊、腿部动作和体型变化后的穿墙问题。
3. 旧兼容清理：当所有正式入口都不再传 `anatomy_type` 后，再移除数据库和调试
   工具里的旧字段；不得在还有旧数据读取需求时提前删除。
