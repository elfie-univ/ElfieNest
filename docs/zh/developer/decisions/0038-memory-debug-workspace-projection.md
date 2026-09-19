# ADR-0038：Memory Debug Workspace 是只读的 Brain 开发者投影

- **状态：** accepted
- **日期：** 2026-09-19
- **范围：** Memory Debug Workspace 的设计归位与 authority 边界

## 背景

Memory Debug Workspace 需要一篇稳定的公开设计文档，用来说明全库视图、Episode 处理、Recall
解释和 Elfie Lab 联动。它是开发者调试界面，不是新的 Memory 子系统，也不替代现有的 Memory
与 Reasoning 设计。

## 决策

设计文档继续放在 `docs/zh/developer/designs/elfie/brain/`，与其他 Brain 设计保持同一链路，
并维护英文镜像。Workspace 是由 Developer Tools 提供的只读投影：

- Memory 继续拥有持久 Episode、Evidence、Node、Assertion 和 Recall 选择事实；
- Elfie Lab 继续拥有 Brain Turn、Prompt Context 和最终上下文顺序；
- Workspace 可以展示已经观测到的操作与 Recall 过程，但不能成为第二个 Memory 存储，也不能
  推断缺失的观测；
- 生产数据查看保持只读；添加 Episode 的实验必须使用隔离或 dry-run 边界。

文档架构测试显式登记新的 Brain 设计。这只是扩展设计目录，不改变系统所有权、依赖方向或运行时
authority。

## 后果

开发者有一个稳定入口理解三个调试问题：库里有什么、Episode 如何影响 Memory、Recall 为什么
返回这些结果。以后修改页面时必须继续遵守 source-first 和单一 authority 边界。

## 否决方案

- 把 Workspace 做成第二个 Memory 实现或持久化 authority；
- 把设计放到泛化的 Developer Tools 目录而切断 Brain 设计链；
- 仅凭 Memory Debug 页面声称 Prompt Context 的最终顺序。
