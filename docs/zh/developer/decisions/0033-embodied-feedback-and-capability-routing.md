# ADR-0033：具身反馈与动态能力路由

**状态：** 已接受
**日期：** 2026-09-02
**范围：** Brain 事件域、具身行动/反馈以及 Body/World 路由

## 背景

旧契约把命令回执和 Activity 事件一起归入 `Internal` 来源域。这会遮蔽真实物理回传链路，
诱导系统为每条回执单独触发 Brain Turn，也让 Nest 看起来既像 Body 链的一环，又像绕过
Body 的捷径。审查还确认，固定 `DecisionIntent` 联合类型无法承载不同虚拟身体和物理身体
动态注册的能力。

## 决策

1. Brain 只接收 `Communication`、`Embodied`、`Activity` 三个来源域。Activity 只表示
   Brain 自己拥有的跨 Turn 工作，不能作为外部回执的收纳桶。
2. 身体动作结果是外部 `Embodied` 事实；消息投递结果是 `Communication` 事实；两者都不
   形成第四个来源域。
3. 身体流量双向都经过同一链路：
   `Brain -> NervousSystem -> Body/BodyPort -> Adapter -> Transport -> Gateway ->
   Runtime/设备`，回传反向经过 Body 和 NervousSystem。Nest 不在直接 Body Channel 中。
4. Nest 继续拥有家庭/世界语义。Nest 产生的定向语义结果必须进入目标 Elfie 的 Body
   输入边界，再进入 NervousSystem。世界解析若最终要求 Actor 移动，移动命令必须重新进入
   NervousSystem 和 Body 后才能执行。
5. `accepted`、`started` 只进入动作账本。Brain 只接收一个终态：`completed`、
   `rejected`、`failed`、`interrupted` 或 `timed_out`。取消统一表示为带原因的
   `interrupted`。超时会请求 stop/cancel；迟到终态按幂等规则对账，不能重开动作。
6. Event Workspace 封装不可变 `TurnFrame`。同一具身因果窗口内，动作终态可以和兼容的
   本体感知、触觉、姿态、位置或到达事实合并。回执没有独立 Brain 触发规则，收到一条事件
   不等于触发一次模型 Turn。
7. Brain 通过有限的通用类型化调用计划选择一个或多个已注册能力：大类、动态 `capability_id`、
   类型化参数、call/cause 身份、截止时间和当前主体。`move.to`、`move.turn`、`speak` 等具体动词属于能力目录，
   不能写死在 `DecisionIntent` 联合类型中；下层根据注册来源和当前 BodyBinding 选路，兼容动作可以有序执行或并发执行。
8. 第一版允许隔离执行 Worker 等待终态，但 Gateway 接收器与传感入口必须保持工作。完全
   非阻塞的 Body 提交和异步回执流延后到第二版。
9. Godot 拥有虚拟物理事实，包括坐标、导航、碰撞、可见性、可听性、动画和实际执行。
   Brain 通过 Orientation 接收归一化本体感知，不接收原始物理帧。物理设备通过单独部署的
   设备代码拥有对应的本地采集、安全和执行。

## 后果

- Brain、Elfie、System、Nest-Godot 四份契约必须同步修订。
- 聊天与具身控制继续分成两条电路：聊天输出自然语言，控制输出目录校验后的结构化调用。
- `BodyPort` 虽薄但必须保留，作为稳定身体语义边界。`NativeBody`、`ExternalBody` 是
  Infrastructure 实现；Transport 和 Gateway 也是目标专属的 Infrastructure 组件。
- 当前源码仍存在 `Internal` 来源命名、固定决定类型和同步执行细节；这些属于实现差距，
  本 ADR 不把它们声明为已经迁移。

## 被否决的方案

明确否决：把身体回执归为 Activity；每个生命周期状态触发一个 Brain Turn；直接 Body
流量经过 Nest；世界结果绕过 Body 或 NervousSystem；Brain 写死全部身体动词；把寻路放进
Brain 或 NervousSystem；以及要求首个 Godot 垂直切片先完成全异步执行器重构。
