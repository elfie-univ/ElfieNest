# Elfie Godot 虚拟身体端到端执行计划

> 状态：基于具身控制链路冻结版 v1 的执行计划
> 范围：一只 Elfie、一只 Godot Runtime、一具虚拟身体；不包含物理设备。

> 设计关系：**所属模块：**Elfie / Embodiment；**上级设计：**[具身控制链路设计](./elfie-embodied-control-chain.md)；
> **下级设计：**无；**规范性契约：**[系统架构契约](../../../contracts/system.md)、[Elfie 契约](../../../contracts/elfie.md)、
> [Nest–Godot 语义世界契约](../../../contracts/nest-godot-semantic-world.md)、[Brain 契约](../../../contracts/brain.md)；
> **当前架构：**[模块边界](../../../architecture/module-boundaries.md)；**一致性：**无；**领域资料源：**Elfaria 与产品资料的稳定标识。

## 1. 第一版验收目标

第一版不是只验证 Godot 能动，而是验证一条完整闭环：

```text
Brain ControlCall
  → 能力目录分发
  → NervousSystem → Body / BodyPort
  → Godot Body Adapter → Transport / Gateway
  → Actor 执行与动画
  → 外部具身终态 + 语义视觉/听觉/触觉/本体感觉
  → Body → NervousSystem → EventWorkspace
  → 下一轮 Brain
```

Runtime 可以产生 `accepted`、`started` 和终态回执，但它们属于一个动作生命周期，不是三次 Brain Turn。
完整生命周期保存在动作状态表中；Brain 每个命令只接收一个外部 `Embodied` 终态结果。EventWorkspace
将它和同一因果窗口内的身体事实合并，最多形成一次后续 Brain Turn。`Activity` 只用于 Brain 的额外活动，
不表示动作回执。

必须能证明：

1. Brain 通过结构化输出发出一个或多个精确能力调用，不能用自由文本控制身体。
2. 一个已注册的移动能力能让虚拟 Actor 经过 Godot 路径规划实际移动，并返回
   `accepted → started → 一个终态`。
3. 一只 Elfie 说话后，Godot 根据空间、距离和遮挡计算听众；Nest 将语音事件经每个目标
   Elfie 的 Body 输入边界投递给命中的 Elfie，而不是广播原始 Runtime 帧。
4. Elfie 请求观察时，Godot 只返回可见语义 ID；Nest 将 ID 解析成结构化场景，再经观察者
   Elfie 的 Body 输入边界投递，Brain 得到“周围有什么”，不接收 Godot 图像帧。
5. Actor 碰撞/触摸、动作终态和当前身体状态能进入 Brain 的下一轮感知。
6. Brain 控制 Turn 在产出结构化调用后结束。第一版允许独立输出 Worker 等待终态，但不能阻塞 Transport
   或传感器接收；后续终态和感知事实合并为一次 Embodied Turn，Activity 保持独立。

第一版感知范围是：语义听觉、语义视觉、触觉/碰撞、动作回执、区域/姿态等本体状态。
原始麦克风音频、原始摄像头图像、完整环境声识别和自由导航问答不属于本切片。

## 2. 当前链路与必须保留的资产

| 责任 | 当前所有者 | 保留内容 |
| --- | --- | --- |
| Brain 决策 | `elfie/brain/reasoning/` | `DecisionPlan`、Turn、EventWorkspace、现有聊天链路 |
| 身体绑定 | `elfie/body/` + `app/orchestration/embodiment/` | `BodyPort`、`BodyBinding`、generation、旧身体失效规则 |
| 身体安全与归一化 | `elfie/nervous_system/` | 物理限制、反射、BodySensorEvent 归一化、感知投递 |
| Godot 宿主 | `infrastructure/godot/` | Gateway、Session、`GodotTransport`、`NativeBody`、传感器映射 |
| 世界语义 | `nest/` + `app/orchestration/nest_session/` | Home/anchor 解析、听觉可达、语义视觉、环境和事件路由 |
| Godot 权威 | `godot_project/runtime/` | Actor、NavigationAgent、路径规划、碰撞、动画、场景语义查询 |

不能保留第二套 Brain→Godot 调用链，也不能把几何、路径、碰撞或渲染复制到 Python。

## 3. 目标到现有代码的缺口

