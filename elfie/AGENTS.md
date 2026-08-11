# Elfie 领域核心执行规则

本目录实现一只完整精灵，并受根目录 `AGENTS.md`、
[`System architecture contract`](../docs/developer/contracts/system.md) 与
[`Elfie internal architecture contract`](../docs/developer/contracts/elfie.md) 约束。
当前实现偏差以
[`Elfie conformance`](../docs/developer/conformance/elfie.md) 为准，不得用现状反向降低
契约目标。

- 稳定、强类型的 `Elfie` / `ElfieFactory` Facade 可以直接承担入站 Port；没有真实
  隔离需求时，不再复制一套同形 Protocol。
- Elfie 保留档案、认知、情绪、记忆语义与算法、Skills、神经系统、通信语义、身体
  契约和自身生命周期；Skills 的目标所有者是 Brain。
- Elfie 为自己需要的 Food 读取、模型调用、工具执行、身体执行与感知、外部通信和
  语义持久化定义出站 Port；Port 使用领域语言，禁止泄漏 Provider SDK、Godot 帧、
  SQLite Row、路径或设备协议。
- 普通运行链路由 Bootstrap 直接注入 `FoodPort`、`ModelPort`、`ToolPort` 的
  Infrastructure 实现，不经过 App Feature 或 Orchestration；Elfie 不自行执行 SQL。
- Body 和 Communication 使用嵌套 Ports/Adapters，因为一只 Elfie 可以注册多具身体
  和多个通信渠道。`BodyPort` 与渠道 Port 定义在其领域使用方旁，具体 Godot、设备、
  网络和平台实现最终归 Infrastructure。
- 每个 Body、Channel、Memory、Profile、Food、Model 和 Tool Port
  只暴露一只已授权 Elfie 的作用域；底层 Adapter 可以共享容器级连接池或 Gateway，
  但不得暴露跨 Elfie 查询、变成 Service Locator 或把共享清理权交给 Elfie。
- Bootstrap 只负责构造、注入、容器生命期与清理登记；系统 Runtime start/stop/restart
  只由 `app/orchestration/lifecycle` 决策。Elfie 生命周期不得控制 Core、Gateway、
  Godot authority 或共享 Adapter。
- 禁止导入 `app/`、`nest/` 或具体 Infrastructure，禁止在新增代码中创建 SQLite、
  YAML 可变存储、网络、Godot、设备或操作系统实现。
- 现有具体技术实现与公共边界偏差以 Conformance Register 中仍开放的条目为准，只能在
  单独获批的完整迁移切片中删除或下移；本规则本身不授权搬迁源码、添加兼容层或保留双路径。
- 单元测试优先注入 fake/in-memory Port，不以真实数据库、文件、网络、设备或 Godot
  作为领域逻辑成立的前提。
