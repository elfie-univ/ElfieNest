# 服务生命周期一致性

> 本临时台账对应规范性的[服务生命周期契约](../contracts/service-lifecycle)。`in progress` 表示
> 实现切片已经验证，但契约仍有残余，不代表可以发布收口。

| ID | 严重度 | 状态 | 当前偏差 | 收口门 | 证据 |
| --- | --- | --- | --- | --- | --- |
| LFC-001 | P0 | in progress | 快照 Schema、generation、phase、目标、端点、失败、计时、Controller token 认证和 generation 级 writer 交接已实现；旧 writer 凭据会被拒绝。 | 在支持的已安装主机上证明同一套 authority/identity 链，包括进程出生身份和恢复。 | target=权威快照；inventory=`runtime_snapshot.py`、`runtime_record.py`、`runtime_supervisor.py`、`controller_ipc.py`；references=契约 Authority；verification=架构门禁及 runtime-record/supervisor/IPC 测试；residuals=已安装跨平台身份与恢复验收仍缺。 |
| LFC-002 | P0 | in progress | Core-first 启动、同 generation 附着、类型化 `operation_id`/generation 结果、取消、目标提升和 `NORMAL` 等待已实现；附着命令等待显式要求的 World/Normal 目标，不会启动第二代。 | 在所有已安装入口证明同一协议和竞争行为。 | target=命令/收敛；inventory=`runtime_supervisor.py`、CLI 生命周期命令、Desktop 生命周期客户端；references=契约 Commands；verification=supervisor、CLI、Desktop 测试；residuals=已安装入口互操作和完整竞争矩阵仍缺。 |
| LFC-003 | P0 | in progress | Core 内 World worker 启动并观察准确 generation；POSIX 进程组和 Windows Job Object 覆盖启动/停止/挂接失败清理；World 失败时 Core 保持可用。 | 在支持的 POSIX/Windows 主机证明认证 watchdog 和有界恢复。 | target=Godot 所有权；inventory=`world_worker.py`、Godot authority adapter、进程/Job 机制；references=契约 Managed-process ownership；verification=world-worker/supervisor/process/Godot 测试及 CLI 烟测；residuals=主机级进程树/watchdog 验收仍缺。 |
| LFC-004 | P0 | in progress | Food 证据通过唯一持久化投影读取；必需能力证据、Common/Emergency 聚合、能力 permit 和状态 API 使用同一模型总览，启动不推理。 | 完成 Common/Emergency route 矩阵，并用真实 Provider 证据证明所有产品操作都有服务端门禁。 | target=模型轴/门禁；inventory=Food 投影 Adapter、`capability_gate.py`、API 路由、状态页；references=契约 Stable state/Commands；verification=Food、能力、API、前端测试；residuals=完整 route 矩阵与真实 Provider 验收仍缺。 |
| LFC-005 | P0 | in progress | Ollama 仅有 `EXTERNAL` 与 `ELFIENEST_OWNED`，具备准确进程身份和用户级 holder 租约；Doctor/start 不再宽泛杀进程。 | 增加多数据根真实崩溃/孤儿/进程复用及 Setup/Runtime 竞争验收。 | target=共享 Ollama 所有权；inventory=`lifecycle_ollama.py`、Setup lease、Ollama 测试；references=契约 Managed-process ownership；verification=共享租约与 Provider 测试；residuals=多进程崩溃和平台验收仍缺。 |
| LFC-006 | P0 | in progress | Desktop 关闭 Viewer 只影响展示；认证的用户级 Controller IPC 已提供 `ACTIVATE_VIEWER`/`ENSURE_SERVER`/`STOP_SERVER`/`STATUS`（POSIX 使用 UDS，Windows 使用 loopback token endpoint）；Electron single-instance 仍是第二道保护。 | 证明安装版 CLI/App 在支持平台上的交接；若产品契约要求，则把 Windows TCP fallback 换成 named pipe。 | target=Desktop/CLI 入口；inventory=`main.ts`、`controller_ipc.ts`、`desktop_role_lifecycle.ts`、`desktop.py`；references=契约 Entrypoints；verification=44 个 Desktop 测试（含授权 IPC 运行）及 Python IPC/CLI 测试；residuals=干净机器安装版交接与 Windows named-pipe 验收仍缺。 |
| LFC-007 | P1 | in progress | 隐式启动会选确定性的备用端口对、重试绑定冲突且不终止占用者；`install.sh` 仍保持删除；PKG/NSIS/DEB 原生打包现在通过各平台钩子创建全局 `elfienest` launcher。 | 在 Core 中原子绑定自动端口，并在受支持的干净主机上验证安装/升级/卸载。 | target=端点/打包；inventory=CLI 端口选择、release pipeline、Electron builder 配置和原生 launcher 钩子；references=契约 Entrypoints；verification=端口冲突测试、发布资源测试、launcher 钩子测试、隔离 CLI 烟测；residuals=预绑定竞态、干净 VM 安装/升级/卸载门禁仍缺。 |
| LFC-008 | P0 | in progress | stop 发布 `QUIESCING`/逆序 phase，Doctor 只诊断；准确当前数据根停止已验证。 | 让升级/Doctor 共用一个有界 stop executor，增加认证 force escalation 和每个 phase 的残留报告。 | target=关闭/恢复；inventory=`runtime_supervisor.py`、Doctor 命令、进程 Adapter；references=契约 Shutdown；verification=supervisor/Doctor 测试及停止烟测；residuals=完整 orphan/进程树/超时矩阵仍缺。 |
| LFC-009 | P1 | in progress | 生命周期/模型版本化投影已通过 API 和状态页暴露；系统健康先于模型健康，phase 计时可见；可重复的生命周期压力门已覆盖 300 次 warm attach 和 50 次 cold 启停循环。 | 跑完原生安装/升级/卸载可靠性门禁，并发布带错误码的启停预算和修复证据。 | target=观测/发布门；inventory=runtime projection DTO、前端 schema/panel、CLI JSON 和生命周期压力测试；references=契约 Observation；verification=API、前端、Desktop 测试、隔离启停烟测及 `test_lifecycle_pressure_gate_runs_warm_and_cold_cycles`；residuals=10 次安装循环和带类型的启停计时预算尚未在此环境执行/发布。 |

任何条目都不能只凭测试关闭。每行都记录 target、inventory、references、verification 和
residuals；剩余 residual 是发布阻断项，不是可选清理项。
