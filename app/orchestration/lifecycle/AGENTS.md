# Runtime 生命周期边界

本目录是启动、停止、重启、健康聚合、owner lease 和最终收束的唯一 App authority。

- 只有本目录可以拥有 Core、Gateway 和 Godot authority 的进程生命周期；其他模块只能
  使用公开 lifecycle client 或只读状态。
- 普通模型验证、提醒等业务后台任务由对应 Feature 定义策略，通过 Scheduler/Runner
  Port 执行，不因为需要定时运行就进入本目录。
- 系统健康只反映技术可运行性和关键服务风险；床位、待领养等业务积压进入事件或业务
  投影，不能降低系统健康。
- Runtime 状态使用严格快照和事件模型，不能暴露原始 Supervisor/Gateway 内部对象。
- 进程、任务和连接必须可取消、可超时、可收束；禁止在 Interface/Desktop 中复制
  Supervisor 或 authority 凭据。
- 任何 authority 所有权变化都必须先修改长期契约和 ADR，再修改实现。