| 目标责任 | 当前路径 | 最小原地改动 | 验收证据 |
| --- | --- | --- | --- |
| 结构化控制调用 | `EffectiveCapabilityProjection`、`DecisionPlan`、`NervousSystemIntentExecutor` | 使用通用 category 加动态注册的 `capability_id + typed args`；由下层分发 | 无法用自然语言或未注册能力形成 BodyCommand |
| Direct Body / World 分路 | `BodyPort`、`NestSession`、Godot v3 lane | Body 注册直接能力，World owner 注册语义能力；组合根只汇总发现；最终身体指令仍回到 NervousSystem → Body | `move/turn` 和语义目标调用命中正确 owner，且不绕过 Body |
| 虚拟身体就绪 | `build_nest_session_services()`、`restore_registered_elfies()`、`BodyBinding` | 明确注册并绑定 `NativeBody`，同步 Actor 后才开放能力目录 | Runtime ready、Actor 已绑定、generation 一致 |
| 虚拟移动 | `NativeBody` → `GodotTransport` → `actor_controller.gd` → `elfie_actor.gd` | 保留 Godot 路径规划；把动态移动能力、Body 执行和终态结果连成一条路径 | Actor 真移动、播放 walking/idle、碰撞或不可达有失败原因 |
| 外部具身终态 | 当前 `GodotTransport.execute_intent()` 会等待终态 | 第一版保留独立输出 Worker 内的等待；终态经 Body/NervousSystem 归一化，完整生命周期进动作状态表，每个命令只向 EventWorkspace 发布一个合并后的 Embodied 终态；非阻塞提交放到第二版 | Transport 和传感器接收保持可用；Brain 只看到终态，不把 accepted/started 当独立 Turn |
| 说话与听见 | `prepare_speech()`、`request_speech_reach()`、`NestEventBus` | 保留“内容在 Nest、空间可达在 Godot、听见事件回 Nest”的链路，补齐目标 Elfie 下一轮输入 | 只有空间命中的 Elfie 收到 `HeardUtterance` |
| 语义视觉 | `request_visual_observation()`、`resolve_visual_observation()`、`SemanticVisualScene` | 保留“Godot 可见 ID → Nest 语义解析”；接通请求方 Brain 的后续感知 | Brain 收到带 label/kind/zone 的结构化场景 |
| 触觉与本体状态 | `NativeSensors` 当前只映射 tactile；Runtime snapshot 主要更新 Nest mirror | 通过 Body → NervousSystem 补齐触觉、姿态、区域、位置和到达状态；World-only 事实仍留在 Nest | 触碰和身体状态变化能触发后续感知；不伪造原始坐标 |
| 单一生产闭环 | `NestSession` tick、`pump_body_events()`、`NestRuntimeEventRouter` | 统一 drain、身份/代次校验、投递 EventWorkspace、通知下一轮 Brain | 一个命令只产生一条可追踪因果链，无重复或旧代次回执 |

## 4. 顺序执行切片

### P0-A：冻结控制与反馈模型

- 保持聊天输出和具身控制输出为两个互斥变体。
- 让每个控制调用使用通用 category 加动态注册的 `capability_id + typed args`，但不把底层 owner/route 交给 Brain。
- 把本地提交确认与 Runtime 权威的 `accepted` 回执分开；二者都不是动作成功。定义回执去重、旧 generation
  丢弃和失败原因。

验收：每个结构化控制调用都可被目录校验，未注册能力和自由文本均不能进入 `BodyPort`。

### P0-B：打通虚拟身体装配

- 在现有 Bootstrap 中创建 `NativeBody`，注册到 `BodyRegistry`，通过 `BodyBinding` 绑定。
- 让能力目录只在 Godot Runtime ready、世界 revision 匹配、Actor 同步完成后对 Brain 可用。
- 保持一个 Elfie 只有一个当前身体 authority。

验收：能观察到 `runtime_id/generation/world_revision/body_generation` 一致的 ready 状态。

### P0-C：打通移动和终态动作结果

- 第一条移动验收使用能力目录中的移动能力：World 语义目标由 Nest 解析，Godot 负责路径、碰撞、步进和动画。
- World 解析不是第二条身体链路：生成的移动指令必须经 NervousSystem 校验并通过 Body / BodyPort，之后才能到达 Godot。
- 直接 `body.move_forward/turn` 的能力目录和转换随后接入同一 BodyPort，不另建运动链。
- 第一版保留当前 GodotTransport 在独立输出 Worker 内的终态等待；`intent_accepted`、`intent_started`、
  `intent_terminal` 都保留原始因果 ID，经 Body 回执归一化。完整生命周期进入动作状态表，但每个命令只向
  EventWorkspace 送一个合并后的 Embodied 终态结果，不增加动作专属 Brain 触发器。第二版再改成本地提交
  加完整异步回执流。
- `emergency_stop` 走确定性安全路径，可中断活动动作。

