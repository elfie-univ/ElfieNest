# Nest–Godot 语义世界迁移规约

**状态：** 生效中的临时一致性规约
**采纳日期：** 2026-08-13
**目标契约：** [Nest–Godot 语义世界契约](../contracts/nest-godot-semantic-world)
**缺口台账：** [Nest–Godot 语义世界一致性](./nest-godot-semantic-world)

本文是把当前 Nest 与 Godot 实现迁移到目标契约的已批准执行顺序。它在迁移期间具有
约束力，但不是永久文档：全部迁移卡和 `NGW-*` 缺口关闭后，最终治理收口会删除本文
及其英文镜像。

本文不声称目标能力已经实现，也不批准一次性大重写。每张卡都是一项可以独立审查、
独立验收的产品改动。

## 1. 不可违反的执行规则

1. **同一时间只做一张迁移卡。** 严格按下文顺序执行。不能因为后续卡碰巧要改同一
   文件，就把前一张卡尚未完成的内容带过去。
2. **每张卡必须形成完整纵向切片。** 同时迁移真实生产者、类型边界、消费者、
   Bootstrap 装配和聚焦测试。只增加类型或空 Package 不算进展。
3. **禁止兼容架构。** 不增加协议双解析、双投递、双读写、fallback、旧别名或第二份
   世界投影。每张卡同时更新受管调用方和协议两端，然后删除旧路径。
4. **一个事实、一个所有者、一条路径。** 同一次发生导致的不同事实使用不同类型和
   event ID，可以共享 `cause_id`；同一个事实不得同时通过 Body 和 Nest 到达 Elfie。
5. **每张卡完成后主分支可用。** 所选 Runtime generation 必须能启动，已迁移链路必须
   可工作；不能合并暂时破坏的中间架构。
6. **先有行为，再建结构。** 只有某张卡提供了真实状态或行为时，才创建对应 Nest 或
   Godot 目录；最后的机械移动不得夹带行为变化。
7. **验证语义边界，而不只是传输。** 每张卡都要证明正确路径、禁止的交叉路径、目标
   身份、适用时的过期 generation 处理，以及旧生产调用方已删除。
8. **只关闭已经证明的缺口。** `NGW-*` 的关闭门全部在当前代码成立后才能关闭；局部
   完成仍保持 open。
9. **发现目标变化立即停下。** 如果实现证明必须改变 authority、依赖方向、生命周期
   所有者或系统级 Port 语义，先暂停迁移卡，另行批准双语 ADR/契约治理变更。
10. **治理与产品迁移分开。** 产品卡可以更新聚焦测试和当前台账状态，但契约/ADR/
    Scanner 规则变化以及最终台账删除必须是独立治理改动。

## 2. 每张卡都必须保持的系统不变量

- 一个运行中的 ElfieNest 只有一个 Nest 和一个当前权威 Godot Runtime generation。
- Elfie 是其 Actor 身体意图的唯一发起者。Nest 可以在原 intent 内解析并转发目标，
  不能自行创建、定时、恢复或改写 Actor 行为。
- Nest 可以在执行家庭或时间/环境规则时独立命令环境对象。
- Godot 拥有物理 ID、场景几何、坐标、移动、寻路、碰撞、可见性、可听性和实际执行。
- Nest 拥有家庭含义，只保存居民 ID，不保存真实 Elfie；只有 App Orchestration 按 ID
  找到真实 Elfie。
- Python 命令和事件只暴露稳定语义 ID，不暴露 NodePath、坐标、碰撞形状或复制的导航
  状态。
- 一条认证 Gateway 连接可以实现多个消费方拥有的窄 Port，但共享连接不能合并语义线路。
- Runtime 生命周期事实只进入 App Lifecycle；直接身体事实只进入所属 Body；Nest
  语义事实只进入对应 Nest 所有者。
- 所有保留的物理投影都带来源 Runtime ID、generation 和 world revision；过期输入必须
  拒绝，不能静默换身份。
- 重试保留 request/event 身份；不能因为 Runtime 换代就重放已经过期的物理副作用。

