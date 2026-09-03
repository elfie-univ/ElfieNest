# Elfie 具身控制链路设计

> 状态：冻结版 v1（总体职责骨架）
> 范围：从 Brain 到 Godot 虚拟身体或外部物理身体的完整链路，以及回程的回执和感知。
> 本文冻结职责骨架，不表示未来所有物理设备协议已经实现。

> 设计关系：**所属模块：**Elfie / Embodiment；**上级设计：**[Elfie 顶级模块设计](../elfie-top-level-module-design.md)；
> **下级设计：**[Godot 虚拟身体端到端执行计划](./elfie-godot-vertical-slice-plan.md)；**规范性契约：**[系统架构契约](../../../contracts/system.md)、
> [Elfie 契约](../../../contracts/elfie.md)、[Nest–Godot 语义世界契约](../../../contracts/nest-godot-semantic-world.md)、[Brain 契约](../../../contracts/brain.md)；
> **当前架构：**[模块边界](../../../architecture/module-boundaries.md)；**一致性：**无；**领域资料源：**Elfaria 与产品资料的稳定标识。

全局所有权规则仍以[系统架构契约](../../../contracts/system)、[Elfie 契约](../../../contracts/elfie)、
[Nest–Godot 语义世界契约](../../../contracts/nest-godot-semantic-world)和
[Brain 契约](../../../contracts/brain)为准。本文只围绕一个问题组织已有边界：同一份身体能力调用，
如何在不让 Brain 或 Body 依赖目标平台的情况下，落到两个不同的执行端——Godot 虚拟身体和物理设备？

## 1. 设计目标

本设计必须提供：

- 两条明确的 Brain 输出电路：聊天电路经 Communication 返回自然语言；具身控制电路产出有限的、精确的
  MCP 式能力调用（`capability_name(typed_params)`），不能返回自由文本，也永远不是原始电机数值；
- 一份 Body 语义契约和一个当前身体执行权威；
- 两条可替换执行路径：Godot 虚拟身体、外部物理身体；
- 每具身体/设备一份**可枚举的能力目录**，让系统和 Brain 都知道当前身体"能做什么、不能做什么"；
- 类型化的指令、能力注册、回执和感知反馈；
- 原始协议帧、电机数值和引擎细节不能进入 Brain；
- 不让模型参与逐帧控制；执行由目标权威完成，后续事实再触发后续 Turn。

本文暂不冻结完整线协议、某个硬件厂商协议或未来全部运动能力。配对只为物理设备定义；
虚拟身体完全没有配对流程。

### Brain 输入域与 `TurnFrame`

`EventWorkspace` 是 Brain 输入唯一的累积、去重、合并和封帧位置。它只有三个输入域：

| 输入域 | 含义 |
| --- | --- |
| `Communication` | 用户/设备对话内容和通信投递事实 |
| `Embodied` | 身体动作的外部终态回执，以及身体/世界感知 |
| `Activity` | Brain 跨 Turn 的额外活动及其状态变化 |

`TurnFrame` 是 EventWorkspace 封存后交给 Brain 的不可变输入帧，不是第四种输入，也不是模型自己创建的。
`accepted`、`started` 只留在动作状态表；最终动作结果是外部的 `Embodied` 事实。同一因果窗口内的最终
动作结果和位置、姿态、触觉等身体事实，由 EventWorkspace 合并成一个 Embodied frame。Activity 状态
不是身体回执，也不进入 Body 路径。

Godot 和物理设备可以在本地保留精确坐标，但 Body 只向 Brain 暴露必要的归一本体感知：身体身份和代次、
语义区域/anchor、姿态、必要时的朝向、活动命令和到达状态。它沿 `Body → NervousSystem → EventWorkspace`
上传，由 Brain 的 Orientation 拥有当前自我位置投影。设备连接上可以连续上传位置变化，但 EventWorkspace
会合并状态，不按每个物理帧创建模型 Turn。

## 2. 双 authority 与两条语义通道

### 双 authority

虚拟侧存在两个不同的权威：

