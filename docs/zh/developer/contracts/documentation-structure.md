# 文档结构契约

**契约版本：** 1.0<br>
**采纳日期：** 2026-08-12<br>
**强制范围：** 公开文档信息架构

本契约定义稳定的公开文档分区、各类 Developer 文档的含义，以及修改这些结构时必须
遵循的治理流程。它保护导航和文档所有权，但不会把普通内容编辑变成架构流程。

## 公开站点结构

英文是站点默认根，简体中文位于 `docs/zh/`，并与英文保持语义镜像。

```text
docs/
├── index.md
├── story/
├── user-guide/
├── developer/
│   ├── index.md
│   ├── architecture/
│   ├── designs/          # 第一篇经审阅的公开设计出现时再创建
│   ├── contracts/
│   ├── conformance/
│   ├── decisions/
│   └── engineering/
└── zh/
    ├── index.md
    ├── story/
    ├── user-guide/
    └── developer/
        ├── index.md
        ├── architecture/
        ├── designs/      # 存在公开设计时与英文镜像
        ├── contracts/
        ├── conformance/
        ├── decisions/
        └── engineering/
```

`docs/.vitepress/` 和 `docs/public/` 是站点实现目录，不是面向读者的内容分区。
`docs/.internal/` 是私有目录，不参与站点构建，也不得被公开页面链接。可选内容分区只在
已经存在获批页面时创建，不保留空占位目录。

旧 `getting-started/` 分区禁止恢复。面向最终用户的安装、配置、运行和故障排查统一
属于 `user-guide/`。

## Developer 文档分类

Developer 分类直接位于 `developer/` 下。禁止增加 `current/`、`evolution/`、
`governance/`、`archive/` 等包装目录。Developer 根目录下只允许
`developer/index.md` 这一篇 Markdown 页面。

| 目录 | 职责 | 生命周期 |
| --- | --- | --- |
| `architecture/` | 描述当前、已经验证的实现和运行结构 | 原位更新，历史留在 Git |
| `designs/` | 保存跨已发布、活跃和被取代版本的重大已审阅设计 | 有价值时保留，明确标记状态 |
| `contracts/` | 代码、边界和治理的版本化规范性规则 | 使用稳定权威路径，按治理流程修改 |
| `conformance/` | 相对当前契约的临时差距及删除门槛 | 完全一致后删除详细台账 |
| `decisions/` | 已接受的架构决策记录 | 永久保留，由后续 ADR 取代旧 ADR |
| `engineering/` | 开发、质量、调试、工具、安全和发布的解释与工作指引 | 与当前工具链保持一致 |

用户可见能力和操作方法属于 `user-guide/`，不在 Developer 中复制一套能力清单。草稿、
会议记录、Agent 计划、执行日志和未经审阅的未来设计继续留在私有区域。

## Design、Contract 与 Conformance 的历史

经审阅的 Design 可以描述已发布、当前活跃或即将实现的版本。实现完成不构成删除已发布
Design 的理由；出现新设计时，由新设计明确标记对旧设计的取代关系。严重过期的内容可以
退出主导航，但公开目录不再按版本或归档状态继续拆分。

同一契约作用域只有一份位于稳定路径的当前权威文档。契约历史通过 Git 和 ADR 追溯，
不复制成另一套平行目录。

Conformance 只保存当前差距，已经关闭的条目立即移除。当某份契约的全部差距关闭且精确
基线清零后，删除详细台账和基线，在一致性索引中把该契约标记为 `Conformant`，永久
Scanner 或架构测试继续以 deny-all 模式运行。历史执行进度留在 Git 和 Pull Request，
不建立公开归档。

## 语言与导航对等

每篇公开英文 Markdown 都必须在 `docs/zh/` 下存在相同相对路径的简体中文版本，反向
亦然。两种语言在同一改动中更新，并保持含义一致。

VitePress 的两种语言使用同一读者模型：

1. 首页；
2. 世界观与故事；
3. 用户指南；
4. 开发者文档，其中包含当前架构、设计与治理、工程实践三个板块。

导航标题可以自然翻译，但必须指向镜像的文档分类，不能产生第二套所有权模型。

## 结构变更流程

现有分类内的普通页面修改和新增页面不改变本契约。修改顶级分区、Developer 分类、分类
含义、语言镜像规则或文档生命周期时，必须同时满足：

1. 新建并接受一份双语 ADR；
2. 同步升级本契约的中英文版本；
3. 更新对应的 `docs/AGENTS.md` 指引；
4. 更新 VitePress 导航；
5. 更新聚焦的文档结构测试；
6. 更新 Contract Registry 并经过负责人审查。

这属于治理变更，不得与生产源码变更混在一起。

## 强制执行

文档结构架构测试检查公开分区、Developer 根目录和分类布局、中英文 Markdown 镜像、
禁止恢复的旧路径以及必要导航路径。VitePress 构建验证最终公开站点能够正常渲染。
人工审查继续负责翻译语义质量，以及一篇内容是否真正属于所选分类。
