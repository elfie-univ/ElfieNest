# ElfieNest 私有知识索引

本目录只保存仍在讨论或尚未公开的产品、架构与世界观知识，不代表当前代码已经实现。
读取具体材料前，必须先判断当前任务是否满足对应的 `read_when` 条件。

## 架构设计

### Elfie 大脑完整系统设计

- file: `architecture/elfie-brain-system-design.md`
- status: `architecture-baseline`
- read_when:
  - 讨论或设计 Elfie 大脑整体架构；
  - 讨论三类事件来源、认知回合或聊天与身体行为隔离；
  - 讨论情绪、记忆、能量、工作空间或大脑皮层；
  - 讨论 Elfie 作为独立具身智慧体、人格、自我模型、动机或驱力；
  - 讨论自主治理、能力边界、资源预算或为什么不做逐操作人工批准；
  - 讨论 ReAct、Skills、Cortical Agent、Worker 或 Sub-Agent；
  - 讨论 Activity、内部任务、调度、派生任务或主动行为；
  - 讨论睡眠、夜间整理、记忆巩固、离线认知或反思系统。
- do_not_read_when:
  - 与大脑系统无关的局部代码、UI、安装、打包或普通运维任务；
  - 只需要依据当前代码和测试判断已实现行为的任务。