| 权威 | 拥有 |
| --- | --- |
| **Godot Runtime** | 虚拟世界的物理事实：场景、位置、物理身体、导航、碰撞、可见、可听、渲染和实际执行；虚拟世界路径规划永远归 Godot |
| **Nest** | 可解释语义：家庭语义、规则、时间/环境意图、语义交互，以及结构化视觉/虚拟听觉/语义动作的关联 |

"是否需要路径规划"不决定语义归属。Nest 解析世界目标、含义和权限；只有在虚拟世界中，Godot
才负责路径规划和实际移动。物理设备由自己的 Device Agent/控制器执行；如以后需要通用规划器，
必须明确放在外部执行侧，不能默认归 Godot。

**环境对象（灯、门、设施）是 Nest 拥有的世界意图，不是精灵身体意图。** 时间与家庭规则自动命令
它们（门走近自动开、灯晚上自动亮）。精灵不通过身体控制环境对象；它的身体链路里没有这种指令。

### 身体路径与 World authority

所有身体指令和身体自身感知只有一条不可绕过的 Body 路径。**World authority** 是独立的语义权威，
不是这条路径上的额外一跳。Nest 可以解析语义目标或筛选世界事件，但不传输、不执行 Body 指令。

```text
Brain 控制调用
  → NervousSystem（Elfie 唯一的具身控制闸门）
  → Body / BodyPort
  → NativeBody 或 ExternalBody
  → Transport → Gateway
  → Godot Actor 或远程 Device Agent / 固件

Godot Actor 或远程设备
  → Gateway → Transport → Body Adapter
  → Body → NervousSystem
  → EventWorkspace → TurnFrame → Brain

World 语义侧：
Godot World 或设备世界适配器 ↔ Nest
  → 定向给某个 Elfie 的语义结果
  → 该 Elfie 的 Body 输入边界
  → NervousSystem → EventWorkspace → Brain
```

Direct Body 的回程是：

```text
Godot Actor 或物理设备
  → Gateway → Transport → Body Adapter → Body
  → NervousSystem → Brain EventWorkspace
```

World authority 不能绕过 Body 和 NervousSystem。它的语义结果先回到目标 Elfie 的 Body 输入边界：

```text
Godot World authority
  → World Gateway → Nest semantic owner
  → 定向结果 → Elfie Body input
  → NervousSystem → Brain EventWorkspace
```

`BodyPort` 是 actor-body 的稳定语义边界，不是额外的运行时层。`NativeBody` 和
`ExternalBody` 是 Infrastructure 中对 `BodyPort` 的具体实现。只有当前 `BodyBinding`
及其当前代次可以执行 Direct Body 指令或更新 Direct Body 的权威感知。

"左转""向前走"这类直接动作走 Body 路径；"听到了什么""看到了什么""回家"这类需要
家庭/世界语义解析的行为咨询 World authority。如果 World 决策最终产生身体移动，生成的 Body
指令仍必须回到 `NervousSystem → Body` 后才能执行；Nest 不能变成 `BodyPort` 实现。

几个关键调用的权威分配是：

| 调用 | 通道 | 语义权威 | 物理执行者 |
| --- | --- | --- | --- |
| `move_forward(distance)`、`turn(angle)` | Direct Body | 当前身体能力 | Godot Actor 或 Device Agent |
| `move_to(anchor_id)`、`go_home` | World | Nest 解析目标、含义和权限 | 虚拟世界由 Godot 路径规划；物理世界由设备控制器/外部规划器执行 |
| `open_door`、`turn_on_light` | World | Nest 拥有的环境意图 | Godot World 或对应环境控制器 |

### 外部身体是远程运行时

`infrastructure/devices/` 中的代码运行在 ElfieNest 宿主机上，不会安装到物理玩具里。物理
玩具运行另一套固件或 Device Agent，负责本地传感器、执行器、安全策略和网络客户端。

