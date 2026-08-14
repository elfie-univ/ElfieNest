# ElfieNest 私有知识索引

本目录只保存仍在讨论或尚未公开的产品、架构与世界观知识，不代表当前代码已经实现。
读取具体材料前，必须先判断当前任务是否满足对应的 `read_when` 条件。

## 架构设计

### Elfie 整体故事、生命形态与功能体系

- file: `../../docs/.internal/elfie-overall-story-and-functional-system.md`
- status: `review-baseline`
- read_when:
  - 讨论 Elfie 是什么、怎样生活、领养前后生命周期或单机/联网故事；
  - 讨论两条对外线路、虚拟/实体身体互斥、三类大脑输入或顶级系统边界；
  - 重新审查 Elfie 的总体功能体系、MVP 范围、Profile 定位或总体守恒规则；
  - 开始设计 Brain、Nervous System、Body、Communication、Profile 或初始化流程前。
- do_not_read_when:
  - 只需要依据当前代码和测试判断已实现行为的任务；
  - 与 Elfie 产品故事、生命形态和总体架构无关的局部任务。

### Nest 与 Godot 虚拟生活世界设计

- file: `../../docs/.internal/nest-godot-virtual-world-functional-architecture.md`
- status: `review-baseline`
- read_when:
  - 讨论 Nest 四个功能模块、公共事件/广播机制或 Nest Facade；
  - 设计或迁移直接身体、语义行动、结构化视觉、虚拟听觉、环境控制等 Godot 语义线路；
  - 审查 Elfie、Nest、Godot、App 的事实 authority、事件目标、cause ID 或恢复边界；
  - 细化 Nest–Godot 规约、Conformance 条目或后续纵向迁移切片前。
- do_not_read_when:
  - 只需要判断当前 Godot 渲染结果、资产或单个脚本行为；
  - 与 Nest 世界语义、Godot 边界和事件路由无关的局部任务。

### Elfie 大脑十三系统历史扩展稿

- file: `architecture/elfie-brain-system-design.md`
- status: `historical-expanded-reference`
- read_when:
  - 十系统基线需要追溯历史上的详细状态机、治理、预算、Activity 或恢复风险；
  - 对抗审查需要确认十系统收敛时是否遗漏扩展稿中的关键能力。
- do_not_read_when:
  - 初次了解当前 Brain 架构，应优先读取十系统基线；
  - 不需要历史设计细节的普通实现和产品任务。
