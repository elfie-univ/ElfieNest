# 开发者文档

Developer 文档按“先理解、再修改、最后交付”的顺序组织。每一篇只负责一个问题，
代码与测试是当前事实来源。

## 先理解系统

- [当前架构](./architecture/)：系统全景、核心调用链和进程边界。
- [架构契约](./contracts/)：长期保留的规范性规则。
- [仓库架构治理](./contracts/repository-governance)：契约、ADR、本地 Agent 规约、
  Scanner、基线和 CI 如何组成一套可执行的质量闭环。
- [系统架构契约](./contracts/system)：四大目标模块、系统级 Ports/Adapters 和迁移方向。
- [系统架构一致性台账](./conformance/system)：根模块和技术边界的临时迁移台账。
- [应用架构契约](./contracts/application)：`app/` 新增和已迁移代码的所有权、
  依赖方向、Port/Adapter 和组合根规范。
- [应用架构一致性台账](./conformance/application)：当前 App 架构债务的临时台账和
  精确删除门。
- [模块边界](./architecture/module-boundaries)：每个根模块负责什么、不负责什么。
- [认知信息流](./architecture/cognitive-flow)：从感知输入到执行回执的类型化流程。
- [运行时与数据](./architecture/runtime)：配置、数据、服务和构建产物如何隔离。
- [架构决策](./decisions/)：长期架构变更的已接受原因。

## 再开始修改

- [开发流程](./development)：环境、分支、最小变更和本地工作顺序。
- [测试与质量](./testing)：测试层级、质量基线、pre-commit 与 CI。
- [调试与实验台](./debugging)：Elfie Lab、Nest Lab、Runtime Lab 的用途和隔离方式。

## 最后验证与交付

- [命令参考](./tooling)：统一 CLI、服务、数据和诊断命令。
- [Developer Tools](./devtools)：三个模块实验台的入口和适用场景。
- [Godot](./godot)：场景、空间、角色、Web Runtime 的所有权和检查流程。
- [Desktop](./desktop)：Electron 宿主、资源发现和进程监督边界。
- [构建与发布](./build-release)：构建目录、发布物、文档站和人工审阅门。

## 协作规则

- [代码规范与约束](./standards)：目录边界、Python 类型、测试和文档写法。
- [安全与数据边界](./security-data)：生产数据、密钥、私有材料和公开站点的隔离。

## 文档规则

Developer 文档只收录最终、可核验、能够帮助别人完成工作的内容。讨论记录、模型
中间稿、未实现方案和私有世界观不进入公开侧栏；关键设计文章需要独立主题、代码
证据和负责人审阅。