```text
ElfieNest 宿主机                                      外部物理设备

BodyPort                                               Device Agent / 固件
  → ExternalBody 或设备专用 BodyPort Driver             ├ 摄像头/麦克风/触摸/
  → ExternalTransport → DeviceGateway                  │ 碰撞/IMU/电量采集器
                            ▲                            │
                            │                            └ 电机/舵机/扬声器/
              Body WebSocket 端点                           屏幕等执行器
                            ⇄ 认证的 Wi-Fi/LAN 会话
                            ⇄
                    Device Agent / 固件
```

下行是 `BodyCommand → ExternalTransport → DeviceGateway → Body WebSocket 端点 → 网络身体消息 →
设备分发器 → 本地执行器 Driver`。上行是 `传感器/执行器状态 → 设备事件消息 → Body WebSocket
端点 → DeviceGateway → ExternalTransport → Body → BodyPort → NervousSystem`。所以外部身体天然是双向的：既有指令输出，也有摄像头、麦克风、碰撞/触摸、
本体感知、电量和健康状态输入。

Wi-Fi/LAN 是连接媒介，不是 Body 契约。第一版外部设备应采用"配对后建立认证的双向 IP 会话"。
Bluetooth 以后可以用于配对或某类设备专用连接，但不能泄漏到 Brain 或 `BodyPort`。

当前 `ExternalBody` 和 `DeviceGateway` 只是宿主侧构件。仓库已经有认证的、版本化的外部身体
WebSocket 端点，以及转发 heartbeat、传感器、终态回执和 command-poll 帧的 `BodyDeviceChannel`。
但 `DeviceGateway` 本身仍是进程内注册表和队列；Device Agent/固件及物理传感器闭环在仓库之外。
另外，当前生产 Bootstrap 还没有把 `ExternalBody` 装配到某个 Elfie 的活动 `BodyBinding`，所以
完整的 BodyPort 到网络运行链路仍是实现缺口。尤其是当前 `ExternalTransport` 连接只承载传感器
回调，终态回执还没有接回 `ExternalBody`；命令现在最多能证明"已入队"，不能证明物理设备已经完成。

WebSocket 端点和 `DeviceGateway` 是同一个外部设备 Gateway 子系统的两个代码部件，不是两个新的
领域层：端点负责网络帧边界，`BodyDeviceChannel` 负责宿主侧身份校验，`DeviceGateway` 负责宿主侧
Session/队列路由。

## 3. Brain 输出电路与能力调用

Brain 有两条不同的输出电路：

| 电路 | Turn/输出范围 | 输出 | 执行规则 |
| --- | --- | --- | --- |
| 聊天 | Communication | 经 `Communication` 返回自然语言 | 自由文本永远不能被解析成身体指令 |
| 具身控制 | Embodied | 经 `NervousSystem` 返回精确能力调用 | 只有类型化、经过能力目录校验的调用才能到 `BodyPort` |

同一个 Turn 不混合这两个外部领域。控制结果不能带一段让运行时猜测执行方式的自由文本，聊天结果
也不能暗中控制身体；如果一次请求同时需要两者，就拆成有明确范围的 Turn，不能把同一段输出解析两次。

### 能力调用形态：MCP 式精确方法调用

具身控制电路对身体的输出是精确的方法调用，不是语义描述：

- 每具身体/设备暴露一份**能力目录**。每个条目是 `name + 类型化参数 schema + 返回类型`，
  形态与 MCP tool 定义一致。系统和 Brain 都可以**枚举**目录（"拉取全部能力"），从而知道
  当前身体"能做什么、不能做什么"。
- 能力目录条目声明的是宽泛的 `category`（`body`、`world`、`communication` 或 `activity`）和注册来源，
  不是固定的方法全集。`BodyPort` 注册当前身体能直接执行的能力；Nest 或其他权威注册需要世界语义的能力。
  组合根可以汇总成 Brain 可枚举的只读目录，但不能合并执行路径。
- Brain 通过模型的 **function-calling / 结构化输出** 产出有限个通用精确调用。每个调用包含
  `call_id + category + capability_id + typed arguments + subject=self`；同一个已结算的 `DecisionPlan`
  内，调用可以有序执行或并发执行。`DecisionIntent` 不枚举 `go_to`、`turn`、`speak` 等具体动词；
  它们都是随身体/设备变化的目录条目。Brain 不填写 Godot、设备、Transport 或具体 Body ID，下层按目录和
  当前 `BodyBinding` 选路由。