验收：Brain 发出一次控制决策，Actor 真实移动；Brain 控制链和传感器接收在独立 Worker 等待期间保持可用，
Brain 后续收到一个结构化终态动作结果；阻挡、超时、中断和旧代次均有可判断结果。

### P0-D：打通说话—听见闭环

- Brain 发 `speak(text)`，当前 Body 产生说话动作和提交/终态回执。
- Nest 保存语音内容，Godot 只计算空间上的听达范围、同区域和视线/遮挡条件。
- Godot 返回 `speech_reach` 后，Nest 生成定向 `HeardUtterance`，经目标 Elfie 的 Body 输入边界，
  只投递给命中的 Elfie。

验收：说话者知道动作结果；听众在下一轮 Brain 中得到结构化听觉事实；无听众时不产生
虚假的听见事件。

### P0-E：打通语义视觉闭环

- Brain 发起观察请求，不接收图片。
- Nest/Godot World 根据 Actor 位置、视锥和遮挡返回语义 ID。
- Nest 校验 ID、区域和当前世界 revision，解析为 `SemanticVisualScene`，经观察者 Elfie 的 Body 输入边界，
  再送入 Brain。

验收：Brain 能区分当前可见的 Actor、anchor、facility 及其 label/capabilities；不可见或
旧 revision 的对象不会进入感知。

### P0-F：打通身体反馈和下一轮 Turn

- Godot 碰撞触发 `tactile_contact`，映射为 `TactileImpact`，经过 NervousSystem 的反射/过滤。
- 将动作结果、区域/姿态等本体状态映射到正确语义流；世界区域和环境事实仍走 Nest。
- `pump_body_events()`、Nest 事件 outbox 和 Brain `EventWorkspace` 统一做 identity、generation、
  去重、生命周期合并和 backpressure 处理。动作结果与其他具身事实使用同一套 Workspace 触发策略；安全
  关键失败沿用已有的通用 critical 路径。

验收：移动、碰撞、听见、看见以及每个命令一个合并后的动作结果都能形成后续 Brain 输入；所有身体输入/输出
都经过 Body 和 NervousSystem，定向 World 结果先回到 Elfie 的 Body 输入边界，且一个动作生命周期不会制造
多个回执驱动的 Turn。

## 5. 第一版能力目录

以下是第一版的能力目录条目示例，不是写死的 `DecisionIntent` 联合类型。Brain 只能调用当前身体或
World owner 实际注册的能力。

| 能力 | 归属 | 第一版用途 |
| --- | --- | --- |
| `world.go_to(anchor_id)` | Nest World | 去床、椅子、活动点等语义目标；Godot 做路径规划 |
| `body.emergency_stop(reason)` | Direct Body | 立即停止当前动作 |
| `body.speak(text)` | Direct Body + Nest interaction | 播放说话动作并计算谁听见 |
| `body.expression(kind)` | Direct Body | 播放已注册表情/动作并返回终态 |
| `world.observe()` | Nest World | 获取当前视野内的语义对象列表 |
| Body tactile/proprioception | Direct Body | 碰撞、触摸、姿态和动作状态反馈 |

`move_forward(distance)`、`turn(angle)` 是冻结架构中的 Direct Body 能力；若当前 Godot
切片先用 `go_to` 证明路径移动，它们仍复用同一目录、BodyPort、回执和 EventWorkspace，
不另起实现路径。

## 6. 明确暂缓

- 物理设备、配对、Wi-Fi/MQTT/WebSocket 设备 Agent。
- 原始图像、原始音频和多模态媒体上传。
- 物理身体无导航能力时的通用外部规划器。
- Brain 多步自主导航 Activity；第一版由一次调用和后续回执驱动下一轮。
- 完整非阻塞 BodyPort 提交和异步回执流；放到第二版。
- 把所有 Godot Runtime 帧广播给所有 Elfie。

## 7. 完成判定

只有以下条件同时满足，才称为“Godot 虚拟身体链路打通”：

- 一个真实 Brain Control Turn 能发出一个或多个已注册的结构化能力调用；
- 虚拟 Actor 能移动、播放动作并返回真实具身终态结果；
- 说话、听见、语义视觉、触觉/本体状态均能按权威进入下一轮 Brain；
- 当前 Body、Runtime generation、world revision 和 command identity 全程一致；
- Godot headless 场景测试、Python 边界测试和至少一条宿主到 Runtime 的可重放集成场景通过；
- 没有第二套控制链、身体输入/输出绕过 Body 或 NervousSystem、原始媒体绕过 Nest，或把 Runtime 事实误写成 Nest 持久事实。
