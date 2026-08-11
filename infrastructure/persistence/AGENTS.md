# 持久化目录规则

本文件只作用于根 `infrastructure/persistence/`。

- 持久化类是 Feature、Orchestration 或领域 Core 出站 Port 的具体 Adapter，不拥有
  产品授权、业务流程或协议 DTO。持久化 Record 只在 Adapter 内部使用，不能作为 API
  响应或跨层通用模型。
- SQL 只能存在于持久化层；API 和业务层不得直接执行 SQL。路径只能通过统一 resolver
  获取，不得在 Repository 中自行拼接新的数据根。
- 多步写用例的事务由显式 Unit of Work 拥有；Repository 方法不得在调用方仍需继续
  原子修改时隐藏 `commit`。数据库事务内不得等待网络、模型、Godot 或设备响应。
- 查询 Adapter 只读取权威事实或明确派生投影，不在读取过程中偷偷写入、修复或迁移
  数据。新建索引、缓存表或投影时必须声明权威源与重建方式。
- 生产数据唯一根为 `${ELFIE_HOME:-~/.elfienest}`。根级 `nest.db` 只保存 Nest 身份、
  账号/归属、运行与房间状态。
- 每只精灵使用稳定 `elfie_id` 的 `elfies/<elfie_id>/` 工作区；聊天唯一事实源为
  `conversations/history.sqlite`。名称不能参与目录寻址。
- 不创建 `users/` 聊天目录，不在 Nest 根保留新的聊天副本；禁止创建、读取、写入或
  迁移已废弃的 `nest.db.chat_messages`。
- Developer Tools 默认根为 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，其下分别保存
  `elfie_lab/`、`nest_lab/`、`runtime_lab/`，不得读写生产 `ELFIE_HOME`。
- 新增永久数据路径必须通过 `infrastructure.persistence.data_home` resolver；不得在
  局部任务中复制第二套路径规则、环境变量解析或数据布局。
- MVP 阶段默认更新当前调用方并删除旧实现；未经用户明确批准，不新增 migration、
  fallback read、dual write、旧字段 alias、兼容 Repository 或长期兼容壳。
