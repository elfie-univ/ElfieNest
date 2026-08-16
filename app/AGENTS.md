# App 应用架构执行规则

本文件作用于整个 `app/`，是公开
[`Application architecture contract`](../docs/developer/contracts/application.md)
的代理执行摘要，并受
[`System architecture contract`](../docs/developer/contracts/system.md) 的顶层边界及
[`Service lifecycle contract`](../docs/developer/contracts/service-lifecycle.md) 的运行时
边界约束。当前用户指令和根目录 `AGENTS.md` 优先；子目录 `AGENTS.md` 只能
细化本文件，不能改变依赖方向、所有权或契约。App 架构债务已清零；以下长期边界由
永久 Scanner 和架构测试直接执行。

## 目标依赖方向

```text
interfaces    -> Feature 公开用例 / Orchestration 公开门面
features      -> 自有 Model、Port + 获准的领域公开 API
orchestration -> App Port + elfie / nest 公开 API
root infrastructure -> 实现 Feature / Orchestration Port + 技术库
bootstrap     -> 以上所有模块（仅创建、注入、生命周期装配）
```

- `interfaces/` 只处理协议、认证入口、参数解析、DTO 映射和错误映射；不得直接导入
  具体 Repository、设备实现或持久化工具，不得创建 Adapter。
- `features/` 按业务域承载用例、业务规则、授权和应用模型；不得导入 FastAPI、具体
  Infrastructure、数据库连接或数据路径，也不得启动线程、进程或后台任务。
- `orchestration/` 只承载跨两个以上 authority、跨模块副作用或 Runtime 生命周期
  流程；不得直接依赖具体 Infrastructure，也不得成为普通 CRUD、Food 读取、模型调用
  或工具执行的中转层。
- 根 `infrastructure/` 是 Adapter 的唯一生产位置，承载 SQL、文件系统、网络、模型
  平台和设备传输等技术细节；不得决定产品权限或业务流程。禁止恢复
  `app/infrastructure/` 产品实现或第二个 Adapter 根。
- Infrastructure 各能力包不得导入或构造彼此的具体 Adapter；跨能力依赖使用窄 Port，
  由 Bootstrap 注入。
- `bootstrap/` 是唯一生产组合根，只负责实例化、注入、Container 对象生命周期和
  清理装配；Runtime 组件启停与重启流程只属于 `orchestration/lifecycle`。Bootstrap
  不写业务分支、SQL、协议映射或第二套配置事实。

禁止反向依赖，也不得恢复已退役路径。

## 最终业务与工作流目录

应用架构契约冻结以下业务与工作流所有权：

```text
features/
├── accounts/
├── adoption/
├── communication/
├── elfies/
├── nest_management/
├── configuration/
│   ├── providers/
│   ├── food/
│   ├── capabilities/
│   └── settings/
├── setup/
├── bodies/
└── operations/

orchestration/
├── lifecycle/
├── nest_session/
├── resident_admission/
├── setup_installation/
├── message_delivery/
├── embodiment/
└── observer/
```

- 目录只表达最终所有权，不批准新功能，也不要求提前创建空目录。
- 禁止恢复已退役的 `administration`、`chat`、`elfie_profile`、`nest_registration`
  和 Feature 层 `embodiment` 目录。
- Orchestration 按真实跨 authority 工作流命名，不为每个 Feature 机械建立同名目录。
- 新能力以可运行的纵向切片完成必要的 Interface、Feature/Orchestration、Port、根
  Infrastructure Adapter、Bootstrap 装配和真实调用方；Bootstrap 与 Infrastructure
  不作为独立横向阶段。

## Feature、Port 与公开门面

- 一个 Feature 目录对应一个业务所有者。跨 Feature 调用只通过目标领域公开门面，
  不导入其内部 `service.py`、私有 helper 或 Repository。
- Port 只用于外部事实、持久化、时钟、网络、设备、模型、任务调度等可替换或有副作用
  的边界；普通纯函数和领域内部 helper 不为“形式统一”创建 Port。
- Port、命令、查询、结果和业务错误由使用它的 Feature 或 Orchestration 拥有；具体
  Adapter 目标位于根 `infrastructure/`，由 `bootstrap/` 注入。