- 分路发生在**能力注册/分发层**，不在 `Body` 里面把身体劈成两半：身体能力走
  `NervousSystem → BodyPort → 当前 Body Adapter`；World 能力由对应世界权威解析；如果最终产生身体动作，
  生成的 Body 指令必须回到 `NervousSystem → BodyPort` 后才能执行。Brain 只决定调用哪个已注册能力。
- NervousSystem 校验身体调用（能力是否存在、参数是否正确、身体代次、物理极限和反射），再经过 `BodyPort`
  交给身体执行。World 调用不能伪装成身体动作，必须经过其语义和权限校验。身体返回类型化结果加生命周期
  回执；状态使用 `accepted`、`started`、`completed`、`rejected`、`failed`、`interrupted`、`timed_out`，
  “被阻挡”是类型化失败原因，不另造状态。

下面只是能力目录条目示例，不是 `DecisionIntent` 的固定联合类型：
`body.move_forward(distance)`、`body.turn(angle)`、`body.speak(text)`、
`body.expression(kind)`、`body.emergency_stop(reason)`、`world.go_to(anchor_id)`。

> 这种调用形态**不代表身体能力走 ToolPort**。`ToolPort` 是认知工具线路（web search、
> 有界工作区文件）；身体/设备能力是具身线路（神经系统/身体）。两者的**调用形态**一致——
> 精确、可枚举、带 schema——但**线路**不同。

### 回执与终态契约

第一版允许 `BodyPort.execute()` 在独立的输出 Worker 内等待目标执行结束，但不能阻塞 Transport 接收线程
或传感器输入链。Transport 层的 send 成功也只能表示本地已经安排发送，不能冒充远端 Runtime/设备已经
接受或完成。第二版再把 Worker 内等待改为本地提交加完整异步回执流；这是执行方式演进，不新增一套 Body
契约。

两版共用同一份类型化回执身份：`call_id/command_id、body_id、generation、capability_revision、status、
timestamp`，失败时带类型化 `error_code`。当前 Body 和 NervousSystem 负责把目标侧生命周期归一化成统一回执。

最小状态机：

```text
提交 ├→ rejected
     └→ accepted → started → completed
                            ├→ failed
                            ├→ interrupted
                            └→ timed_out
```

NervousSystem 校验回执身份、代次和能力版本。Body/输出状态表可以保留每一次生命周期变化用于审计和恢复，
但 `accepted` 和 `started` 永远不作为 Brain 的独立事件。Brain 每个命令只接收一个外部具身终态结果，并与
同一因果窗口内的身体感知合并，因此不增加动作专属 Brain Turn。安全关键失败沿用已有的通用 critical-event
路径。过期代次和重复回执必须幂等丢弃或记录，不能因为命令入队就伪造终态成功。

传感器事件遵循同一原则：Godot 或设备侧回调先由当前 Body 归一化，再交给 NervousSystem。事件先在
EventWorkspace 中累积、去重和合并；一次事件不等于一次 Brain Turn。身体输入永远走
`Body → NervousSystem → EventWorkspace`，Nest 不插入这条路径。后续动作结果或传感事实可以触发一次
后续 Turn 或 `Activity` 状态更新。

## 4. 两条执行路径

