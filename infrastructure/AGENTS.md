# 根 Infrastructure 执行规则

本目录实现 App Feature/Orchestration 与领域 Core 所定义的出站 Port，并拥有持久化、
文件、网络、模型平台、Godot、设备、通信和操作系统等技术 Adapter。

- 可以依赖它所实现的公开 Port/Model，不能依赖 Interface、Bootstrap 或 Feature 私有
  Service/helper，也不能承载产品授权和用例流程。
- 按技术能力和事实源组织，不要求逐目录镜像 Feature；一个 Adapter 只能实现明确的
  消费方契约，不能扩张成第二套业务 API。
- 各能力包不得导入或构造其他能力包的具体 Adapter；需要其他能力时依赖窄 Port 或
  共享技术模型，由 Bootstrap 注入具体实现。
- 技术 Record、SDK 对象、SQLite Row 和设备帧只留在 Adapter 内，进入 Port 前映射为
  由消费方拥有的严格模型。
- 全局配置的路径解析、文档解码与已声明合并策略只在 Infrastructure 配置 Adapter 中
  实现；生产入口只接受注册文档 ID 和固定相对路径，不暴露任意路径、点分键或通用
  嵌套字典 API。测试与开发工具可以注入隔离沙箱根，但必须复用同一注册文档和解析器，
  且不得默认读取生产 `ELFIE_HOME`。
- Infrastructure 异常在边界翻译为稳定技术失败，不把供应商、数据库或文件异常原样
  泄漏给 Interface。
- 持久化、设备、Godot 等子目录的 `AGENTS.md` 可继续细化，但不能改变上述依赖方向。
