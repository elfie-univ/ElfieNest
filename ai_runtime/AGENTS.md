# AI Runtime 历史迁移边界规则

本目录是当前模型、Food、工具和报告实现的历史混合路径。目标所有权以
[`System architecture contract`](../docs/developer/contracts/system.md) 为权威；旧
[`AI Runtime design contract`](../docs/developer/contracts/ai-runtime.md) 只保留当前行为
清单作用，不能定义目标模块。

- 不创建目标 `infrastructure/ai_runtime/`，也不把本目录整体移动。
- Provider 目录/发现、连接协议、模型列表、技术探测和模型调用目标进入
  `infrastructure/models/`；Provider 连接管理和凭据引用进入 App Feature；搜索、文件
  和沙箱执行进入 `infrastructure/tools/`；存储实现进入持久化 Adapter。
- Food 管理、自动生成和管理报告进入 App Feature；Elfie 通过自有 Food/模型/工具
  Port 直接使用能力，不经过 App Orchestration。
- App Feature 写入 Food 可见性、授权、分配和选择；持久化 Adapter 只按这些事实解析
  指定 Elfie 的有效投影，不重新作出授权决策，也不代理 `ModelPort`。
- 模型验证和提醒的调度策略进入 App Feature，通过 Scheduler/Runner Port 执行，不进入
  Runtime 进程 lifecycle。
- 当前目录只允许在获批迁移切片中维护或收缩；禁止新增永久所有权、兼容壳或第二事实源。
