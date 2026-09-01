# 设计文档

设计文档保存已经确认的跨版本目标与未来架构背后的思考。它可以同时覆盖已经完成和
尚未完成的版本，但不表示当前源码已经符合设计。规范性约束仍以[架构契约](../contracts/)
为准，当前实现差距仍由[一致性台账](../conformance/)跟踪。

- [Elfie 顶级模块设计](./elfie-top-level-module-design)：一只完整 Elfie 的目标顶级所有权。
- [Elfie 大脑十系统架构](./elfie-brain-ten-system-architecture)：Brain 的概念系统、边界、
  运行回路和渐进实现顺序。
- [Elfie Reasoning Core](./elfie-reasoning-core)：Reasoning 自有 Context Workspace、
  Context/Memory 边界、有界单 Turn Agent 循环、压缩、完成判断和 P0 无工具主人聊天范围。
- [Elfie Selfhood 与固定模型头部](./elfie-selfhood-and-fixed-model-header)：在线 Reasoning
  四段前缀、两层 Selfhood 状态、初始化、投影、持久化与未来 Memory-only 更新边界。
- [Elfie 情绪系统](./elfie-emotion-system)：六通道正负动态、稳定/快速/复核 Turn
  生命周期、人格投影与模态边界。
- [Elfie Brain 评价与进化系统](./elfie-brain-evaluation-system)：面向一只完整、连续生活
  Elfie 的 Quality Constitution、Q6/P0 证据协议、统计决策和安全持续改进闭环。
- [Elfie Memory 架构](./elfie-memory-architecture)：经历记忆、个人知识图谱与图谱/文本混合检索。
- [ElfieNest 服务生命周期状态机设计](./service-lifecycle-state-machine)：服务稳定态、
  入口行为、进程所有权与故障收敛。
- [Provider 与 Endpoint 模型可用性](./provider-model-availability)：精选模型加载、在用核心
  范围、低成本证据与统一健康投影。
- [虚拟外貌生成最终设计](./virtual-appearance-generation)：一只 Elfie 的几何输入、四层皮肤、
  语义区域、颜色体系和视觉验收门。
- [原生发布验证与安装版核心用户旅程](./native-release-validation)：六层测试体系、确定性 CI
  模型边界、四 target 覆盖、成本控制和分阶段收口计划。
