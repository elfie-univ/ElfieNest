# Configuration Feature 执行规则

本目录拥有管理员配置用例，包括 Food 管理、Provider 管理投影、全局工具设置和其他
系统配置，继承 `app/features/AGENTS.md`。

- 每份配置只有一个语义所有者、一个强类型 Schema、一个写入 Port 和明确优先级；
  禁止双写、第二事实源、任意 `{section: dict}` 接口或隐式 Fallback Read。
- 根 `config/` 是不可写内置默认值，`${ELFIE_HOME}/configs/` 是用户配置；Feature 只能
  通过自身 Port 读写归其所有的强类型用户文档或 section，不能直接读文件、修改内置
  默认值，或把“用户优先”扩张为通用深合并。
- Provider 连接管理和凭据引用属于本 Feature；Provider 目录/发现、连接协议和模型探测
  的技术实现属于 `infrastructure/models/`。Food 管理和全局工具启用属于本 Feature；
  工具实际执行属于 `infrastructure/tools/`。
- 模型验证与提醒的调度策略属于本 Feature，后台执行通过 App 自有 Scheduler/Runner
  Port；它不是 Runtime 进程生命周期。
- Secret 只能通过引用或专用 Secret Port 流动。管理投影不得返回密钥、供应商 SDK
  对象、数据库 Row 或内部技术 Record。
- 配置 Command 负责校验业务约束；持久化 Adapter 负责原子写入。普通 Elfie Runtime
  通过自有 Port 读取有效 Food/模型/工具投影，不经过本 Feature 作为运行时中转。
- 物种可用性来自已发布 Genesis 资料源的强类型“创建可用性”投影，并受独立包/资源校验；
  它不属于 Profile 或管理员设置，也不得与 Godot/展示使用的运行时资产投影混为一个目录。
  不得新增或恢复 `allowed_species_ids` 之类的物种白名单、持久化字段或按精灵巢审批流程。
