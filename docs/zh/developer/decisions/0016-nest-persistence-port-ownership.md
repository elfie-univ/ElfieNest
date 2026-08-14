# ADR-0016：Nest 状态存储 Port 归 App Orchestration

- **状态：** 已接受
- **日期：** 2026-08-14
- **范围：** 系统级 Nest 持久化 Port 语义

## 背景

当前 `NestRepository`、`NestPersistenceSnapshot` 和持久化错误从 `nest/` 导出，但生产
代码中的 Nest 从不调用 Repository。加载、恢复、保存、回滚和恢复时机都由
`app/orchestration/nest_session` 决定，Bootstrap 注入 SQLite Adapter。这与系统/Nest
契约中“Repository Port 归 Nest”的表述冲突，也与应用契约“直接消费方拥有 Port”的
规则冲突。

把当前文件移成 `nest/persistence.py` 只会让目录看起来合理，却仍不符合真实调用方和
生命周期所有者。反过来，把领域事实也迁到 App 同样错误：协调持久化不会让 App 成为
居民、Home、家庭规则或环境意图的 authority。

## 决策

出站存储 Port 归直接消费能力的一方。当前 Nest 状态采用以下归属：

- Nest 拥有可持久语义事实、不含技术细节的 `NestSnapshot`，以及通过 Facade 导出和恢复
  合法聚合状态的操作；
- `app/orchestration/nest_session` 拥有 `NestStateStorePort`、稳定应用存储错误，以及
  加载/保存/回滚/恢复时机；
- `infrastructure/persistence/` 拥有 SQLite、SQL、Schema、事务、序列化、路径和具体
  Adapter；
- Bootstrap 构造 Adapter 并注入 Nest Session。

App Orchestration 可以协调持久化，但不得修改 Nest 内部状态、重新定义家庭含义或成为
领域事实的第二写入者；它只能保存和恢复由 Nest Facade 产生或接受的快照。

当领域本身直接消费存储能力时，领域自有 Port 仍然成立，例如 Elfie Brain 的 Memory。
Port 所有权跟随真实能力消费方，语义事实所有权与它相互独立。

## 后果

目标架构不存在 `nest/persistence.py` 或从 Nest 导出的 Repository Protocol。快照、Facade、
App Port、Adapter 类型、全部调用方和测试已经在同一切片中迁移完成，`NGW-R12` 现在已准备
收口。不增加兼容 Alias、Fallback Read 或双写。

本决策改变冻结的系统级 Port 语义，因此必须在产品迁移前更新双语系统契约。整个迁移
期间，具体持久化始终归 Infrastructure。
