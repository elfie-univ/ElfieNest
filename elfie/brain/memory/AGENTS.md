# Elfie Memory 执行规则

本目录拥有记忆节点、关系、编码、检索、巩固和语义搜索算法，并定义这些算法实际需要
的窄存储 Port。

- 领域模型不得表达 SQL Row、表名、连接、文件路径或序列化格式；元数据逐步收紧为
  命名强类型模型。
- 禁止新增 SQLite、SQL、数据根解析、Schema 管理或具体 Repository；这些技术实现只
  属于 Infrastructure Adapter，不得恢复到 Memory。
- Memory 不选择全局数据库，不查询其他 Elfie，也不通过 App Orchestration 代理普通
  读写；Bootstrap 注入按单只 Elfie 限定的 `MemoryStorePort`。
- 算法测试使用 Fake/in-memory Port；持久化事务、迁移与 Record 映射测试放在最终
  Infrastructure Adapter 对应测试目录。
