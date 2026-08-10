# Elfie 领域核心执行规则

本目录实现一只完整精灵，并受根目录 `AGENTS.md` 与
[`System architecture contract`](../docs/developer/contracts/system.md) 约束。

- 稳定、强类型的 `Elfie` / `ElfieFactory` Facade 可以直接承担入站 Port；没有真实
  隔离需求时，不再复制一套同形 Protocol。
- Elfie 保留档案、认知、情绪、记忆语义与算法、Skills、通信语义、身体契约和生命周期。
- Elfie 为自己需要的 Food 读取、模型调用、工具执行、身体执行与感知、外部通信和
  语义持久化定义出站 Port；Port 使用领域语言，禁止泄漏 Provider SDK、Godot 帧、
  SQLite Row、路径或设备协议。
- 普通运行链路由 Bootstrap 直接注入 `FoodPort`、`ModelPort`、`ToolPort` 的
  Infrastructure 实现，不经过 App Feature 或 Orchestration；Elfie 不自行执行 SQL。
- 禁止导入 `app/`、`nest/` 或具体 Infrastructure，禁止在新增代码中创建 SQLite、
  YAML 可变存储、网络、Godot、设备或操作系统实现。
- 现有具体技术实现是 `SYS-002` 迁移债务，只能在单独获批的迁移闭环中删除或下移；
  本规则本身不授权搬迁源码。
- 单元测试优先注入 fake/in-memory Port，不以真实数据库、文件、网络、设备或 Godot
  作为领域逻辑成立的前提。