| 事项 | Godot 虚拟身体 | 外部物理身体 |
| --- | --- | --- |
| 身体实现 | `NativeBody` | 宿主侧 `ExternalBody` 代理或设备专用 `BodyPort` Driver |
| 宿主 Transport | `GodotTransport` | 连接宿主 Gateway 的 `ExternalTransport` / `DeviceGatewayTransport` |
| 网络协议端点 | `infrastructure/godot/gateway/` | `app/interfaces/api/v1/realtime/bodies/` |
| 宿主 Gateway 注册表 | Godot Gateway/Session 代码 | `infrastructure/devices/gateway.py` |
| 远程执行权威 | Godot Runtime | 独立 Device Agent/固件及本地执行器 Driver |
| 能力目录 | Godot 化身支持什么 | 设备在配对时注册的能力 |
| 导航 | Godot 负责路径、步进、碰撞和动画 | 只有设备/控制器声明并实现时才具备 |
| 指令规则 | 从已注册目录内调用能力 | 只调用物理身体实际注册的能力；Brain 永远不接触原始电机控制 |
| 回程事实 | Godot 返回生命周期回执和身体/世界感知；Brain 默认每个命令接收一个合并后的动作结果 | 设备路径返回生命周期回执，以及传感器/本体感知、电量和健康状态；Brain 默认每个命令接收一个合并后的动作结果 |

两条 Direct Body 路径共享 `BodyCommand`、`BodySensorEvent`、`CommandReceipt`、身体身份、
代次和能力版本。它们只在 `BodyPort` 之后产生差异。World authority 是独立的：它拥有世界语义
并做语义过滤，但定向给 Elfie 的结果仍必须进入该 Elfie 的 Body 输入边界，再经过 NervousSystem，
不能直接送 Brain，也不能强行伪装成 `BodyPort` 的执行。

对 Godot 和物理玩具，都应该按"事实的含义"而不是按"传感器类型"分类。本地麦克风/摄像头/
触摸/本体感知如果描述的是身体自身状态，可以沿 Body 路径进入；如果描述外部环境并需要"那里
还有另一个可听见的物体"这类语义，在 Godot 侧走虚拟 World lane。物理设备侧不强加第二个语义权威：
如果物理环境被纳入 Nest，就由外部 World Adapter 把观察送入 Nest 解析；若解析结果需要送给某个
Elfie，仍须回到它的 Body 输入边界 → NervousSystem → EventWorkspace；如果该范围尚未启用，事实
就停留在身体本地输入，不能直接当成 Nest 事实。

"回家"这类语义目标，可以在执行前使用 Nest/Godot 世界语义解析目标；这不意味着 Nest 成为
Body 执行器。解析后如果要移动身体，实际 Body 指令仍必须经过 NervousSystem → Body。
"向前走一步""左转"这类直接动作直接走 Body 路径，不经过 Nest。

## 5. 设备配对：仅物理设备

**虚拟身体不需要物理配对。** 它是精灵自己的身体：经 Godot Runtime authority（Gateway handshake
加 generation）连接。但它仍要经过运行时装配、注册、显式 `BodyBinding` 和 generation 校验；“无配对”
只表示没有用户/设备之间的信任交换，不表示无需绑定。

物理设备在被进驻前，走一段明确的配对流程：

```text
发现 → 配对 → 认证 → 会话 → 注册能力 → ready
```

1. **发现** —— 设备上电，向服务器发起连接（或局域网发现）。
2. **配对** —— 设备与服务器交换配对凭据/配对码，把设备身份绑定到用户/巢。
3. **认证** —— 设备获得独立最小权限身份（device principal），不复用管理员或 Observer 凭据。
4. **会话** —— 建立认证的双向网络通道（服务器下发命令，设备回传事件、回执和感知）。
5. **注册能力** —— 设备上报能力目录（传感器 + 动作，MCP 式）；服务器登记，系统从此知道
   该设备"能做什么、不能做什么"。
6. **ready** —— 设备健康、目录可查，成为可被进驻的身体。

虚拟身体跳过物理配对，但仍要经过运行时装配、注册、显式 `BodyBinding` 和 generation 校验。“无配对”
只表示没有用户/设备之间的信任交换，不表示无需绑定。

## 6. 外出与回巢：大脑决定 + ready 门

外出是一个大脑控制的开关加上一道外部 ready 门：

- 大脑决定"我想出去"并发起外出意图。
- 系统检查物理身体是否 **ready**（已配对、能力目录已注册、连接健康）。
- ready 才执行切换：虚拟身体睡眠，物理身体获得传感与动作 authority（HOSTED）。
- 大脑决定"我想回来"：物理身体释放 authority，虚拟身体醒来（回巢）。

