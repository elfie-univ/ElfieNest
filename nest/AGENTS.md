# Nest 领域核心执行规则

本目录实现唯一精灵巢的世界语义，并受根目录 `AGENTS.md` 与
[`System architecture contract`](../docs/developer/contracts/system.md) 约束。

- 稳定、强类型的 `Nest` Facade 可以直接承担入站 Port；不得为形式统一重复定义接口。
- Nest 保留居民 ID、住所与床位状态、环境时间、互动传播、声音受众、触碰后果等世界规则；
  不持有或构造真实 Elfie 对象。
- Nest 为语义持久化及世界 authority 同步/事件接收定义出站 Port；Port 不暴露
  SQLite、WebSocket、JSON 帧、环境变量、Godot bundle 或进程对象。
- 禁止导入 `app/`、`elfie/` 或具体 Infrastructure。真实 Elfie 与 Nest 的组合只由
  `app/orchestration/` 完成。
- Actor 身体命令可以经共享 Godot Adapter 直达 authority；全局世界事实必须进入
  Nest 规则，再由 Orchestration 向受影响 Elfie 分发类型化感知。
- Godot 具体传输、协议和宿主已归位 `infrastructure/godot/`。Nest 只接收
  `app/orchestration/nest_session` 提供的类型化世界事实，不保存协议帧或连接状态。
