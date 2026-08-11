# Godot Infrastructure 执行规则

本目录实现 Python 侧 Godot 技术 Adapter，受根目录 `AGENTS.md`、
[`System architecture contract`](../../docs/developer/contracts/system.md) 与 Runtime
authority 规则约束。

- `lifecycle/` 只负责选择、启动、承载、观察和收束 Godot authority；不持有 Nest
  业务状态，不实现世界规则，也不成为产品协议路由层。
- `gateway/` 只负责版本化、认证的协议传输、Session、Frame 与 Bundle 检查；产品
  授权和 Nest 世界语义留在各自所有者。
- `artifacts/` 只负责已导出 Runtime 产物的元数据、清单和校验；`godot_project/`
  永久保持独立源工程，不迁入本目录。
- Infrastructure Godot 子能力不得构造其他 Infrastructure 具体 Adapter；跨能力依赖
  经消费方窄 Port，由 `app/bootstrap/` 组合。
- Elfie/Nest 不得导入本目录的进程、传输或宿主实现。禁止恢复 `godot_runtime/`、
  在 Python 复制几何/导航/碰撞/渲染事实，或新增第二套 Gateway/authority 入口。