- Feature 通过 `__init__.py` 暴露稳定用例和模型；调用方不得绕过门面
  读取内部实现。
- 不新增万能 Repository、Service Locator、自动扫描式 DI、事件总线、完整 CQRS、
  Event Sourcing 或分布式事务框架，除非用户单独批准。

## 边界模型与类型

- HTTP/WS DTO、Feature Command/Query/Result、Port 数据模型和持久化 Record 是不同
  边界的模型；不得把 ORM/SQLite Row、FastAPI Request、任意字典跨层传递。
- 所有公开边界使用命名、严格类型；禁止新增 `Any`、`Dict[str, Any]`、无约束字典、
  动态字段和仅靠类型断言成立的契约。
- Pydantic 负责协议/配置校验；领域内部可使用 dataclass、Protocol、Enum 和明确的
  值对象。不要为同一事实维护第二份手写 Schema。
- 新增或修改的公开边界必须进入严格类型检查范围，不得新增类型债。

## 身份、授权与错误

- Interface 负责验证凭据并构造严格 `Principal` / `RequestContext`；Feature 根据用例
  和资源关系授权。前端隐藏按钮、URL 前缀和调用方自报身份都不是授权。
- `user`、`setup`、`admin`、`observer`、`device` 等主体使用不同的最小权限模型；
  不把管理员会话或 Runtime authority 凭据复用于设备和 Observer。
- Feature/Orchestration 抛出稳定、可测试的业务错误；Interface 统一映射 HTTP/WS
  状态和错误 envelope。Infrastructure 异常不得原样泄漏到协议层。

## 一致性与副作用

- 数据库原子修改由一个明确 Unit of Work / 事务边界拥有；Repository 不得在多步
  用例中暗自提交。SQL 仍只能存在于获准的持久化目录。
- 文件配置使用强类型文档、单写入者、临时文件加原子替换；禁止双写或第二事实源。
- 网络、模型、Godot、设备等外部流程使用持久状态、幂等键、超时、回执和必要的补偿；
  不伪装成数据库事务。
- 数据库事务中不得等待网络、模型、Godot 或设备响应。命令改变事实；查询只能读取
  权威事实或明确的派生投影，不在读操作中偷偷修复状态。
- 重试只用于明确可重试且幂等的操作。跨边界调用必须有超时；长任务必须返回稳定
  `task_id`，支持状态查询，并明确取消、失败和进程重启后的语义。

## 生命周期、配置与可观测性

- 进程级 Container/Gateway/无状态 Service 由 Bootstrap 持有；Unit of Work、
  Repository、Principal 属于请求或用例；WebSocket 会话属于连接；后台 Job 属于
  任务调度器。不得把请求对象或数据库连接缓存为全局单例。
- Feature 不直接调用 `Thread`、`Process`、`asyncio.create_task` 或无限循环。后台工作
  由受生命周期管理的 Scheduler/Runner Port 执行；Runtime 启停仍只属于
  `app/orchestration/lifecycle`。
- 生命周期查询严格只读；`OFFLINE / CORE_READY / WORLD_READY`、模型健康投影、
  generation 与 phase 必须来自同一权威快照，Interface 不得按端口或页面状态重算。
- 配置有一个类型化所有者和明确优先级；Secret 只以引用或专用 Secret Port 流动，
  不进入普通 DTO、日志和缓存。缓存必须声明权威源、失效条件、作用域和可重建性。
- 请求、任务和外部工作流传递关联 ID；日志只记录安全上下文，不记录密码、Token、
  API Key 或完整设备凭据。

## 验证与防回退

- `scripts/architecture/app_layer_scan.py --mode deny-all` 与
  `test/architecture/test_app_layer_boundaries.py` 是 App 依赖、目录和协议边界的永久门禁；
  不得恢复空基线或为回退增加 allowlist。
- 新能力必须同时验证直接契约、授权/事务/错误/超时/幂等语义和至少一条真实调用路径；
  不得交付半条调用链、长期双写、隐藏 Fallback 或只靠兼容 Alias 维持的状态。
- 临时缺口只有在仓库治理契约要求的台账、精确证据和删除门齐全时才能存在；最后一个
  缺口清零后必须执行零债务治理收口。
