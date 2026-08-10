# Account Feature 执行规则

本目录拥有账户、登录会话、角色、密码策略和成员自身身份用例，继承
`app/features/AGENTS.md`。

- Interface 只验证凭据并构造严格 `Principal` / `RequestContext`；本 Feature 根据
  用例和资源关系授权，禁止依赖前端隐藏、URL 名称或调用方提交的任意 `user_id`。
- Session TTL、密码策略、Rate Limit 和角色规则使用强类型配置 Port；不得读取 YAML、
  解析数据根、导入 FastAPI 或直接构造 Repository。
- 密码、Token、Session Secret 和完整凭据不进入普通 DTO、日志、缓存或错误消息。
- 账户和 Session 的原子变更由明确事务/UoW Port 完成；公开门面使用稳定业务错误，
  Interface 再映射协议状态。
