# 公开文档目录规则

本文件只作用于 `docs/`。根目录 README 和社区文档也遵循同样的双语原则。

- 公开文档默认语言为英文，同时维护简体中文版本。英文位于站点根目录，中文位于
  `zh/`；修改现有公开页面时在同一改动中更新对应的中英文两份。
- 路径、标识符、API、协议字段和第三方产品名可以保留英文并用中文说明。
- 这里只发布最终读者需要、与当前实现一致且经用户审阅的内容。会议记录、提示词、
  模型中间稿、历史草案、合作材料和未开发剧情留在私有区域。
- 不为解释代码而维护冗余 JSON Schema；代码中的类型模型是内部契约事实源。
- 只有公开命令、用户可见行为、公开 API 或永久数据契约变化时，代码任务才需要
  同步公开文档。内部重构和测试调整不得自动扩大为文档任务。
- 任何公开能力、剧情秘密、截图或页面上线前都需要负责人目视审阅；无法证明已经
  实现的能力应标为规划，或不公开。

## 站点信息架构

公开内容分为首页、`story/`、`user-guide/` 和 `developer/`。英文位于站点根，
中文在 `zh/` 下保持相同相对路径。旧 `getting-started/` 禁止恢复；用户安装、配置、
运行和排障统一属于 `user-guide/`。

Developer 内容直接分为 `architecture/`、可选的 `designs/`、`contracts/`、
`conformance/`、`decisions/` 和 `engineering/`，不得再增加 `current/`、
`evolution/`、`governance/`、`archive/` 等包装层。`developer/` 根目录只保留
`index.md`；可选分类没有获批页面时不创建空目录。

- `architecture/` 只描述当前、已验证的实现；
- `designs/` 保存有长期价值且已经审阅的跨版本重大设计；
- `contracts/` 保存当前权威的版本化规范；
- `conformance/` 只保存当前差距，完全一致后删除详细台账；
- `decisions/` 永久保存已接受 ADR；
- `engineering/` 解释开发、质量、测试、调试、工具、安全和发布实践。

结构权威见双语
[`Documentation structure contract`](developer/contracts/documentation-structure.md)。修改
顶级分区、Developer 分类、分类含义、双语镜像或生命周期时，必须使用独立治理变更，
同步更新新 ADR、契约版本、本文件、VitePress 导航、Contract Registry 和聚焦架构测试。

## 架构治理文档

`developer/architecture/` 只描述当前事实，`developer/contracts/` 定义长期目标，
`developer/conformance/` 记录临时差距，`developer/decisions/` 保存已接受 ADR。四类
文档不能互相代替，当前架构页必须显式链接目标契约，台账不能重新定义目标。

- 修改规范性契约时同步修改英文和 `zh/` 镜像并升级同一版本；所有权、依赖方向或
  authority 变化必须有 ADR，且同步更新受影响 `AGENTS.md` 和机器门禁。
- 宏观架构 v1 已冻结；以后改变顶层模块、authority、依赖方向、生产组合/生命周期或
  系统级 Port 语义时，必须新建独立双语 ADR，并先提交不含产品代码的治理变更。
- 产品迁移只更新当前事实说明、Conformance 和精确 Baseline；不得顺手改写目标契约
  或 Scanner。治理变更不得混入实现侧文件。
- 普通 Markdown 内容在治理/实现分类中保持中立；`docs/.vitepress/`、文档站
  `package.json` 和锁文件属于实现侧，不能与契约、ADR、Scanner 等治理变更混在同一
  提交或 Pull Request。
- Conformance 只保留仍然存在的缺口、验收门和迁移顺序；历史测试次数、过期失败、
  会话过程和已完成执行计划不作为长期台账内容。
- 最后一个缺口和 Baseline 条目清零后，先以五类逐行证据把双语台账标为 ready，再立即
  按仓库治理契约进行独立治理收口：删除空 Baseline、待收口台账及其注册表、测试、索引、
  链接和局部 Agent 迁移指引；基线检查器必须观察删除本身，永久 Scanner 和架构测试继续
  以 deny-all 执行。
- 中英文语义同步由契约注册测试、文档构建和人工审查共同保证；不能只改版本字符串
  或复制一份未翻译文本来通过机器检查。
