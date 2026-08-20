# 设计文档

设计文档保存已经确认的跨版本目标与未来架构背后的思考。它可以同时覆盖已经完成和
尚未完成的版本，但不表示当前源码已经符合设计。规范性约束仍以[架构契约](../contracts/)
为准，当前实现差距仍由[一致性台账](../conformance/)跟踪。

- [Elfie 顶级模块设计](./elfie-top-level-module-design)：一只完整 Elfie 的目标顶级所有权。
- [Elfie 大脑十系统架构](./elfie-brain-ten-system-architecture)：Brain 的概念系统、边界、
  运行回路和渐进实现顺序。
- [ElfieNest 服务生命周期状态机设计](./service-lifecycle-state-machine)：服务稳定态、
  入口行为、进程所有权与故障收敛。
- [Provider 与 Endpoint 模型可用性](./provider-model-availability)：精选模型加载、在用核心
  范围、低成本证据与统一健康投影。
- [虚拟外貌生成最终设计](./virtual-appearance-generation)：一只 Elfie 的几何输入、四层皮肤、
  语义区域、颜色体系和视觉验收门。
