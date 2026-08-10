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
