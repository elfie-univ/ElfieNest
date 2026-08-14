# Godot Infrastructure 执行规则

本目录实现 Python 侧 Godot 技术 Adapter，受根目录 `AGENTS.md`、
[`System architecture contract`](../../docs/developer/contracts/system.md)、
[`Nest–Godot semantic-world contract`](../../docs/developer/contracts/nest-godot-semantic-world.md)
与 Runtime authority 规则约束。协议两端和全部生产调用方必须保持单一路径，不保留双路径。

- `lifecycle/` 只负责选择、启动、承载、观察和收束 Godot authority；不持有 Nest
  业务状态，不实现世界规则，也不成为产品协议路由层。
- `gateway/` 只负责版本化、认证的协议传输、Session、Frame 与 Bundle 检查；产品
  授权和 Nest 世界语义留在各自所有者。
- 一个 Gateway 可以实现直接 Body、Nest 语义行动/视觉/听觉/环境和 Runtime 控制等
  多个消费方窄 Port，但共享连接不能合并事件语义、目标和生命周期所有权。Adapter
  必须在投递前按事件类型、actor/target ID、generation 和 revision 分类，禁止默认
  fan-out 到全部 Body。
- `artifacts/` 只负责已导出 Runtime 产物的元数据、清单和校验；`godot_project/`
  永久保持独立源工程，不迁入本目录。
- `observer_world.py` 只把 NestSession 提供的几何无关语义投影映射为 Observer Port
  Model，并投递已有的高层意图；不拥有 Observer 授权、Nest 规则或第二份世界状态。
- Infrastructure Godot 子能力不得构造其他 Infrastructure 具体 Adapter；跨能力依赖
  经消费方窄 Port，由 `app/bootstrap/` 组合。
- Elfie/Nest 不得导入本目录的进程、传输或宿主实现。禁止恢复 `godot_runtime/`、
  在 Python 复制几何/导航/碰撞/渲染事实，或新增第二套 Gateway/authority 入口。
