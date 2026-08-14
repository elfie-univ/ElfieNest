# ADR-0014：Desktop 启动进度与有界退出

**状态：** 已接受
**日期：** 2026-08-13

## 背景

此前 Desktop Observer 要等完整 Runtime 就绪契约通过后才展示管理页面。Godot
authority 是该契约中最慢的部分，因此 authority 启动较慢时，用户会误以为应用没有
启动；显式退出也会等待仍在进行的启动。生命周期边界必须继续作为 Core 与 Godot
进程状态的唯一所有者；Desktop 不能通过再启动一套 Runtime 或削弱 `ready` 契约来解决
这个问题。

## 决策

- `RuntimeSupervisor` 写入临时的 `startup_owner_id` 收据，并通过公开 CLI 发出启动
  阶段。该收据阻止重复启动，由同一个 Supervisor 清除或提升为普通 owner lease。
- Desktop 立即创建本地窗口和启动壳。在 `core_ready` 时加载现有管理页面，但在完整的
  Godot-backed ready 状态出现前，Observer 控件保持禁用。
- 显式退出先隐藏窗口和 Dock/托盘入口；如果启动仍在进行，则通过公开的 owner-scoped
  stop 命令取消，再按正常生命周期流程停止 Desktop 自己拥有的 lease。
- 关闭 Observer 窗口仍然只是呈现层操作，不停止也不取消 Runtime。
- 生命周期所有者给隐藏 authority 和受管 Core 一个短暂的优雅退出窗口；如果经过再次
  身份核验的同一进程组仍存活，则在有界关闭预算内强制停止。

Core、Gateway 和 Godot 的完整就绪契约不变：只有所有必需组件 ready 后才报告 `ready`。
本决策不改变业务 API、模型启动、打包目标或 Runtime authority 所有权。

## 后果

用户会立即看到真实的启动界面，并可在 Web/Core 层可用后先进入管理页面；Godot 仍在启动
期间，依赖它的控件会明确受限。退出请求不再让 Desktop 界面在清理期间继续可见，启动也
可以通过公开 owner-scoped 路径取消，不需要私有进程控制通道。持久收据增加一个临时字段
`startup_owner_id`，`status --json` 会为机器客户端暴露它，事务结束后该字段被移除。
无响应的子进程也不会再让显式退出无限等待，同时身份校验仍阻止信号发往无关进程。
