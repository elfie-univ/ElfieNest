# Runtime 生命周期边界

本目录是启动、停止、重启、健康聚合、owner lease 和最终收束的唯一 App authority。
目标行为以双语 [`Service lifecycle contract`](../../../docs/developer/contracts/service-lifecycle.md)
为准。

- 只有本目录可以拥有 Core、Gateway 和 Godot authority 的进程生命周期；其他模块只能
  使用公开 lifecycle client 或只读状态。
- 普通模型验证、提醒等业务后台任务由对应 Feature 定义策略，通过 Scheduler/Runner
  Port 执行，不因为需要定时运行就进入本目录。
- 系统健康只反映技术可运行性和关键服务风险；床位、待领养等业务积压进入事件或业务
  投影，不能降低系统健康。
- Backend 稳定层级只有 `OFFLINE / CORE_READY / WORLD_READY`；phase、失败和
  `CORE / WORLD / NORMAL` 目标不得混入稳定层级。
- Runtime 状态使用单一、原子、带 Schema 版本和 generation 的严格快照，不能暴露原始
  Supervisor/Gateway 内部对象。PID、端口和 receipt 只是待验证证据。
- 模型健康算法和证据归模型能力服务；本目录只消费常用粮/保底粮总览，不在启动时执行
  真实推理验证，也不把 Ollama 当成 Backend 第四层。
- start/stop/restart 按规范化数据根串行；重复 start 附着同一 generation，restart 必须
  先到 `OFFLINE`，health/status 永远只读。
- 进程、任务和连接必须可取消、可超时、可收束；禁止在 Interface/Desktop 中复制
  Supervisor 或 authority 凭据。
- 任何 authority 所有权变化都必须先修改长期契约和 ADR，再修改实现。
