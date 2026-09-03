# 持久化目录规则

本文件只作用于根 `infrastructure/persistence/`。

- 持久化类是 Feature、Orchestration 或领域 Core 出站 Port 的具体 Adapter，不拥有
  产品授权、业务流程或协议 DTO。持久化 Record 只在 Adapter 内部使用，不能作为 API
  响应或跨层通用模型。
- Profile、Selfhood、Memory 与领养事务的 Adapter 只保存调用方已经生成并校验的强类型
  结果。禁止在 `materialize`、Repository 或配置 Loader 中选择个人知识、生成关系/经历、
  推导人格或重新解释问卷/Canon；这些语义只属于 Elfie Genesis。
- SQL 只能存在于持久化层；API 和业务层不得直接执行 SQL。路径只能通过统一 resolver
  获取，不得在 Repository 中自行拼接新的数据根。
- 多步写用例的事务由显式 Unit of Work 拥有；Repository 方法不得在调用方仍需继续
  原子修改时隐藏 `commit`。数据库事务内不得等待网络、模型、Godot 或设备响应。
- 查询 Adapter 只读取权威事实或明确派生投影，不在读取过程中偷偷写入、修复或迁移
  数据。新建索引、缓存表或投影时必须声明权威源与重建方式。
- 生产数据唯一根为 `${ELFIE_HOME:-~/.elfienest}`。根级 `nest.db` 只保存 Nest 身份、
  账号/归属、运行与房间状态。
- `${ELFIE_HOME}/configs/` 是唯一可写全局配置根；仓库 `config/` 和安装态
  `resources/config/` 只读。首次运行只创建目录，不复制默认文档；用户写入使用同目录
  原子替换，读取不得顺手修复、迁移或覆盖用户文件。
- 每只精灵使用稳定 `elfie_id` 的 `elfies/<elfie_id>/` 工作区；聊天唯一事实源为
  `conversations/history.sqlite`。名称不能参与目录寻址。
- 不创建 `users/` 聊天目录，不在 Nest 根保留新的聊天副本；禁止创建、读取、写入或
  迁移已废弃的 `nest.db.chat_messages`。
- Developer Tools 默认根为 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，其下分别保存
  `elfie_lab/`、`nest_lab/`，不得读写生产 `ELFIE_HOME`。
- 新增永久数据路径必须通过 `infrastructure.persistence.layout.data_home` resolver；不得在
  局部任务中复制第二套路径规则、环境变量解析或数据布局。
- 0.x 首版阶段默认更新当前调用方并删除旧实现；未经用户明确批准，不新增 migration、
  fallback read、dual write、旧字段 alias、兼容 Repository 或长期兼容壳。

## 数据库变更门禁

数据库不是普通实现细节。任何表、字段、索引、约束、触发器、事务语义或持久化 SQL
变化，都必须先按高风险数据库变更审查；没有完成审查，不得修改生产实现。

- 先区分数据类型：临时表单、会话状态、生成中间物和重试信息不得写入最终业务表；最终
  表只保存已经完成、可被上层当作事实使用的数据。不得用 `provisioning`、`pending`、
  `draft` 等状态把半成品伪装成最终记录。
- 先执行只读盘点：
  `uv run --no-sync python scripts/governance/persistence/scan.py --project-root . --check`。
  审查输出必须覆盖变更表、所有写入方、所有读取方、统计/容量/权限/运行时依赖、触发器、
  API/前端投影、测试夹具和数据目录；不能只看当前正在修改的 Repository。
- 每次变更必须回答：新库和已有库如何处理、是否需要显式 migration、事务边界在哪里、
  每个崩溃/重启/超时/重复请求窗口如何收束、失败如何回滚、临时文件如何清理、是否会
  影响容量/计数/权限/隐私/性能。`CREATE TABLE IF NOT EXISTS` 不得被当作 migration。
- 数据库变更与 UI、模型、运行时或大规模业务重构分开；先单独审查并验收数据库契约，
  再迁移上层调用方。一次变更不能同时新增 schema、改变最终状态语义并修改多个产品流程。
- 任何新增表、字段、索引、约束或触发器都必须说明权威所有者、直接消费者、重建方式、
  备份/回滚策略和删除条件。缓存、投影或临时存储必须声明权威源，不能成为第二事实源。
- 机器门禁失败时不得通过新增 baseline、放宽扫描器、删除测试或把临时状态改名绕过。
  当前数据库边界测试和扫描器属于治理规则，修改它们必须单独进行并经过双语 ADR 和
  人工审查。
