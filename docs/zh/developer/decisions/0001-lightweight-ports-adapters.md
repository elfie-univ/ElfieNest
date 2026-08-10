# ADR-0001：App 采用轻量 Ports/Adapters

- **状态：** 已接受
- **日期：** 2026-08-10
- **范围：** `app/`

## 背景

多轮功能开发后，Interface 会创建 Repository，Feature 依赖持久化细节，组合逻辑也
散落在不同入口。项目需要稳定所有权和可测试边界，但不需要微服务或复杂依赖注入仪式。

## 决策

App 采用轻量 Ports/Adapters 结构：

- Feature 仍是具体产品用例实现，不是只有接口的空层。
- 使用外部事实或副作用的 Feature/Orchestration 消费方定义最小 Port。
- Infrastructure 实现 Port，并拥有技术 Record 和 Adapter。
- Bootstrap 是唯一创建并注入具体 Adapter 的位置。
- Interface DTO、Feature Model、Port Model 和持久化 Record 各自有明确所有者，不能
  隐式跨边界传播。
- 小领域可以使用内聚的 `models.py` 和 `ports.py`；大领域可以拆成内聚子包。禁止
  全仓巨型 Models 文件，也不要求每个模型单独一个文件。
- Infrastructure 按技术能力组织，不需要逐个镜像 Feature 目录。

## 后果

现有代码按业务域逐个迁移，并受精确一致性基线约束。边界上会增加明确映射，但能
删除隐藏的框架/存储耦合，使产品用例可独立测试。设备传输仍属于 Infrastructure；
组合真实精灵、Nest 和外部身体的流程仍属于 Orchestration。

当前不采用原有直接依赖结构、每个 helper 一个 Port、全局万能 Repository、DI 框架、
完整 CQRS、Event Sourcing 或微服务。