不需要额外复制一份认知上下文，但身体切换本身必须是由 App Orchestration 拥有的显式
`BodyBinding` 事务：取得 ready 身体的 authority、推进 generation、释放旧身体，并支持回滚/恢复。
之后 Brain 的 Orientation 再从当前身体事实重建。

## 7. 模块职责

| 模块 | 负责 | 不负责 |
| --- | --- | --- |
| `elfie/brain/` | 自我、认知、推理、Skills，决定要做什么，产出精确能力调用 | Godot 帧、Socket、电机值、导航执行或设备协议 |
| `elfie/nervous_system/` | Direct Body 事件归一化、物理限制、确定性反射、指令前置检查和能力调用到 `BodyCommand` 的转换 | 开放式决策、Socket、协议 Session、几何、路径规划或 Nest 世界语义 |
| `elfie/body/` | 身体 ID、能力目录、指令、传感事件、回执、Registry、当前绑定和身体代次 | 具体 Godot/设备 Adapter、凭据、WebSocket/Bluetooth/LAN 和进程控制 |
| `BodyPort` | Body 领域对外的类型化接口：描述/连接、传感器、指令和快照 | 线协议编码或目标平台行为 |
| `nest/` | 家庭/世界语义、目标含义、视觉/听觉/动作关联和定向语义结果 | Elfie 的 Direct BodyPort、物理执行、设备传输或 Actor 所有权 |
| `infrastructure/godot/native_body.py` | 一具 Godot Actor 的 `BodyPort` 实现，把能力调用映射为 Godot Actor 语义 | Brain 决策、World 含义、Godot 场景权威或产品授权 |
| `infrastructure/devices/external_body.py` | 宿主侧远程身体代理，实现 `BodyPort`；共享能力校验、传感器缓冲和回执归一化 | 运行在玩具上、采集物理传感器、驱动电机，或必然承担所有厂商转换 |
| 外部设备 Driver（可选，位于 `infrastructure/devices/`） | 在通用设备消息与厂商协议之间按家族/型号翻译；设备能运行时优先放在远程 Device Agent/固件 | Brain 决策、家庭语义或向 Brain 暴露原始协议 |
| `infrastructure/*/body_transport.py` | 宿主侧 Adapter 到 Gateway 的投递、取消、待处理状态和投递失败 | 决定目标、定义 Body 语义或拥有物理事实 |
| `app/interfaces/api/v1/realtime/bodies/` | 面向网络的版本化 WebSocket 帧解析、鉴权，以及与远程 Device Agent 的进出站 | Brain 逻辑、Body 绑定、Nest 语义、导航或设备物理 |
| `app/orchestration/embodiment/BodyDeviceChannel` | 校验设备 Principal/Body 身份，转发已校验的 heartbeat、传感器、回执和 command-poll 操作 | 线帧编解码、电机 Driver、Brain 决策或普通移动 |
| `infrastructure/devices/gateway.py` | 宿主侧进程内设备注册表、命令队列、传感器/回执回调路由；外部 Gateway 的技术部分 | WebSocket 帧/鉴权、Brain 逻辑、Body 绑定、Nest 语义或设备物理 |
| Device Agent / 固件（独立设备代码，在本仓库之外） | 设备身份/配对客户端、传感器采集器、本地安全、执行器分发和网络会话 | Elfie 身份、Nest 家庭语义、Brain 推理或宿主侧 Body 绑定 |
| `godot_project/` / 物理设备执行器控制器 | 实际移动、导航、碰撞、动画和硬件行为；上报发生了什么 | Elfie 身份、记忆、家庭规则或第二个 Brain |
| `app/orchestration/nest_session/` | 组合真实 Elfie/Nest 实例并路由 Nest World Channel | 决定世界语义、拥有 Godot 物理或代理每条 Direct Body 指令 |
| `app/orchestration/embodiment/` | 注册、配对、关联、宿主、切换和跨权威恢复 | 普通移动指令和逐帧身体控制 |
| `app/orchestration/lifecycle/` | 启停和恢复 Core、Gateway 与选中的世界权威 | Brain 决策、Nest 规则或普通身体控制 |

