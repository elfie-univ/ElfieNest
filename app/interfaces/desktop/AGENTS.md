# Desktop Interface 规则

本目录只负责可见 Electron 窗口、系统 UI 集成、资源发现和公开 lifecycle/Observer client。

- Desktop 不拥有 Supervisor、Gateway、账户、聊天、领养、Nest 规则或 Godot authority。
- 只能调用公开 API、版本化 Observer 协议和 lifecycle client；不得导入 Python 内部实现
  或持有 authority 凭据。
- Electron main/preload/renderer 使用最小 IPC 表面和严格消息模型；renderer 不能直接
  获得 Node、文件系统或 Secret 能力。
- 打包资源解析和窗口生命周期属于本目录；产品用例与持久化仍由 App 其他层负责。
- Controller 在每个 OS 用户下全局唯一；Viewer 是可关闭、可重开的展示。关闭 Viewer
  或展示层 Quit 不停止 Server，只有托盘显式 Stop Server 才请求完整收束。
- 安装版 `elfienest start` 通过已认证激活 IPC 复用同一 Controller，并保持 Viewer 关闭；
  第二个 App 副本只激活现有 Controller。
- 新增启动/停止能力前先验证是否违反 lifecycle 唯一所有权。
