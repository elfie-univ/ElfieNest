# Godot Runtime 宿主执行规则

本目录是当前 Godot authority 宿主路径，受根目录 `AGENTS.md`、
[`System architecture contract`](../docs/developer/contracts/system.md) 和 Runtime authority
规则约束。

- 只负责选择、启动、承载、观察和收束 Godot authority；不持有 Nest 业务状态，
  不实现世界规则，也不成为产品协议路由层。
- 对领域暴露的边界必须是共享、版本化、认证的 Adapter；Elfie/Nest 不得导入本目录
  的进程、传输或宿主实现。
- 与当前 `nest/godot_gateway/` 一起收敛到根 `infrastructure/godot/` 属于 `SYS-001`
  后续迁移；`godot_project/` 保持独立且不迁移。未经单独批准不得搬迁。
