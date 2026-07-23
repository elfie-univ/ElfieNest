# 开发者文档

这里面向准备阅读源码、运行测试、调试模块或参与 ElfieNest 建设的人。公开
Developer 文档只保留经过当前代码验证的最终说明，不把历史设计过程自动发布。

## 选择你的路线

### [当前架构](./architecture.md)

先理解 `elfie`、`nest`、`ai_runtime`、`app`、`desktop` 与 `godot` 的职责，
以及类型化认知信息流、进程边界、数据和产物边界。

适合：第一次进入代码库、准备改跨模块流程，或需要判断一段代码应放在哪里。

### [开发流程](./development.md)

从锁定环境、聚焦测试、架构测试和统一质量门，一直走到提交前检查；同时说明三个
隔离实验台和常见环境问题。

适合：准备开始写代码、修测试或验证一组改动。

### [命令与开发工具](./tooling.md)

查询当前 CLI、数据与高风险命令、Godot Web 构建、Desktop 工具链，以及 Elfie
Lab、Nest Lab、Runtime Lab 的真实入口。

适合：已经知道要做什么，正在寻找可执行命令。

## 开发前先知道

1. 阅读根 [AGENTS.md](https://github.com/elfie-univ/ElfieNest/blob/main/AGENTS.md)，
   了解目录边界、安全门和文档语言规则；
2. 阅读改动模块自己的 README，不从历史设计稿猜当前职责；
3. 先运行最接近改动的测试，再扩大到 `test/architecture/`；
4. 为测试和实验设置独立 `ELFIE_HOME`；
5. 新增目录或跨边界依赖时，同步更新 README、架构文档和架构测试。

项目级协作流程见
[贡献指南](https://github.com/elfie-univ/ElfieNest/blob/main/CONTRIBUTING.md)，
漏洞与密钥处理见
[安全策略](https://github.com/elfie-univ/ElfieNest/blob/main/SECURITY.md)。

## 关键设计文章如何进入文档

Developer 侧栏不会保存每一次讨论或大模型生成的中间稿。一篇关键设计文章只有
同时满足以下条件才会加入：

- 描述的是当前事实，而不是尚未落地的路线图；
- 主题足够独立，不能被模块 README 或现有架构页清楚覆盖；
- 能定位到当前代码、测试或稳定配置；
- 已由项目负责人审阅，确认适合公开。

未满足这些条件的材料留在本机私有知识区，或在失去长期价值后废弃。这样公开
文档维护的是项目最终状态，而不是开发过程的堆积。
