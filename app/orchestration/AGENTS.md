# Orchestration 层执行规则

本目录遵守 `app/AGENTS.md`，只负责跨 authority 或非原子外部副作用的产品流程。

- 可组合 Feature 公开契约和 `elfie`、`nest` 的公开 API；不得导入
  Interface、Bootstrap 或具体 Infrastructure。
- Orchestration 自己消费的 Gateway、持久化、设备或任务能力由本层定义 Port，再由
  Infrastructure 实现、Bootstrap 注入。
- 普通 CRUD、单领域授权和页面聚合不得为了“统一入口”搬到本层。
- 单只精灵通过注入的 Food/模型/工具 Port 完成普通调用，不经过本层。
- 外部工作流明确持久状态、幂等键、超时、回执、取消和恢复；数据库事务中不得等待
  Godot、模型、网络或设备。
- `lifecycle/` 是 Runtime 生命周期唯一所有者；`embodiment/` 只协调真实精灵、Nest
  与外部身体，不拥有设备传输实现。

最终工作流目录固定为 `lifecycle`、`nest_session`、`resident_admission`、
`setup_installation`、`message_delivery`、`embodiment`、`observer`：

- `nest_session` 组合唯一 Nest、真实 Elfie、世界事件和共享 Godot world channel；
- `resident_admission` 只协调已接受领养、Elfie 构造、Nest 接纳和失败补偿；
- `setup_installation` 只协调 Setup 状态与 Accounts、Provider/模型、Food、Nest 和受管
  安装 Runner；
- `message_delivery` 协调已授权会话、用户可见历史、真实 Elfie 投递与回执；
- `observer` 协调受限主体/能力、授权投影和允许的高层意图。

不得在 Orchestration 根恢复平铺工作流文件；工作流必须进入以上固定目录。模型、Godot、
通信或平台的具体技术 Adapter 必须进入对应根 Infrastructure 能力包。
