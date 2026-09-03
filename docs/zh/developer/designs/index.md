# 设计文档

设计文档保存已经确认的跨版本目标。它不表示当前源码已经符合设计；规范性规则仍以
[架构契约](../contracts/)为准，当前差距仍由[一致性台账](../conformance/)跟踪。

全局系统设计是独立的上级设计。本次整理不移动也不替代它。特别是，[Elfie 顶级模块设计](./elfie/elfie-top-level-module-design)
只描述 Elfie 模块本身，不是全局系统设计。物理目录按需创建：只有某个所有者拥有多篇文档时
才建立目录。本页只是目录页，不是另一篇上级设计。

- App 设计：
  - [服务生命周期状态机设计](./app/service-lifecycle-state-machine)：服务状态、入口、进程所有权和故障收敛。
  - [原生发布验证与安装版核心用户旅程](./app/native-release-validation)：安装包、生命周期和安装版产品验收。
- Infrastructure 单篇设计：
  - [Provider 与 Endpoint 模型可用性](./provider-model-availability)：精选模型加载、在用范围、证据与健康投影。
- Elfie 设计：
  - [Elfie 顶级模块设计](./elfie/elfie-top-level-module-design)：一只完整 Elfie 的模块所有权、
    生命系统和边界。
  - Brain 父级与系统：
    - [Brain 十系统架构](./elfie/brain/elfie-brain-ten-system-architecture)：十个概念系统、边界、运行回路和实现顺序。
    - [Reasoning Core](./elfie/brain/elfie-reasoning-core)：有界单 Turn 认知循环。
    - [Selfhood 与固定模型头部](./elfie/brain/elfie-selfhood-and-fixed-model-header)：Selfhood authority 与在线模型固定前缀。
    - [Emotion 情绪系统](./elfie/brain/elfie-emotion-system)：情绪状态、动态和边界。
    - [Memory 架构](./elfie/brain/elfie-memory-architecture)：持久经历、知识和召回。
    - [Brain 评价与进化系统](./elfie/brain/elfie-brain-evaluation-system)：证据优先的评价和受约束改进。
  - Embodiment 设计：
    - [具身控制链路设计](./elfie/embodiment/elfie-embodied-control-chain)：Brain 到身体的语义指令链路、
      Godot/物理设备两条执行路径及其边界。
    - [Godot 虚拟身体端到端执行计划](./elfie/embodiment/elfie-godot-vertical-slice-plan)：动作、感知和
      下一轮 Brain 反馈的渐进打通计划。
    - [虚拟外貌生成最终设计](./elfie/embodiment/virtual-appearance-generation)：不可变外貌生成与视觉验收边界。
- Nest 单篇设计：
  - [Nest 与 Godot 虚拟生活世界](./nest-godot-virtual-world-functional-architecture)：
    Nest/Godot 的最终功能边界、语义—物理闭环和事件路由。