## 3. 必须执行的事件分类

共享 Gateway 必须先验证并分类，再投递：

| 事实类别 | 唯一目的地 | 示例 | 禁止路径 |
| --- | --- | --- | --- |
| Runtime 生命周期 | App Lifecycle | connected、ready、health、generation、disconnected | Nest 事件或所有 Body |
| 直接 Body | 所属 Body transport/sensors | 命令回执、触觉、本体感知、移动输入 | Nest 广播或 App 遍历所有 Elfie |
| Nest 物理输入 | 一个类型化 Nest Port | manifest、`VisibleSet`、声音可达候选、环境事实/结果 | 原始投递给 Elfie |
| Nest 语义事件 | 经 App 按明确居民 ID 投递 | `HeardUtterance`、`SemanticVisualScene`、`SemanticActionResult` | 默认广播或再走 Body |
| Observer 投影 | 受授权的 App Observer 读模型 | 展示所需 Actor 姿态/区域 | 持久化为 Nest 居民状态 |

`world_ready` 不能继续同时表示进程就绪和语义世界配置完成。Runtime 就绪属于
Lifecycle；经过验证的场景 manifest 或世界配置结果属于 Nest/world session。

## 4. 目标责任结构

下面固定的是目标责任，不是预建空目录的授权。只有对应迁移卡提供真实行为时，路径才出现。

```text
nest/
  nest.py                     稳定聚合 Facade
  space/                      语义目录和设施投影
  rules/                      居民、Home、访问、共享和受众规则
  time_environment/           时钟、生活阶段和期望环境状态
  interaction/                说话、视觉和语义行动关联
  events.py                   公共类型化 Nest 事件信封/outbox 机制
```

各所有者需要的持久化与 Godot 能力 Port 由消费方所有。公共事件机制只是共享管道，不是
第五个业务模块。小而内聚的代码可以留在一个文件；上述名称不构成把每个 model 都拆成
service/repository Package 的理由。

Godot 源工程的最终结构为：

```text
godot_project/
  main.gd                         只负责装配
  characters/shared/elfie_actor.gd
  rooms/                          几何和场景资源
  runtime/
    endpoint/
      websocket_client.gd
      authority_endpoint.gd
      event_envelope.gd
    actor/
      actor_controller.gd
      actor_catalog.gd
      actor_path_planner.gd
      actor_animation_runtime.gd
      actor_appearance.gd
    world/
      world_controller.gd
      semantic_scene_index.gd
      spatial_queries.gd
      environment_controller.gd
      objects/                    只放真实有状态对象的脚本
    observer/
      observer_presentation.gd
      nest_camera_controller.gd
    lab/
      lab_runtime.gd
```

该结构按能力迁移逐步形成。`main.gd` 和房间脚本随对应行为抽取；禁止先一次性搬目录，
再把行为改变藏进“结构整理”。

## 5. 数据决策门

开始 `NG-M04` 前必须解决 `DATA-01`：

- **开发阶段默认方案：** 有需要先备份，然后按新 schema 重建开发 Nest 数据；
- **明确保留真实数据：** 另行获得用户批准，执行一次离线转换；必须有备份、精确的
  源/目标数量和回滚点。

两种方案都不允许运行期双读、双写、fallback Repository 或无限期兼容 `bed_number`。
没有明确批准，任何产品卡不得删除或改写真实 `${ELFIE_HOME:-~/.elfienest}` 数据。

## 6. 有序迁移卡

