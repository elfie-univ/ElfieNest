# 应用架构一致性台账

> 本文是规范性[应用架构契约](../contracts/application)的临时实现缺口台账，只记录
> 当前历史不合规，不定义架构，也不批准新的例外。当全部条目关闭且精确机器基线清零
> 后，删除本页及其导航入口。

## 状态与证据规则

- `open`：当前生产代码仍违反契约。
- `in progress`：一个业务域正在迁移，但完整完成条件尚未通过。
- `closed`：调用方、实现、测试和机器基线已经全部清理。
- 不能因为文档、接口或替代类已经存在就关闭条目；旧生产调用链也必须删除。
- 每个机器例外都带一个缺口 ID。禁止未登记例外，缺口 ID 也不能批准新增同类违规。

可执行事实源是 `test/architecture/baselines/app_layer.py`，其中条目精确到 import、
函数、构造点或 Route。架构测试要求它与当前代码精确一致：删除债务时必须在同一改动
删除基线条目；新增或恢复债务会失败。本文只按原因和验收门归组，不复制整份机器清单。

## 当前缺口

| ID | 严重级别 | 状态 | 当前缺口 | 验收门 |
| --- | --- | --- | --- | --- |
| APP-001 | P0 | open | Interface 直接导入具体持久化/设备实现，因此知道技术存储和 Gateway 细节。 | 所有 Interface 只依赖注入的 Feature/Orchestration 公开服务和协议模型；`interface -> infrastructure` 机器集合清零。 |
| APP-002 | P0 | open | Feature 导入具体 Infrastructure，部分公开用例接收 `db_path`，一个 Feature 导入 FastAPI；embodiment Orchestration 也导入持久化实现。 | 用使用方拥有的 Port 替代具体依赖，公开用例接收类型化依赖，Feature/Orchestration 隔离机器集合清零。 |
| APP-003 | P0 | open | 组合根不完整；API/CLI 工厂、Route 和依赖 helper 会构造 Repository、Store 或 Registry。 | Bootstrap 拥有构造和生命周期，入口接收应用 Container 或明确 Service，Interface 构造机器集合清零。 |
| APP-004 | P1 | open | Interface 和 Feature 导入其他 Feature 内部模块；Infrastructure 也依赖一个 Feature 私有模块；稳定包门面不一致。 | 每个已迁移领域只暴露一个公开门面，跨域调用使用门面或自有 Port；内部 import 机器集合清零，App import 图无环。 |
| APP-005 | P1 | open | 许多 JSON Route 没有命名 `response_model`，协议边界仍有松散字典/`Any` 注解。 | 所有产品 Route 使用严格请求/响应模型和统一错误 envelope；非 JSON 页面/流响应明确声明；Route 模型与松散注解机器集合清零。 |
| APP-006 | P1 | open | 认证、角色检查和错误映射散落在 Interface 与 Feature helper 中，没有统一 Principal/RequestContext 和业务错误分类。 | user/setup/admin/observer/device 使用严格主体；Interface 认证、Feature 授权；业务错误只有一套已测试协议映射。 |
| APP-007 | P1 | open | 事务所有权、Repository commit、类型化文件写入和外部工作流恢复尚未通过 Port 与测试统一表达。 | 每个已迁移 command 声明数据库、文件或外部工作流一致性类别；DB 事务内不等待外部响应；原子性和恢复测试通过。 |
| APP-008 | P1 | open | 部分 Feature 持有线程/Job 或阻塞平台工作，任务取消、超时、回执和重启语义不一致。 | Scheduler/Runner Port 拥有后台工作，Bootstrap/lifecycle 拥有 Runner；异步边界和长任务语义有聚焦测试。 |
| APP-009 | P1 | open | 全局 MyPy 仍非 strict，尚未建立已迁移领域严格区。 | 每个已迁移领域及其公开调用方通过 strict MyPy，不使用 `Any` 逃生口；领域关闭时扩大 strict override。 |
| APP-010 | P1 | open | 外部身体持久化与设备注册存在重叠 Registry/Repository；embodiment 契约导入持久化 Record，Orchestration 携带 `db_path`。 | 只保留一套外部身体产品模型和使用方 Port；设备传输是 Infrastructure Adapter；托管/归巢仍属于 Orchestration；删除重复事实和具体 import。 |
| APP-011 | P1 | open | 版本化和历史产品 API 并存，存在重复调用方投影和无类型旧资源。 | 按 `app/interfaces/api/AGENTS.md` 逐业务域迁移，移动全部真实调用方，再删除旧 Route、Client、DTO 和夹具，不保留别名。 |
| APP-012 | P1 | open | App 各领域的配置、Secret 和缓存尚未共用一套可执行所有权模板。 | 每个已迁移配置只有一个类型化所有者/写入者和优先级；Secret 使用引用/Secret Port；缓存声明权威源、失效、寿命和重建方式。 |

## 机器覆盖

当前 App 精确 Scanner 与 `app_layer.py` 基线覆盖 `APP-001`、`APP-002`、`APP-003`、
`APP-004`、`APP-005`、`APP-008`、`APP-011`。其余授权、事务、严格类型、外部躯体事实和
配置所有权条目，需要在选中各业务域迁移时补充专属测试和审查。Scanner 通过只证明未
新增已覆盖违规且基线精确，不代表整个 App 契约已经达标。

## 迁移单元记录

每个获批的领域迁移在改代码前向本节添加一份短记录：

```text
业务域：
缺口 ID：
当前权威事实：
Route 与生产调用方：
目标公开门面与模型：
Port 与 Adapter：
一致性类别：
Principal 与授权：
超时 / 重试 / 幂等：
历史删除清单：
聚焦测试与端到端验收：
需要删除的机器基线条目：
状态：open | in progress | closed
```

这份记录是执行检查表，不是设计权威。只有应用架构契约中的十二项完成条件全部通过，
领域才能关闭。即使属于同一业务域，API 调用方迁移、持久化变化和 UI 变化仍应保持
可分别审阅。

## 初始业务域盘点

当前应用业务域包括 accounts、administration、adoption、configuration、setup、
chat、Elfie profile、Nest management/registration 和 embodiment。这里不规定优先级，
也不批准整体重写。维护者一次选择一个领域，先记录精确调用链和删除门，再开始实现。

已经讨论过的 API 清理仍是第一条迁移流。容量闭环和基于硬件的本地模型推荐仍是独立
产品变更，不能藏进架构迁移。
