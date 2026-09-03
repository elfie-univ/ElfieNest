# Elfie Profile 执行规则

本目录只拥有外部可见且创建后不可变的客观档案：稳定身份、年龄/出生锚点、个人出身
标识/名称、最终虚拟外貌、技术 Schema revision，以及随源码发布的不可变外貌默认资源；
并定义读取/保存已校验 Profile 所需的窄 Port。

- Profile 回答“客观上是哪一只 Elfie”；可变化的 Self Model、人格、兴趣和规范属于
  Brain Selfhood，记忆和人物关系属于 Brain Memory。
- Profile 不是创建账本或世界百科。禁止加入 Canon/资料包引用、世界描述或知识、生成器/
  模型/策略版本、Seed、用户问卷/选项、抵达/培训/领养事件、人物关系或完整传记。
- 身体能力属于 Body/NervousSystem，认知能力、Tool/模型权限与预算属于 Brain 的能力
  边界和 Energy。`ElfieProfile` 不得重新增加 `personality`、`capabilities`、
  `system_limits` 宽字段；Brain seed 与能量限制必须由对应 owner 持有。

- 领域模型不得包含文件路径、YAML 文档、账户、领养流程或产品数据根。
- 随源码发布的只读外貌默认资源可以保留；用户可变 YAML/文件持久化、路径解析和具体
  Repository 只属于 Infrastructure，不得恢复到 Profile。
- Profile 只描述一只 Elfie；账户所有权、领养授权和跨 Elfie 查询属于 App Feature。
- Profile 与 Selfhood 是 Genesis 共同校验后并列提交的终态，不在运行期互相派生、投影、
  刷新或同步。对外组合页面可以聚合多个 owner，但不能把聚合字段写回 Profile。
- 新增或修改 Profile 边界时使用命名强类型模型和 Fake Store；不得新增 fallback read、
  双写、字段 alias 或兼容 Repository，除非用户明确批准过渡方案与删除门槛。