| 迁移卡 | 前置依赖 | 状态 | 主要缺口结果 |
| --- | --- | --- | --- |
| `NG-M01` | 治理基线 | open | 关闭 `NGW-002`、`NGW-003` |
| `NG-M02` | `NG-M01` | open | 建立空间与设施；部分解决 `NGW-001/008/009` |
| `NG-M03` | `NG-M02` | open | 建立巢内生活规则和 Home authority；部分解决 `NGW-001/008` |
| `NG-M04` | `NG-M03`、`DATA-01` | open | 切换 Nest 持久化；部分解决 `NGW-001/008` |
| `NG-M05` | `NG-M04` | open | 建立时间与环境；部分解决 `NGW-001/007` |
| `NG-M06` | `NG-M01` | open | 从 Nest 移除用户消息责任；部分解决 `NGW-001` |
| `NG-M07` | `NG-M02`、`NG-M03`、`NG-M06` | open | 关闭 `NGW-008`、`NGW-009` |
| `NG-M08` | `NG-M01`、`NG-M03`、`NG-M06`、`NG-M07` | open | 建立交互/事件并关闭 `NGW-004` |
| `NG-M09` | `NG-M08` | open | 关闭 `NGW-005` |
| `NG-M10` | `NG-M03`、`NG-M07`、`NG-M08` | open | 第一条语义行动；部分解决 `NGW-006` |
| `NG-M11` | `NG-M10` | open | 关闭 `NGW-006` |
| `NG-M12` | `NG-M05`、`NG-M07`、`NG-M08` | open | 关闭 `NGW-007` |
| `NG-M13` | `NG-M08`–`NG-M12` | open | 关闭 `NGW-010` |
| `NG-M14` | `NG-M13` | open | 关闭 `NGW-001`，完成结构整理 |
| `NG-M15` | 所有 `NGW-*` 已关闭 | open | 仅治理：删除一致性材料 |

### NG-M01——协议身份、分类入口和直接 Body 输入

**目标：** 在增加新语义能力前，先消灭“先 fan-out 再判断”，让现有直接 Body 路径
成为真实路径。

- Python 与 Godot 同一张卡从协议 v2 干净切换到 v3。信封按需包含协议版本、frame/
  event 类型、message/event ID、可选 `cause_id`、语义线路、actor/target、Runtime
  generation、world revision 和发生时间。
- Gateway 验证并分类后才投递；注册按目标定位的 Body sink/transport。App
  Orchestration 不得遍历所有 Elfie，把每个 Runtime 事件都试投给每个 Body。
- `NativeSensors` 排队保存类型化触觉/本体感知/身体输入，保留源 event/cause 身份和
  真实物理值。Godot 没有真实力值就表示未知，禁止从 intensity 伪造牛顿值。
- 旧说话可达输入在 `NG-M08` 前仍走 Nest 语义入口，但不能先走 Body。
- 区分 Runtime ready/health/generation 与 world configured/manifest 结果。
- 同一张卡删除 Nest 碰撞/触觉兼容入口、伪造力逻辑、全 Body fan-out 和全部 v2 解析。

**证据：** 聚焦协议往返；只有目标 Actor 收到回执和身体输入；其他 Actor 与 Nest 均不
收到；过期 generation 被拒绝；说话可达只进入 Nest；ready 只进入 Lifecycle；源码中
不存在 v2 parser、全 Body 循环或伪造力。

### NG-M02——空间与设施

**目标：** 让第一个 Nest 所有者管理 Godot 物理指代物的家庭含义，但不复制物理世界。

- 从宽 `NestState` 中抽出无坐标语义目录，通过 Nest Facade 提供房间、区域、anchor、
  设施和 capability 的类型化用例。
- 只接受 Godot 创作的稳定 ID 和经过验证的 manifest revision；保存设施用途/能力及
  规则真正需要的最小离散环境投影。
- 拒绝坐标、NodePath、导航数据、逐帧 Actor 状态和持久化的每只 Elfie 周围列表。
- 从 Nest 消费方移除宽泛姿态/active command mirror；只供展示的 Actor 投影留待
  `NG-M07` 进入 Observer 路径。

**证据：** 目录查询不含几何；未知/换版物理 ID 有明确处理；generation/revision 变化
使最小投影失效；现有调用方通过 Facade 而非可变 state 操作。

### NG-M03——巢内生活规则与 Home authority

**目标：** 把居民和 Home 决策放回 Nest，不能由 App SQL 或 Godot metadata 决定。

- 在 Nest Facade 后建立居民 ID、完整 `home_anchor_id`、归属、共享、预约、占用、访问
  和受众规则行为。
