# Feature 层执行规则

本目录遵守 `app/AGENTS.md`。Feature 是具体产品用例和业务规则的实现层，不是只有
接口的空壳。

- 按业务所有权组织用例、授权、Command/Query/Result、业务错误和公开门面。
- Feature 定义自己消费的最小 Port；不得导入具体 Infrastructure、FastAPI、数据库
  连接、数据路径或 Adapter Record。
- 跨 Feature 只使用目标领域 `__init__.py` 暴露的公开门面，不能导入内部 Service、
  helper、Repository 或私有模型。
- 小领域可使用内聚的 `models.py` / `ports.py`；领域变大后按职责拆子包。禁止全局
  巨型 Models 文件，也不为每个 helper 创建 Port。
- 不启动线程、进程、无限循环或无所有者后台任务。外部副作用通过注入的 Port，跨
  authority 流程交给 `app/orchestration/`。

最终 Feature 所有者固定为 `accounts`、`adoption`、`communication`、`elfies`、
`nest_management`、`configuration`、`setup`、`bodies`、`operations`；其中
`configuration` 只包含可独立迁移的 `providers`、`food`、`capabilities`、`settings`
子域。目录存在不等于批准尚未实现的能力。

- `elfies` 只拥有授权目录与投影，不写 Elfie Profile、认知或记忆事实。
- `nest_management` 只通过公开 Nest 边界提供产品用例，不复制 Nest 事实。
- `bodies` 拥有注册、授权和 Elfie/body 关联；技术传输属于 Infrastructure，托管、
  归巢和切换属于 Orchestration。
- `operations` 只拥有当前系统维护用例和稳定管理投影；Runtime 启停属于
  `orchestration/lifecycle`，Observer Session 属于 `orchestration/observer`。
- `setup` 只拥有首装决策、草稿和状态；跨 Accounts、Provider、Food、Nest 的安装执行
  属于 `orchestration/setup_installation`。
- 当前 `administration`、`chat`、`elfie_profile`、`nest_registration` 和 Feature 层
  `embodiment` 是台账登记的迁移期目录，只能收缩，不得建立新所有权。
