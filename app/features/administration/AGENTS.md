# Administration Feature 执行规则

本目录拥有家庭管理员对成员、系统状态和维护操作的产品用例，继承
`app/features/AGENTS.md`。

- 每个管理员用例显式要求 admin Principal；路径前缀、前端按钮或登录状态本身不构成
  管理权限。
- 备份、重置、Session 撤销、成员修改等破坏性操作使用明确 Command、审计上下文和
  事务/任务 Port；不得由 Route 直接访问数据库或进程。
- 系统健康只报告技术可运行性；未领养、未分配床位等业务积压进入事件或业务投影，
  不得污染 Health authority。
- Owner/Admin 页面只是同一权威事实的高权限投影，不能建立第二套账户、Nest、模型或
  Runtime 状态。