- App 负责认证/授权家庭管理员，然后调用 Nest 用例；App 不计算床位 ID，也不决定
  Home 规则。
- 所有管理和 Runtime 调用方迁出直接 `bed_number` SQL 假设以及 `bed-01` 等伪造值。
- Home 是 Nest 规则事实。可以向 Godot 传已经解析的物理 spawn/action target，但
  Godot 不得把它命名或持久化为 Home。

**证据：** 规则测试覆盖分配冲突和访问；API/用例测试证明 App 授权后由 Nest 决策；
Repository/SQL 不能绕过 Nest 用例；生产调用方不再伪造 Home ID。

### NG-M04——Nest 持久化切换

**目标：** 通过所有者定义的 Port 持久恢复 `NG-M02/03` 的状态，并保证只有一条存储
路径。

- 先解决 `DATA-01`。定义贴合所有者的 Repository 操作和 schema，保存完整稳定物理 ID
  与 Nest 规则状态，不做坐标算术。
- SQLite Adapter 与全部生产装配一次切换；删除“四张床一个宿舍”计算、`bed_number`
  authority 和旧宽状态 Repository。
- 不持久化说话/视觉/行动短期关联、直接 Body 状态或一般 Godot Actor snapshot。

**证据：** 目录/规则/Home 恢复往返、失败与重启测试、明确的数据决策记录；源码证明
只有一个 Repository binding，没有旧读写路径。

### NG-M05——时间与环境领域

**目标：** 把当前 elapsed seconds engine 变成 Nest 拥有的时间、阶段和期望环境行为，
但不假装 Godot 对象控制已经存在。

- 把 clock、pause/scale 和生活阶段计算放到时间与环境用例后。
- 把定时家庭环境规则和当前期望状态建模为 Nest 事实；个体睡眠/能量选择仍属于 Elfie。
- 只持久化重启所需 clock/policy/desired state。
- 本卡不建立 Godot 对象脚本或空环境 Gateway；真实命令/事实同步留给 `NG-M12`。

**证据：** 确定性 clock/phase/policy、pause/scale 和重启恢复测试；Nest 不依赖 physics
tick、Actor command 或渲染。

### NG-M06——用户消息归属清理

**目标：** 在删除 `InteractionHub` 前，先移走藏在 Nest 内但不属于世界的通信责任。

- 用户聊天走 App `message_delivery` 和 Elfie Communication，沿用既有授权、历史和
  回执所有权。
- 全部生产调用方迁移后，删除 `Nest.receive_user_message`、用户消息队列及相关
  `InteractionHub` 状态。
- 用户消息不得变成 Nest 广播或 Godot 事件。

**证据：** 真实聊天用例只到达所选 Elfie，并记录正常回执/历史；Nest 不再有用户消息
API、队列或持久副本。

### NG-M07——Godot 语义场景与物理投影

**目标：** 为后续说话、视觉、行动和环境建立一套稳定物理词汇，同时从 Godot 移除
家庭含义。

- 在场景/builder 中创作稳定 room/zone/anchor/object ID，由
  `semantic_scene_index.gd` 索引并发布带 revision、无几何的语义 manifest。
- 从 Godot actor catalogue 删除 `home_anchor_id`。创建 Actor 时可以接收已经解析的
  `spawn_anchor_id`，但 Godot 不保留它为什么是该居民 Home。
- 展示用 Actor pose/zone/current-command 投影进入 Observer 路径；Nest 只保留规则明确
  列出的最小离散物理状态。
- 随行为迁移逐步从 `main.gd` 和房间脚本抽出 endpoint、actor、world、observer 责任。
  复用 Godot physics/navigation/animation/query API，不为每个引擎类再包一层。
- 只有真实有状态或可交互对象才加窄脚本；静态家具只需语义 metadata，不是一物一脚本。

**证据：** reload 后 manifest ID 稳定；无 NodePath/坐标泄漏；Godot 无 Home 字段；
Observer 与 Nest 投影分离；既有移动/导航仍可工作。

### NG-M08——虚拟说话/听觉与公共 Nest 事件

