# Elfie Communication 执行规则

本目录拥有一只 Elfie 的数字通信语义：标准 Envelope、准入、去重、策略、Inbox、
Outbox、Hub、Router 和投递回执。渠道 Port 支持多个平台实现并发存在。

- Web、ElfieNest App、微信、钉钉、飞书等都实现同一渠道 Port；以稳定 `channel_id`
  路由，不按具体平台复制领域流程。
- 外部入站先由 Infrastructure Adapter 认证并转换原生 Payload，再由 App
  Communication Feature 解析 Principal、会话成员、目标 Elfie 与授权，最后通过
  `Elfie` Facade 投递标准 Envelope；Infrastructure 不得自行选择 Elfie 或绕过产品
  授权。没有独立进程或多实现需求时，不创建对称的入站 Protocol。
- 平台 SDK、凭据、Webhook、网络会话、传输重试和原生 Payload 映射属于
  Infrastructure。现有 `channels/` 技术实现属于 `ELF-007` 迁移债务，不得扩展。
- 产品账户、关系、会话成员和用户可见历史属于 App Communication Feature，不得写入
  Elfie Communication 作为第二 authority。
- Inbox/Outbox 只保留有界处理和投递状态，不持久化第二份产品会话历史，也不接管平台
  传输重试；Elfie Memory 可形成语义记忆，但不是 App 会话记录副本。
- 领域测试使用 Fake Channel，并覆盖多渠道并存、去重、策略与类型化回执；网络集成由
  Adapter 测试承担。
- Envelope/回执必须有稳定消息/关联身份和 `channel_id`；默认回复来源渠道，并发渠道
  之间没有隐式总顺序；平台 Sender ID 不能直接作为已认证 Principal。
