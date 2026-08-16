# 开发者文档

Developer 文档按“先理解、再修改、最后交付”的顺序组织。每一篇只负责一个问题，
代码与测试是当前事实来源。

## 当前架构

- [当前架构](./architecture/)：系统全景、核心调用链和进程边界。
- [模块边界](./architecture/module-boundaries)：每个根模块负责什么、不负责什么。
- [认知信息流](./architecture/cognitive-flow)：从感知输入到执行回执的类型化流程。
- [运行时与数据](./architecture/runtime)：配置、数据、服务和构建产物如何隔离。

## 设计与治理

- [设计文档](./designs/)：已经确认的跨版本目标、系统边界和未来实现方向。
- [Elfie 顶级模块设计](./designs/elfie-top-level-module-design)：一只完整 Elfie 的目标
  一级所有权。
- [Elfie 大脑十系统架构](./designs/elfie-brain-ten-system-architecture)：Brain 的概念系统、
  运行关系和渐进实现顺序。
- [服务生命周期状态机设计](./designs/service-lifecycle-state-machine)：服务稳定层级、入口、
  进程所有权和收敛。
- [Provider 与 Endpoint 模型可用性](./designs/provider-model-availability)：精选模型加载、
  在用核心范围和节省资源的健康证据。
- [架构契约](./contracts/)：长期保留的规范性规则。
- [仓库架构治理](./contracts/repository-governance)：契约、ADR、本地 Agent 规约、
  Scanner、基线和 CI 如何组成一套可执行的质量闭环。
- [文档结构契约](./contracts/documentation-structure)：公开分区、Developer 文档分类和
  双语结构规则。
- [系统架构契约](./contracts/system)：四大目标模块、系统级 Ports/Adapters 和迁移方向。
- [服务生命周期契约](./contracts/service-lifecycle)：Runtime 状态、入口语义和受管进程的
  规范性不变量。
- [Elfie 内部架构契约](./contracts/elfie)：一只 Elfie 的聚合、生命系统与 Port 所有权边界。
- [Elfie Brain 内部架构契约](./contracts/brain)：Turn、思考、心智状态与跨回合活动所有权。
- [Elfie 一致性](./conformance/elfie)：主体级生命系统迁移的收口证据，等待独立治理删除。
  Brain 已完成一致性收口，其契约由永久架构测试守护。
- [应用架构契约](./contracts/application)：`app/` 新增和已迁移代码的所有权、
  依赖方向、Port/Adapter 和组合根规范。
- [服务生命周期一致性](./conformance/service-lifecycle)：已接受契约与当前实现之间的开放缺口。
- [架构决策记录（ADR）](./decisions/)：长期架构变更的已接受原因。

## 工程实践

- [仓库质量治理](./engineering/quality-governance)：契约、Agent 指引、机器检查、
  质量棘轮和人工审查怎样共同保护仓库。
- [开发流程](./engineering/development)：环境、分支、最小变更和本地工作顺序。
- [测试与质量](./engineering/testing)：测试层级、质量基线、pre-commit 与 CI。
- [调试与实验台](./engineering/debugging)：Elfie Lab、Nest Lab 的用途和隔离方式。
- [命令参考](./engineering/tooling)：统一 CLI、服务、数据和诊断命令。
- [Developer Tools](./engineering/devtools)：两个模块实验台的入口和适用场景。
- [Godot](./engineering/godot)：场景、空间、角色、Web Runtime 的所有权和检查流程。
- [Desktop](./engineering/desktop)：Electron 宿主、资源发现和进程监督边界。
- [代码规范与约束](./engineering/standards)：目录边界、Python 类型、测试和文档写法。
- [安全与数据边界](./engineering/security-data)：生产数据、密钥、私有材料和公开站点的隔离。
- [构建与发布](./engineering/build-release)：构建目录、发布物、文档站和人工审阅门。

## 文档规则

Developer 文档只收录最终、可核验、能够帮助别人完成工作的内容。讨论记录、模型
中间稿、未实现方案和私有世界观不进入公开侧栏；关键设计文章需要独立主题、代码
证据和负责人审阅。