**目标：** 完成第一条 Elfie–Nest–Godot 语义交互；只有真实 `HeardUtterance` 使用时才
建立事件管道。

- 增加 Elfie 自有的虚拟世界参与 Port，由 App Orchestration 实现跨 authority 协调，
  Elfie 不导入 Nest。物理身体可以保留不同的直接 `SpeechCommand` capability，它不是
  虚拟说话的兼容 fallback。
- 虚拟 speech intent 携带 utterance identity、text 和明确的 expressed emotion。
  Nest 保存内容；Godot 只接收 occurrence ID、speaker ID 和有限声学/传播参数。
- Godot 计算物理可达听众候选；Nest 规则解析最终居民受众，公共事件机制再为每位听众
  产生一个幂等、定向 `HeardUtterance`；App 按 ID 找真实 Elfie。
- 建立类型化 Nest event envelope/outbox：包含事实所有者、event ID、cause/origin ID、
  目标 ID、发生时间和 Runtime 来源。
- 删除按同一区域和 text-through-Godot 的旧说话链路。只有触觉（`NG-M01`）、用户消息
  （`NG-M06`）和说话全部迁走后，才在本卡删除 `InteractionHub`。

**证据：** 遮挡、超距、居民规则场景；text 与 expressed emotion 不进入 Godot frame；
speaker 和非听众不收到重复；重试保留身份；每位听众只收到一个语义事件；
`InteractionHub` 已不存在。

### NG-M09——结构化语义视觉

**目标：** 不用每只 Elfie 的渲染相机或截图推理，提供高效 Actor 相对视觉。

- 通过 Elfie 参与 Port 发出 observation intent/ID；Nest 建立短期关联并调用窄 Vision Port。
- Godot 根据 Actor transform、视野角、距离、遮挡和当前物理状态计算有上限的
  `VisibleSet`，只返回稳定 ID。
- Nest 批量连接设施/规则含义，产生一个定向 `SemanticVisualScene`；不保存周围物体列表。
- 有上限的重要变化可以复用同一路径，但不能形成默认逐帧流。

**证据：** 目标、遮挡、数量上限、过期 observation/generation；不存在每 Elfie Viewport、
screenshot/VLM 输入、坐标泄漏或无限逐帧事件。

### NG-M10——第一条语义行动：回 Home

**目标：** 用最小家庭语义行动证明“一次 intent 完整闭环”。

- 增加类型化 semantic-action intent，与自由字符串 direct motion 区分；在 Elfie → App
  coordinator → Nest 全程保留 intent、actor 和 authorization 身份。
- Nest 一次解析 `my Home` 和规则权限，以同一 intent 向 Godot 发送稳定目标；Godot
  负责寻路/执行并返回类型化物理终态。
- Nest 关联该结果并产生一个 `SemanticActionResult`；不能只为“先查目标再执行”要求
  第二次 Brain Turn。
- Nest 不能主动发起该 Actor 行动；已知目标的直接移动继续走 Body 通道。

**证据：** 成功、无 Home、禁止、不可达、中断、过期 generation；一个 intent 只有一个
终态；Body/Nest 不重复结果，Nest 不创建 Actor command。

### NG-M11——通用语义行动

**目标：** 泛化已经证明的闭环，但不建立万能字符串命令解释器。

- 只为已批准语义增加类型化 resolver/executor，例如具名设施、共享/可用物体、允许目的地。
- 分离 Nest 的语义目标解析与 Godot 的物理寻路/动作执行；capability/policy 失败是领域
  结果，不是任意 transport error。
- 每种行动定义取消、超时、幂等和终态规则。

**证据：** 第二种非 Home 行动证明复用；错误/未批准类型被拒绝；直接 Body 移动仍绕过
Nest；不存在只对 Home 特判的捷径后才关闭 `NGW-006`。

### NG-M12——环境对象、定时规则与恢复

**目标：** 完成 Nest 控制环境的行为，但不授予 Nest Actor 控制权。

- 增加时间与环境自有的期望对象状态窄 Port；Godot `environment_controller.gd` 把命令
  映射到真实有状态对象，并返回实际离散事实/结果。
