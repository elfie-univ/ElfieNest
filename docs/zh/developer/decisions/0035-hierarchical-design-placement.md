# ADR-0035：设计文档层级归位与私有资料边界

- **状态：** accepted
- **日期：** 2026-09-03
- **范围：** 私有资料与公开 Developer 设计文档的归位

## 背景

公开设计文档原来是平铺的，但系统实际上存在全局设计、四个一级模块，以及包含多篇子设计
的 Brain。私有目录也混合了世界资料、产品资料、技术目标设计和执行计划。仅凭目录名无法
让代理知道应先读哪个上级设计，也无法判断哪篇文档具有权威性。

## 决策

`docs/.internal/` 只保留三个扁平一级目录：

- `elfaria/`：Elfaria 世界与居民知识资料；
- `product/`：产品意图、故事和体验资料；
- `drafts/`：尚未定稿的领域草稿。

不新增私有代码设计、执行日志或执行报告分类。现有历史计划和技术草稿在独立治理决定
提升、退役或删除之前，统一作为迁移期间的非权威遗留资料。

公开 `designs/` 使用以下逻辑层级：

```text
全局系统设计（独立的上级设计，本决策不移动）
├── app/                         （App 拥有多篇设计后建立）
├── infrastructure/              （Infrastructure 拥有多篇设计后建立）
├── elfie/
│   ├── elfie-top-level-module-design.md  （仅 Elfie 模块设计）
│   └── brain/                    （Brain 拥有多篇设计，已经建立）
└── nest-godot-virtual-world-functional-architecture.md  （Nest 单篇设计）
```

全局系统设计仍是独立的上级设计，本决策不移动它，也不为它指定新的公开路径。
`designs/elfie/elfie-top-level-module-design.md` 只是 Elfie 模块的顶级设计；
它的下级是 Brain、Embodiment、Communication 和 Genesis，不是 App、Infrastructure
或 Nest。Nest/Godot 设计是公开 `designs/` 根下的单篇文档，因此暂不建立
`nest/` 目录。物理目录按需创建：只有某个所有者拥有多篇文档时才建立目录，
不要求每个目录都有 `index.md`。`designs/index.md` 继续作为目录页，实际设计文档
通过上级、下级、契约、当前架构、一致性和领域来源引用表达关系。

Selfhood 属于 Brain，因为它是 Brain 第 3 个系统。Skill 和 Tool 是 Reasoning Core 的
阶段性能力，不是额外的 Brain 系统。

Product 与 Elfaria 是领域资料源，不是实现设计。Genesis 设计负责把这些资料编译为 Elfie
各 owner 的初始状态。允许建立交叉引用，但权威不能循环：公开页面使用稳定的资料标识，
不直接链接站点排除的 `.internal` 路径。

## 后果

代理修改局部设计时，必须先阅读上级设计链。移动文档不改写设计含义，只改变路径并补充明确
关系。作用域内 `AGENTS.md`、双语治理文档、导航和文档架构测试共同执行这套结构。

## 否决方案

- 把 Elfie 顶级模块设计当成全局系统设计的上级；
- 为每个模块或子模块添加 `index.md`；
- 预先创建空的 `app`、`infrastructure`、`nest`、`embodiment` 或 `communication` 目录；
- 继续把私有代码设计或执行历史保留为第二套权威目录。