这些 Infrastructure 概念的区别是：

```text
BodyPort       = 通用 Actor-Body 语义契约
Body Adapter   = 一个 BodyPort 实现加目标身体翻译
Transport      = Adapter 使用的宿主侧连接与消息投递
Gateway        = 宿主侧协议端点以及 Session/路由边界
Device Agent   = 负责采集传感器和驱动执行器的远程设备代码
```

Body Adapter 可以就是唯一的目标专用实现。`ExternalBody` 不自动构成第二层转换：只有在需要
共享宿主侧身体校验、传感器缓冲或回执归一化时才使用它。如果某个设备专用 Driver 可以直接实现
`BodyPort`，就直接实现；如果目标协议已经接受通用类型化指令，就不需要额外的宿主侧翻译器。

对于运行我们 Device Agent 的设备，必要的转换不是空转换：通用 `BodyCommand` 先变成设备无关的
网络消息，再由 Device Agent/固件映射到厂商电机、舵机、扬声器或屏幕 Driver。厂商映射不应在每个
宿主侧 `ExternalBody` 中重复。不能运行我们 Agent 的设备，才使用明确支持的宿主侧厂商 Driver。

Transport 不是新的顶层模块，而是位于目标 Infrastructure 包中、Adapter 旁边或内部的组件。
只有存在真实协议端点、Session 或路由器时才需要 Gateway。

## 8. 指令与反馈闭环

1. 当前身体通过 `BodyPort` 暴露类型化能力目录。
2. Brain 读取能力投影并**在已注册目录内产出精确能力调用**，不选择线协议帧或电机数值。
3. 如果是 Direct Body 调用，NervousSystem 检查范围、身体代次、能力版本、截止时间、物理限制
   和确定性反射规则；BodyPort/身体实现负责最终的能力和连接状态校验。
4. 如果需要家庭/世界语义，World owner 解析语义并与自己的 authority 关联；这不让 Nest 变成
   Body 执行器。如果结果需要身体移动，生成的 Body 指令必须重新进入 NervousSystem → Body 后才可执行。
5. Direct Body 路径由宿主侧身体实现/Driver 把类型化调用映射为目标语义 API；Transport 和
   Gateway 投递并按 command/intent/body/generation 身份关联响应。外部身体还要跨认证的
   Wi-Fi/LAN 会话到独立 Device Agent，由它分发给本地执行器。
6. 目标权威执行动作并上报实际事实：Godot 上报 Actor/World 事实，Device Agent 上报物理设备的
   传感器、执行器、电量和健康状态事实。
7. Direct Body 回执和身体传感沿 `Body Adapter → Body → NervousSystem → Brain` 返回。World
   语义结果定向给目标 Elfie，先进入其 Body 输入边界，再沿 `Body → NervousSystem → Brain` 返回。
   过期代次和版本一律拒绝。
8. Brain 在后续事件帧中消费结果，再决定下一步；不参与目标引擎的逐帧循环。

一个 Brain Turn 结算一个有界决策。当前 `DecisionPlan` 可以包含有限个有依赖关系或并发的调用，
但具身链路仍然是有限的、由回执驱动的；连续调整属于后续 Turn 或 Persistent Activity，不能藏在
Transport 或 Gateway 里变成模型循环。每个调用保留自己的动作账本和终态结果，产生的 Embodied
事件仍可以合并到一个后续 Frame。

## 9. 必须保持的边界

- Brain 产出精确能力调用；不能导入具体 Body Adapter、Transport 或 Gateway，也不能把语义文字
  当调用发出。
- NervousSystem 是确定性的具身处理层，也是 Elfie 身体输入/输出唯一的门；可以拒绝、过滤、限幅或急停，
  但不做路径规划、Nest 世界解析或网络 I/O。