- 只实现必要对象脚本，先完成一个真实能力（如一组灯）的端到端；门或可移动设施只在
  对应产品行为获批后加入。
- 实际环境变化进入空间与设施投影，需要居民事件时由事实所有者创建事件，再按需应用
  受众规则。
- Runtime 换代后重同步当前期望状态，不重放过期说话、动画或物理副作用。
- 环境命令与 Actor 命令分离；定时规则可以关灯，不能决定某只 Elfie 行走或睡觉。

**证据：** desired/actual、手动 override/规则、失败、重启、过期事实；一个有状态对象
端到端工作；Nest 时间规则不产生 Actor command。

### NG-M13——窄能力与 Bootstrap 收口

**目标：** 真实窄能力都存在后，删除剩余宽 `WorldRuntimePort`/通用协议表面。

- 每个消费方只拥有所需 capability：直接 Body transport、语义行动、视觉、声音可达、
  环境和 Runtime lifecycle/control。
- 一个具体 Godot Gateway 可以实现全部 Port，Bootstrap 只实例化一次并注入类型化视图；
  具体 Godot Adapter 之间不互相构造。
- 全部生产调用方迁移后，删除宽 world/session 方法、任意 dictionary payload 和旧
  Bootstrap alias。

**证据：** 依赖/Bootstrap 测试证明只有一个 Gateway 和 authority；每个消费方可用自己的
窄 fake 测试；源码找不到宽 Port 或旧 binding；关闭 `NGW-010`。

### NG-M14——Nest/Godot 最终结构整理

**目标：** 在行为已真实归位后，让物理结构匹配所有权，不改变可观察行为。

- 把剩余宽 `NestState`、engine、interaction 代码归入四个已实现所有者，保留 `Nest`
  稳定 Facade。
- 完成上文 Godot 结构；`main.gd` 只做装配/分发，endpoint、Actor、world、observer、lab
  不再混在宽脚本中。
- 删除旧路径的死 model、import、Adapter 和测试；不得只为保留旧 import 增加 wrapper。
- 只有结构真实成立后，才把公开 Developer architecture 当前页更新为新现状。

**证据：** 四个 Nest 所有者均有真实行为；公共事件机制不是业务所有者；Nest 无禁入
责任；聚焦架构测试通过并关闭 `NGW-001`。

### NG-M15——仅治理收口

**目标：** 只有产品匹配永久契约后，才删除临时迁移材料。

- 确认所有 `NGW-*` 行都有当前证据且已关闭，不存在临时 baseline。
- 在一个仅治理改动中，删除双语一致性台账、本文双语版本、注册项、索引链接、临时
  Agent 迁移引用和一致性专用测试断言。
- 保留永久契约、ADR、deny-all Scanner 和永久 authority 测试。

**证据：** Registry/治理/System 架构测试在无 Nest–Godot conformance 注册时通过；改动
中没有产品源码。

## 7. 每张卡的审查与完成模板

每张产品迁移卡都必须回答：

1. 本卡精确覆盖哪张迁移卡和哪个 `NGW-*` 关闭门？哪些相邻工作明确不做？
2. 每个变化事实迁移前后分别由谁拥有？
3. 唯一生产路径是什么？哪条旧路径在本卡删除？
4. actor/target、request/event/cause、generation 和 revision 身份怎样保持？
5. 重试、超时、取消、断连和过期输入分别怎么处理？
6. Python 是否复制了 Godot 几何或动态物理状态？
7. Nest 是否获得了发起 Actor 行为的能力？
8. Nest 是否仍只保存 ID，真实 Elfie 是否只由 App 查找？
9. 正向行为、禁止交叉路径和恢复场景是否都有测试？
10. 数据路径是否满足 `DATA-01`，且没有双存储？
11. 所有生产调用方是否迁移，旧代码是否真正删除？
12. 台账是否如实更新，而没有为了迎合未完成代码去修改目标契约？

只有当前 diff 与聚焦测试能证明以上答案时，本卡才完成。只写出类型、目录图或通过一个
WebSocket 测试都不足以完成迁移卡。
