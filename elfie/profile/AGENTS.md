# Elfie Profile 执行规则

本目录拥有稳定身份、物种、外貌、人格、能力、限制、来源及随源码发布的不可变默认
资源，并定义读取/保存已校验 Profile 所需的窄 Port。

- 领域模型不得包含文件路径、YAML 文档、账户、领养流程或产品数据根。
- 随源码发布的只读默认资源可以保留；用户可变 YAML/文件持久化、路径解析和具体
  Repository 属于 `ELF-005` 迁移债务，目标位置是 Infrastructure。
- Profile 只描述一只 Elfie；账户所有权、领养授权和跨 Elfie 查询属于 App Feature。
- 新增或修改 Profile 边界时使用命名强类型模型和 Fake Store；不得新增 fallback read、
  双写、字段 alias 或兼容 Repository，除非用户明确批准过渡方案与删除门槛。
