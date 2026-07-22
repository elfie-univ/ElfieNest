# Elfie 模块

`elfie/` 实现一只完整精灵，不包含账户、房间、Godot 场景、模型供应商或桌面
生命周期。

## 目录与职责

```text
elfie/
├── elfie.py             # 单精灵 facade 与生命周期
├── factory.py           # Profile、Body、Communication、Runtime 装配
├── cognitive_context.py # Brain owner 读取 Memory、历史与有效能力
├── cognitive_runtime.py # Coordinator、Router、worker 生命周期组合
├── message_types.py     # 跨模块 ID、Actor、时间和错误 primitive
├── profile/             # 唯一稳定档案 profile.yaml
├── brain/               # Workspace、上下文、情绪、能量、记忆与皮层决策
├── nervous_system/      # 身体感知规范化、过滤、反射与物理输出
├── body/                # Headless、Native、External 可替换身体
├── communication/       # 不经过 NervousSystem 的数字消息通道
└── skills/              # 允许传给 Runtime 的工具白名单
```

禁止恢复 `elfie/state/`、`brain/cognition/`、`brain/brain_types.py` 或新增
`brain/perception/`。`PerceptualWorkspace` 是 Brain 根层输入设施，不是第四脑层。

## 信息流

```text
Body -> NervousSystem ----\
                          -> PerceptualWorkspace -> BrainCoordinator
Communication ------------/                         -> BrainContext
                                                     -> DecisionPlan
                                                     -> OutputRouter
                                                       |-> NervousSystem -> Body
                                                       |-> Communication
                                                       \-> Internal
ExecutionReceipt ----------------------------------> PerceptualWorkspace
```

物理 tick、感知采集、模型推理和输出执行各自运行。Engine 只推进时钟并泵类型化
输入，不等待模型或执行器。每只 Elfie 最多一个 in-flight cortical turn；推理期间
的新事件进入下一 frame。

## 稳定契约

- Body：`BodySensorEvent`、`BodyCommand`、`CommandReceipt`、`BodySnapshot`。
- Communication：`CommunicationEnvelope`、`DeliveryReceipt`。
- Brain 输入：`PerceptionWrite`、`IngestReceipt`、`PerceptionFrame`。
- Brain 决策：`BrainContext`、`DecisionPlan`、`ExecutionReceipt`、`TurnOutcome`。

契约是 Pydantic v2 frozen model 或 discriminated union。第三方 wire 数据必须在
adapter 边缘立即解析，稳定模块间边界禁止使用裸字典。版本化 JSON Schema 位于
`docs/contracts/elfie/v1/`。

## Profile、运行值与 Memory

- `profile.yaml` 保存身份、外貌、人格、具身配置和稳定限制。
- 情绪、能量、`elapsed_time` 和当前身体绑定只由各自模块在内存维护，重启后使用
  默认值，不生成或恢复聚合 `state.yaml`。
- `graph_memory.db` 保存长期记忆。当前核心闭环只对 owner-origin 文本保留最小兼容
  写入；多角色来源记忆与关系建模属于后续 D1。

完整时序和模块所有权见
[`docs/design/Elfie感知认知决策信息流.md`](../docs/design/Elfie感知认知决策信息流.md)。
