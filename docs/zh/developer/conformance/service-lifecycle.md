# 服务生命周期一致性

> 本临时台账对应规范性的[服务生命周期契约](../contracts/service-lifecycle)，只记录已验证
> 的实现缺口和收口门；详细执行计划是独立的非规范性产物。

| ID | 严重度 | 状态 | 当前偏差 | 收口门 | 证据 |
| --- | --- | --- | --- | --- | --- |
| LFC-001 | P0 | open | `RuntimeHealth` 与 `runtime.json` 混合总状态、组件探针和 owner receipt，缺少规范化 instance 身份、快照 Schema 版本、目标和 phase 计时。 | 唯一原子 generation 快照与数据根命令锁实现契约字段；stale/损坏记录不能授予 authority。 | pending |
| LFC-002 | P0 | open | start 等待单一完整 `ready/degraded` 结果，未表达 desired/wait target 和确定性的 start/stop/restart 竞争。 | 类型化命令实现 `CORE/WORLD/NORMAL`、幂等附着、目标提升、取消、`BUSY_STOPPING` 和 generation 不重叠。 | pending |
| LFC-003 | P0 | open | Godot 从 Core 健康回调中启动；authority 失败会停止 Core，崩溃后的重新收敛也不是独立流程。 | 世界收敛与恢复按 generation 管理、可独立取消并真实回落 `CORE_READY`；平台子进程清理得到证明。 | pending |
| LFC-004 | P0 | open | Ollama 被当成布尔型可选 Runtime 组件，Provider/状态页分别重算健康；没有消费常用粮/保底粮证据的统一能力门禁。 | 模型能力服务从持久化证据投影四种总览状态，Lifecycle 只消费；唯一服务端能力注册表执行要求。 | pending |
| LFC-005 | P0 | open | Ollama 启动没有 `EXTERNAL`/`ELFIENEST_OWNED` 身份、用户级租约、最后释放停止或孤儿收束。 | 多实例租约测试证明准确所有权、复用、最后释放、崩溃恢复和对预先存在服务的保护。 | pending |
| LFC-006 | P0 | open | 已打包 Desktop 总会打开 Viewer；已打包 CLI 直接启动 Server，也没有全局 launcher 以无 Viewer 模式激活共享 Controller。 | App 副本和安装版 CLI 共享一个已认证 Controller；Viewer 退出独立，托盘/CLI 显式停止准确关闭生产 Server 与 Controller。 | pending |
| LFC-007 | P1 | open | 默认端口固定，实例发现仍部分依赖 PID/端口证据；各支持平台的原生包尚未全部安装全局 `elfienest` 命令。 | 自动 endpoint 原子选择并发布，显式冲突类型化；干净机器安装/升级/卸载测试证明运行中 Server 有界交接且无需源码即可找到全局 launcher。 | pending |
| LFC-008 | P0 | open | 关闭与 Doctor 已有多条 receipt/进程修复路径，但没有唯一 quiesce-to-offline 流程证明逆所有权、有界升级和准确残留报告。 | stop/restart/Doctor 复用唯一命令执行器；竞争、超时、孤儿和第三方负例证明准确有界清理。 | pending |
| LFC-009 | P1 | open | 启动 phase 粗糙；状态页独立拼接 `/api/health`、Provider 和 Ollama 数据，没有原子生命周期/模型投影及阶段计时。 | CLI/API/Desktop/状态页消费同一版本化投影，先显示系统再显示模型健康；发布验收记录启停阶段预算和类型化修复动作。 | pending |

实现按依赖顺序关闭：先 `LFC-001`、`LFC-002`，再处理 `LFC-003`–`LFC-005`，之后处理
入口、打包与关闭，最后以观测和发布证据关闭 `LFC-009`。任何行都不能只凭测试关闭；证据
必须同时包含 target、inventory、references、verification 和 residuals。
