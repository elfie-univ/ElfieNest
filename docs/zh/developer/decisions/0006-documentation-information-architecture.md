# ADR-0006：公开文档信息架构

- **状态：** 已接受
- **日期：** 2026-08-12
- **范围：** 公开文档结构与生命周期

## 背景

公开站点服务三类不同读者需求：理解世界观与故事、使用 ElfieNest，以及参与系统开发。
Developer 内容本身也有不同生命周期：当前架构、跨版本设计、规范性契约、临时一致性
差距、长期决策和工程指引。

如果信息架构不受保护，用户操作说明会漂移进 Developer 页面，工程页面会重新堆到
Developer 根目录，临时治理记录也可能被误认为永久历史。导航配置只能描述展示方式，
不能独立保护内容所有权和双语对等。

## 决策

公开根导航由首页、Story、User Guide 和 Developer Docs 组成。`getting-started/`
改为 `user-guide/`，因为该分区拥有完整用户手册，而不只是第一次启动引导。

Developer 内容直接分为 `architecture/`、可选的 `designs/`、`contracts/`、
`conformance/`、`decisions/` 和 `engineering/`。不增加 evolution、governance、
current-version 或 archive 包装层。侧栏先展示当前架构，再展示设计与治理，最后展示
工程实践。

英文与简体中文继续保持路径镜像，不保留空占位分区。详细 Conformance 只记录当前
差距，完全一致后删除；索引记录当前已经一致的状态，永久机器检查继续生效。

该结构由独立双语契约进行版本化，在 `docs/AGENTS.md` 中转化为编码 Agent 指引，
注册进 Contract Registry，并由聚焦架构测试和 VitePress 构建共同检查。

## 后果

读者能够在唯一明确的位置找到用户操作说明，也能通过统一的 Developer 模型理解当前
系统、系统演进和工程工作流。公开站点不积累历史执行噪声，但有长期价值的 Design 和
ADR 仍然可以追溯。

以后修改结构需要单独的治理 ADR 和契约更新。现有分类内的普通页面编辑继续保持轻量，
不需要 ADR。

被否决的方案包括：永久使用 `getting-started/` 作为完整用户手册名称、继续平铺
Developer 页面、增加更深的演进或归档目录、只依靠侧栏配置，以及归档每一次已经完成的
Conformance 执行记录。
