# ElfieNest 私有知识索引

本目录只保存仍在讨论或尚未公开的产品、架构与世界观知识，不代表当前代码已经实现。
读取具体材料前，必须先判断当前任务是否满足对应的 `read_when` 条件。

## 架构设计

### Elfie 三阶段产品交付路线

- file: `../../docs/.internal/elfie-product-delivery-stages.md`
- status: `discussion-baseline`
- read_when:
  - 讨论 ElfieNest 的顶层产品阶段、首个聊天交付、虚拟精灵巢生活或现实身体路线；
  - 规划第一阶段身份、领养前历史、主人共同经历与认知边界的纵向实现；
  - 规划第二阶段真实具身、日常生活、自主活动、多精灵社会或受控成长；
  - 为上述任一产品子阶段创建实现工作卡或用户可感知验收场景前。
- do_not_read_when:
  - 只需要判断当前源码行为、局部修复或运行故障；
  - 与产品交付阶段、聊天体验、虚拟生活或现实具身无关的任务。

### Elfie 第一阶段记忆支撑聊天闭环执行计划

- file: `../../docs/.internal/elfie-stage1-memory-backed-chat-execution-plan.md`
- status: `e1-deterministic-pass-real-model-blocked`
- read_when:
  - 实施或审查第一阶段稳定聊天、异星知识、领养前传记、主人事实或完整聊天验收；
  - 修改 Genesis Memory seed、Memory 类型化检索、Reasoning 记忆上下文或聊天回执/写回语义；
  - 评估 Canon 与 Memory 的事实分工、旧 Elfie 数据策略或第一阶段 P0 优先顺序；
  - 为第一阶段任一轮建立具体工作卡、失败测试和纵向验收场景前。
- do_not_read_when:
  - 只讨论第二阶段 Nest/Godot 真实生活或第三阶段实体身体；
  - 与第一阶段聊天、记忆、Genesis、Reasoning 或 Communication 无关的局部任务。

### Elfie Brain 评价体系与自动化试验场

- file: `../../docs/.internal/elfie-brain-evaluation-system.md`
- status: `evaluation-baseline-design`
- read_when:
  - 设计或审查 Brain 修改的基线/候选对比、确定性红线、真实模型评测或人工体验验收；
  - 建立 EvalRun、EvalScenario、回归场景、模型裁判、长时间试验或候选晋级规则；
  - 为第一阶段 `E1–E5` 之外的 Brain/Nest/具身能力建立统一评测方法。
- do_not_read_when:
  - 只需执行第一阶段聊天某一轮的既定专项题库和门禁，此时直接读上面的执行计划；
  - 与 Brain 行为质量、回归或晋级无关的局部实现任务。

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
