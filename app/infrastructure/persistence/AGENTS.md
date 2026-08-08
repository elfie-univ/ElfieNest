# 持久化目录规则

本文件只作用于 `app/infrastructure/persistence/`。

- SQL 只能存在于持久化层；API 和业务层不得直接执行 SQL。路径只能通过统一
  resolver 获取，不得在 Repository 中自行拼接新的数据根。
- 生产数据唯一根为 `${ELFIE_HOME:-~/.elfienest}`。根级 `nest.db` 只保存 Nest
  身份、账号/归属、运行与房间状态。
- 每只精灵使用稳定 `elfie_id` 的 `elfies/<elfie_id>/` 工作区；聊天唯一事实源为
  `conversations/history.sqlite`。名称不能参与目录寻址。
- 不创建 `users/` 聊天目录，不在 Nest 根保留新的聊天副本；禁止创建、读取、写入
  或迁移已废弃的 `nest.db.chat_messages`。
- Developer Tools 默认根为 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，其下分别保存
  `elfie_lab/`、`nest_lab/`、`runtime_lab/`。它们不得读取或写入生产 `ELFIE_HOME`。
- 新增永久数据路径必须由 `ai_runtime.storage.data_home` 解析，并更新直接相关的
  architecture 契约。只有永久数据契约或开发者可见行为变化时才同步中英文文档。
- MVP 阶段默认更新当前调用方并删除旧实现；未经用户明确批准，不新增 migration、
  fallback read、dual write、旧字段 alias、兼容 Repository 或长期兼容壳。
