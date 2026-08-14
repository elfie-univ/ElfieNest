# Configuration Feature 执行规则

本目录拥有管理员配置用例，包括 Food 管理、Provider 管理投影、全局工具设置和其他
系统配置，继承 `app/features/AGENTS.md`。

- 每份配置只有一个语义所有者、一个强类型 Schema、一个写入 Port 和明确优先级；
  禁止双写、第二事实源、任意 `{section: dict}` 接口或隐式 Fallback Read。
- Provider 连接管理和凭据引用属于本 Feature；Provider 目录/发现、连接协议和模型探测
  的技术实现属于 `infrastructure/models/`。Food 管理和全局工具启用属于本 Feature；
  工具实际执行属于 `infrastructure/tools/`。
- 模型验证与提醒的调度策略属于本 Feature，后台执行通过 App 自有 Scheduler/Runner
  Port；它不是 Runtime 进程生命周期。
- Secret 只能通过引用或专用 Secret Port 流动。管理投影不得返回密钥、供应商 SDK
  对象、数据库 Row 或内部技术 Record。
- 配置 Command 负责校验业务约束；持久化 Adapter 负责原子写入。普通 Elfie Runtime
  通过自有 Port 读取有效 Food/模型/工具投影，不经过本 Feature 作为运行时中转。
- 物种可用性由 `elfie/profile` 的不可变注册表和资源校验决定，不属于管理员设置。不得
  新增或恢复 `allowed_species_ids` 之类的物种白名单、持久化字段或按精灵巢审批流程。
