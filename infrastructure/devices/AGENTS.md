# Device Adapter 规则

本目录承载精灵外部身体的技术接入：发现、配对、凭据材料、LAN/其他传输、Session、
技术健康与设备网关实现。

- 只实现 Feature/Orchestration/Elfie body 定义的 Port。设备注册、授权和 Elfie/body
  关联属于 App Feature；身体命令与感知语义属于 `elfie/body`；hosting、回巢和身体
  切换等跨 authority 流程属于 Orchestration。
- 原始设备帧、SDK 对象和密钥不能越过 Adapter；输出严格 Port Model，并对凭据和日志
  做最小暴露。
- 设备使用独立最小权限身份，不复用管理员会话、Observer 或 Runtime authority 凭据。
- 网络调用必须有超时、取消、幂等/重连语义和明确错误分类；不能在数据库事务中等待。
- 新协议先定义受测试保护的版本化边界，不能为某一页面临时发送任意 JSON。