- Body 拥有身体语义契约和唯一当前绑定，但不编码目标协议。
- `NativeBody` 和 `ExternalBody` 实现同一份 `BodyPort`，不能产生第二个身体权威。
- `infrastructure/devices/` 是宿主侧集成代码。物理设备固件/Device Agent 是独立运行时，不能
  像 `elfie/body` 一样被宿主代码直接导入。
- Transport 和 Gateway 只传递指令与事实，不决定精灵想做什么。
- 外部设备通信必须是双向的：同一个认证会话承载下行指令和上行回执/传感器事件。
- Godot Body 和 Godot World 是两条独立 authority 通道，即使共用一个 Gateway。定向给 Elfie 的 World
  结果必须先在该 Elfie 的 Body 输入边界归一化，再交给 NervousSystem；不能绕过 Body，也不能成为原始协议帧。
- Godot 和物理控制器拥有各自的真实物理事实；Python 只保存领域需要的类型化语义投影与回执。
- App Orchestration 管理生命周期和跨权威流程，但普通身体控制不绕道产品用例。

## 10. 延后决定的细节

以下内容可以后续设计，不改变本骨架：

- 外部设备线协议、配对/鉴权握手与重连策略；
- Device Agent/固件边界以及具体传感器/执行器消息结构；
- 物理设备是否自带导航，或是否需要一个独立的 Infrastructure 执行规划器；
- 各类设备的重试和队列策略；
- 未来设备的能力目录词汇如何增长。

能力调用的**形态**现在已定（精确、可枚举、类型化）；目录的**具体内容**随设备增长。如果以后
确实需要通用物理导航规划器，它必须作为明确的执行侧 Infrastructure 能力引入，不能悄悄塞进
NervousSystem、Gateway 或 Brain。终态回执语义和身份现在确定；完整的非阻塞异步执行留到第二版，
第一版允许独立 Worker 等待终态，但不能阻塞传感器接收或 Transport 接收线程。

## 11. 设计自审

### 目标架构

| 要求 | 结果 |
| --- | --- |
| 展示 Brain 到 Godot 和物理身体的完整链路 | 通过 |
| 区分 Body、BodyPort、Adapter、Transport、Gateway | 通过 |
| 两条路径共用一份语义契约 | 通过 |
| Direct Body 和 World 语义通道已分开 | 通过 |
| 聊天和具身控制两条 Brain 输出电路已分开 | 通过 |
| 能力调用是精确的 MCP 式方法调用 | 通过 |
| 每具身体/设备的能力目录可枚举 | 通过 |
| 物理配对与虚拟身体绑定已分开 | 通过 |
| `move_to`/`go_home` 的世界权威与身体相对运动已分开 | 通过 |
| 外出/回巢是大脑决定加外部 ready 门 | 通过 |
| 没有强加与 Nest 平行的真实世界语义权威 | 通过 |
| 精灵不控制环境对象 | 通过 |
| 定义外部具身终态、Activity 分离和单因果窗口 Turn | 通过 |
| 低级控制不进入 Brain | 通过 |
| 后续细节可在边界内演进 | 通过 |
| 已经冻结完整线协议和所有硬件能力 | 有意延后 |

### 当前实现就绪度

| 证据 | 结果 |
| --- | --- |
| 认证的外部身体 WebSocket 端点和帧类型 | 已有 |
| 宿主侧 `DeviceGateway` 队列/路由 | 已有，但仍是进程内 |
| `ExternalBody` 装配到 Elfie 活动 `BodyBinding` | 未完成 |
| 终态回执回到 `ExternalBody` | 未完成 |
| Device Agent/固件及物理传感器/执行器闭环 | 在本仓库之外 |
| Brain 到真实物理设备的端到端执行 | 未完成 |

结论：职责骨架已经清楚，可以作为终版设计候选；当前实现还不能宣称完成。第一版冻结
`Brain → NervousSystem → Body` 的唯一身体链路、外部具身终态回执、Activity 专属事件、动态能力注册
和单因果窗口触发；完整非阻塞异步执行推迟到第二版。改变所有权或 `BodyPort` 语义时，必须同步新增 ADR
并更新契约。
