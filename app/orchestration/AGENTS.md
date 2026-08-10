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
