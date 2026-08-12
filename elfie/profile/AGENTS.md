# Elfie Profile 执行规则

本目录只拥有不可变固有身份、物种、虚拟外貌、生成来源及随源码发布的不可变外貌默认
资源，并定义读取/保存已校验 Profile 所需的窄 Port。

- Profile 回答“客观上是哪一只 Elfie”；可变化的 Self Model、人格、兴趣和规范属于
  Brain Selfhood，记忆和人物关系属于 Brain Memory。
- 身体能力属于 Body/NervousSystem，认知能力、Tool/模型权限与预算属于 Brain 的能力
  边界和 Energy。当前 `personality`、`capabilities`、`system_limits` 宽字段及对应默认
  YAML 属于 `ELF-010` 迁移债务，不得扩展或增加新的调用方。

- 领域模型不得包含文件路径、YAML 文档、账户、领养流程或产品数据根。
- 随源码发布的只读外貌默认资源可以保留；用户可变 YAML/文件持久化、路径解析和具体
  Repository 只属于 Infrastructure，不得恢复到 Profile。
- Profile 只描述一只 Elfie；账户所有权、领养授权和跨 Elfie 查询属于 App Feature。
- 新增或修改 Profile 边界时使用命名强类型模型和 Fake Store；不得新增 fallback read、
  双写、字段 alias 或兼容 Repository，除非用户明确批准过渡方案与删除门槛。
