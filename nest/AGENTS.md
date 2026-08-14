# Nest 领域核心执行规则

本目录实现唯一精灵巢的世界语义，并受根目录 `AGENTS.md` 与
[`System architecture contract`](../docs/developer/contracts/system.md)、
[`Nest–Godot semantic-world contract`](../docs/developer/contracts/nest-godot-semantic-world.md)
约束。

- 稳定、强类型的 `Nest` Facade 可以直接承担入站 Port；不得为形式统一重复定义接口。
- Nest 有空间与设施、巢内生活规则、时间与环境、精灵与巢交互四个功能所有者；这些
  是真实状态与行为边界，不要求预建四个空 Package。公共事件机制横贯四者，但不是
  第五个业务模块。
- 四个所有者的目标目录一一对应为 `space_facilities/`、`living_rules/`、
  `time_environment/`、`elfie_interaction/`。时间推进归时间与环境，不新增通用 `engine/`
  责任；状态、模型和错误跟随事实所有者，不向宽泛 `state/` 继续增加跨所有者行为。
  现有短名目录、`engine/`、`state/` 只按活动一致性台账的获批切片迁出，不为兼容保留
  第二公开 Facade。
- Nest 只保存居民 ID、Home、家庭规则、环境时间/期望状态、最小带来源环境投影，以及
  observation/utterance/semantic intent 的短期关联；不持有或构造真实 Elfie，不保存
  坐标、路径、动态视野或具体 Godot 连接。
- Nest 拥有技术无关的持久语义快照及通过 Facade 导出/恢复合法聚合状态的行为；当前
  加载、保存、回滚和恢复时机及 `NestStateStorePort` 由消费它的 App Orchestration
  拥有。Nest 仍为世界 authority 同步/事件接收定义出站 Port；任何 Port 都不得暴露
  SQLite、WebSocket、JSON 帧、环境变量、Godot bundle 或进程对象。
- 禁止导入 `app/`、`elfie/` 或具体 Infrastructure。真实 Elfie 与 Nest 的组合只由
  `app/orchestration/` 完成。
- 已知目标、无须家庭语义解析的 Actor 身体命令和身体感知经共享 Godot Adapter 直达
  所属 Elfie；需要“我的、共享、可用、允许”等语义的行动、结构化视觉、虚拟听觉和
  环境事实进入 Nest 窄类型边界。
- 每个事实由其所有者产生事件；生活规则只在需要时解析受众；路由器只向显式目标投递
  一次。广播只是 NestEvent 的受众形态，禁止把原始 Runtime 事件默认发送给所有 Body，
  也禁止同一语义事件同时走 Body 与 Nest，或同时进入类型化事件与无类型居民队列。
- Elfie 是自身身体意图的唯一发起者。Nest 只能在原 intent 授权内解析并转发目标，不能
  自主创建、定时触发或改写 Actor 行为；Nest 可以按时间/家庭规则命令环境对象。
- Godot 具体传输、协议和宿主已归位 `infrastructure/godot/`。Nest 只接收
  `app/orchestration/nest_session` 提供的类型化世界事实，不保存协议帧或连接状态。
