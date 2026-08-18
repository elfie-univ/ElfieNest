# 服务生命周期一致性

> 本临时台账对应规范性的[服务生命周期契约](../contracts/service-lifecycle)。`in progress` 表示
> 实现切片已经验证，但契约仍有残余，不代表可以发布收口。

外部验收缺口统一记录为“未测试（外部条件）”，不等同于本地实现失败。在记录指定主机或
安装环境证据前，它们仍然保持开放，不能因为本地检查通过就报告为已完成。

## 已确认实施计划

> 状态：规约已冻结，本地实现切片已落地；安装版支持主机验收仍是明确的外部门禁。
> 风险：**L**；安装版/源码入口、公开 CLI、Desktop 交接和 Runtime 关闭必须一次收敛。

保留现有权威 Runtime 快照/generation、每数据根 writer 锁、用户级 Controller IPC、端点
原子绑定和有界进程树基础，只替换不合规的选择与 fallback 路径。实现边界固定如下：

| 关注点 | 最终结果 |
| --- | --- |
| 任务身份 | 唯一规范化数据根；代码 checkout、PID、端口、候选目录和 health 永远不是身份 |
| 安装版 | 只能是 `${ELFIE_HOME:-~/.elfienest}`；配置根与默认根二选一；每个 OS 用户只有一个 Controller/Runtime |
| 源码 CLI | 忽略调用方 `ELFIE_HOME`；只有 `start`、`serve`、`restart`、`stop` 接受 `--data-home` |
| 交互上下文 | 只有一份内存目标；没有持久活动指针；解析成功后、执行命令前更新上下文 |
| Runtime 控制 | 快照 `(instance_id, generation)` 与准确进程身份授权控制；端口只是在快照发布的 endpoint |
| 非权威 CLI 状态 | `<source-root>/.elfienest-cli.local/` 只保存受保护的 history 与重新验证的候选目录，位于产品根之外 |

### 工作包与门禁

每个工作包先写失败的契约测试。WP1-WP4 可以分开审阅，但共同组成一个**不可拆分发布的
切换**：remembered-root/端口 fallback 仍可达时，任何构建都不能暴露新解析器。

| WP | 实现内容 | 主要边界/文件 | 完成门 |
| --- | --- | --- | --- |
| WP0 — 冻结测试与清单 | 已完成基线与 authority 清单；在实现前分类 remembered-root、调用方环境、端口 fallback 和端口杀进程路径。 | 现有 CLI/lifecycle/Desktop/process 测试及目标/状态聚焦测试。 | 本地基线已分类；外部主机证据留在 WP6。 |
| WP1 — 唯一强类型目标解析器 | 已实现 App 层入口模式、命令策略、目标请求/结果、类型化选择错误以及安装版/源码规范化。 | `app/orchestration/lifecycle/target_resolution.py`、目标上下文解析器和 lifecycle 导出。 | 纯解析器与源码上下文测试通过；解析器不含 UI、subprocess 或数据相关服务构造。 |
| WP2 — 源码 Shell 与 checkout 控制状态 | `elfienest.sh` 只做 bootstrap；持久 Python Shell 管理内存上下文、共用 parser/help、TTY 选择和 scoped 目标环境。受保护 history/候选目录位于被忽略的 `.elfienest-cli.local/`，并重新校验。 | `elfienest.sh`、`scripts/elfienest.py`、`app/interfaces/cli/target_context.py`、`infrastructure/platform/source_cli_state.py`、`.gitignore`。 | Shell、parser、源码状态和 no-fallback 聚焦测试通过；进入 Shell 不创建产品数据。 |
| WP3 — 安装 App/全局 CLI 收敛 | 安装版解析固定为 `${ELFIE_HOME:-~/.elfienest}`；Controller IPC protocol 2 携带期望规范化根并返回 Controller 根。不一致时拒绝附着/停止/切换；Desktop 数据根选择与激活路径已删除。 | 安装版 CLI、Controller IPC、Desktop lifecycle client/role 和 main handlers。 | Desktop/CLI 聚焦测试通过；干净安装主机交接留给外部验收。 |
| WP4 — 命令原子切换 | 只有四个源码生命周期命令解析 `--data-home`；其他命令使用会话/默认/候选解析。scoped 目标环境在命令结束后恢复；旧活动根收据和 activation alias 惰性失效。Provider catalog 与 DB 读取延后到目标绑定执行之后；web/mobile/status 只消费所选快照 endpoint。 | `scripts/elfienest.py`、lifecycle commands/facade、Bootstrap、data-home adapter、parser 与 lifecycle 测试。 | resolver/CLI 聚焦测试通过；已实现路径中不再存在可达活动根 authority 或任意端口附着。 |
| WP5 — 准确 generation 关闭与观测 | 已实现进程出生身份记录、绑定快照的 PID/可执行文件/cwd 校验、发信号前即时复核、类型化 start/stop 错误及每根数据目录的 service log。端口只作发布证据，不向端口占用者发信号。 | Lifecycle snapshot/supervisor/service/start-cleanup、process/record/endpoint adapter 和 CLI 输出。 | PID/端口复用、身份不可读、部分启动、日志和关闭聚焦测试通过；支持主机竞争/恢复证据留在 WP6。 |
| WP6 — 集成、原生验收与收口 | 完成双根/双 worktree 源码验收、安装 App/全局 CLI 交接、Desktop/托盘关闭、Godot 并存、共享 Ollama lease 及每个支持系统的干净安装烟测。真实行为存在后再更新公开帮助/排障/tooling、删除“临时当前行为”文字；只有五类证据齐全才关闭 Conformance 行。 | A/B CLI harness、PTY/非 TTY 测试、Desktop TypeScript suite、release install smoke、文档/契约门禁和 LFC-006/007/008/009/010。 | 本地检查通过；macOS/Windows/Linux 外部证据附上；受影响 P0 residual 与未分类路径均为零。 |

### 解析器命令矩阵

只有没有显式/会话目标时，解析器才判断默认根是否适合当前命令。显式/会话目标即使不能
执行也具有最终决定权。默认根不适用后，有 TTY 才出现选择器；非 TTY 打印同一批重新验证
候选并类型化非零退出。交互中确认的候选会成为会话上下文。目标选择确认与之后的破坏性
操作确认必须分开。

| 命令组 | 源码默认根何时可用 | 没有可用目标/候选时 |
| --- | --- | --- |
| `start`、`serve` | 始终可用，可初始化 `.elfienest.local` | 除非路径本身无效，否则不适用 |
| `restart` | 存在可识别 lifecycle 任务 | `selection_required`；候选为空则 `task_not_found` |
| `stop` | 存在经验证的运行中/收敛中 generation | `no_running_service`；空闲默认根不得压住运行中的 A/B |
| `status` | 存在可识别任务/快照，包括 `OFFLINE` | `task_not_found` |
| `web` | 准确默认根有经验证的运行中 generation 和健康 endpoint | `selection_required`/`task_not_found`；解析后只打开该目标 |
| `mobile` | 准确快照有经验证的运行中 generation 和健康 endpoint | `no_published_endpoint` 或选择 |
| Config、Setup、Doctor、Owner、DB | 数据根适合或可恢复于该操作 | 类型化数据根错误或选择；Runtime 不必运行 |
| `help`、`version`、Shell `exit` | 不需要目标 | 不触碰数据根或候选状态即可执行 |

### 验收矩阵

| ID | 可重放场景 | 必须结果 |
| --- | --- | --- |
| A1 | 安装 App/全局 CLI，`ELFIE_HOME` 未设置或空值 | 只解析 `~/.elfienest`；不存在选择器或 remembered 根。 |
| A2 | 安装 App/全局 CLI，绝对或相对 `ELFIE_HOME=X` | 只读写规范化 X；相对 X 稳定地以用户主目录为基准；默认根完全不动。 |
| A3 | Controller 运行在 A，新安装进程解析到 B | 类型化不一致同时标明 A/B；不产生第二 Controller/Server，不跨根停止或按端口附着；现有托盘可以停止 A。 |
| A4 | 源码 wrapper 在调用方 `ELFIE_HOME=X` 下启动 | bootstrap/选择均不读写 X；仅进入 Shell 不创建产品数据根。 |
| A5 | 分别检查源码/安装模式 parser 与 help，并设置调用方 mode/Desktop 变量 | provenance 仍选择正确入口模式；源码只有四个生命周期命令支持 `--data-home`；安装版和其他全部命令拒绝它。 |
| A6 | 交互执行 `start --data-home A`、`web`、`restart --data-home B`、`status` | 前两条目标 A；restart/status 目标 B；A 继续运行；结果标明根/generation/endpoint。 |
| A7 | 显式/会话目标离线、损坏或不适用，同时另有任务运行 | 只报告准确目标；不得静默改选、探测其他端口或用失败解析覆盖会话。 |
| A8 | 单次 `stop` 的默认根空闲/不存在，A/B 正在运行 | TTY 列出重新验证的 A/B，即使只剩一个也要求确认；非 TTY 打印候选并非零退出；无候选明确没有运行服务。 |
| A9 | 候选文件含重复、stale 根、被替换 instance、坏 JSON 或并发写入 | 只展示去重且当前适用的根；选择后再验证；安全告警/禁用便利功能；绝不推导 authority。 |
| A10 | 8000 上有无关健康进程，所选任务发布其他 endpoint，执行 `web`/`mobile`/`status` | 只消费所选快照 endpoint；`web`/`mobile` 只打开已运行的所选目标，绝不启动服务；外部进程不动。 |
| A11 | 快照 PID 已消失/复用，command/cwd/birth 不一致或不可读，或发布端口已复用 | 不向替代/不可验证进程发信号；安全降级 stale 证据或返回 identity-unverifiable；端口占用本身不能阻止已确认 stop，也不能证明 start。 |
| A12 | 重复 start、启动中 stop、restart、关闭中 start | 每根只有一个 generation；按契约附着/提升、安全取消、先 `OFFLINE` 或返回 `BUSY_STOPPING`。 |
| A13 | 两个 worktree 分别运行根 A/B、独立 Godot，并共享 Ollama | 两套 Runtime/Godot 并存；停止 A 不影响 B；只释放 A 自己的 Ollama holder lease。 |
| A14 | 选择或 start/restart/stop 在启动前、部分启动或有界关闭中失败 | 非零类型化结果保留已脱敏原因和 correlation ID；解析后含准确目标/phase 及可写时的日志路径，否则明确没有可用数据根日志；没有假成功或静默丢异常。 |
| A15 | 存在旧 `selected-data-home`，且 `.elfienest-cli.local` 被删除、只读或设为符号链接 | 旧收据无影响；显式/默认操作仍安全；控制状态失败可见且不能影响 Runtime/产品数据。 |
| A16 | 通过 TTY 选择 recovery/uninstall | 展示规范化目标与状态，选择后重新验证，再单独确认破坏操作；只允许改动该根。 |

### 切换、回滚与完成条件

- 不增加产品数据库迁移、双读写、兼容别名或 feature flag。旧 `selected-data-home` 只可被
  报告为废弃；旧 CLI history 不回放；二者都不能被读取或复制到新控制状态。
- 切换前必须先用旧版本停止旧 Controller/Runtime（原生升级流程调用其现有有界 stop）。
  新客户端遇到仍存活的旧/不兼容协议时只报告，不猜测、不按端口附着、不强杀。
- 规约、实现、最终 Conformance 收口可以分开审阅，但 WP1-WP4 必须原子发布。首版发布前
  回滚只能在受管服务停止后整体回退实现 revision，不能在运行时 fallback 到旧 authority。
- ownership 仍位于 `app/orchestration/lifecycle`，因此不需要新 ADR；若实施时发现真实的
  authority、顶层 ownership 或协议变化，必须停下并先获得批准，再改 ADR/契约版本。
- 完成必须让 LFC-010 与受影响的 LFC-006/007/008/009 都具备 `target`、`inventory`、
  `references`、`verification`、`residuals` 证据并关闭；本地测试全绿不能替代支持主机
  的安装态验收。

### 三轮对抗审查

| 轮次 | 攻击方式 | 已锁定的修补 |
| --- | --- | --- |
| 第一轮：身份/authority | 把候选目录、remembered 根、PID、cwd、健康端口或调用 worktree 当身份；Controller 运行中改变安装 env；删除后复用同一路径。 | 先解析唯一规范化根；候选只做发现；Controller 根不一致直接失败；进程由 `(instance_id, generation, birth identity, credential)` 控制；cwd 只校验被观测的已记录 generation。 |
| 第二轮：上下文/命令流 | 让空闲默认根压住 A/B，让失败显式目标 fallback，候选确认后丢上下文，对 pipeline 弹提示，选择前构造 DB/config 服务，或切到 B 后复用绑定 A 的 facade。 | 命令级适用判断、不 fallback、执行前更新会话、只在 TTY 提示、非 TTY 类型化失败、无根解析与逐命令绑定目标装配都成为门禁；bootstrap 前移除源码调用方 env。 |
| 第三轮：失败/安全/切换 | 用 history 污染 `.elfienest.local`，并发 Shell 竞争，跟随符号链接，杀复用 PID/端口，吞启动错误，或只发布一半新 authority。 | 独立仅所有者控制状态、加锁原子写与重新验证；准确 generation 的 fail-safe 身份关闭；含身份的类型化日志；WP1-WP4 原子发布与整 revision 回滚。 |

三轮审查后，没有遗留需要新增产品规则的决策冲突；开放项是实现与支持主机外部证据，不是
authority 语义未定。

| ID | 严重度 | 状态 | 当前偏差 | 收口门 | 证据 |
| --- | --- | --- | --- | --- | --- |
| LFC-001 | P0 | in progress | 快照 Schema、generation、phase、目标、端点、失败、计时、Controller token 认证和 generation 级 writer 交接已实现；旧 writer 凭据会被拒绝。 | 在支持的已安装主机上证明同一套 authority/identity 链，包括进程出生身份和恢复。 | target=权威快照；inventory=`runtime_snapshot.py`、`runtime_record.py`、`runtime_supervisor.py`、`controller_ipc.py`；references=契约 Authority；verification=架构门禁及 runtime-record/supervisor/IPC 测试；residuals=已安装跨平台身份与恢复验收仍缺。 |
| LFC-002 | P0 | in progress | Core-first 启动、同 generation 附着、类型化 `operation_id`/generation 结果、取消、目标提升和 `NORMAL` 等待已实现；附着命令等待显式要求的 World/Normal 目标，不会启动第二代。 | 在所有已安装入口证明同一协议和竞争行为。 | target=命令/收敛；inventory=`runtime_supervisor.py`、CLI 生命周期命令、Desktop 生命周期客户端；references=契约 Commands；verification=supervisor、CLI、Desktop 测试；residuals=已安装入口互操作和完整竞争矩阵仍缺。 |
| LFC-003 | P0 | in progress | Core 内 World worker 启动并观察准确 generation；POSIX 进程组和 Windows Job Object 覆盖启动/停止/挂接失败清理；World 失败时 Core 保持可用。 | 在支持的 POSIX/Windows 主机证明认证 watchdog 和有界恢复。 | target=Godot 所有权；inventory=`world_worker.py`、Godot authority adapter、进程/Job 机制；references=契约 Managed-process ownership；verification=world-worker/supervisor/process/Godot 测试及 CLI 烟测；residuals=主机级进程树/watchdog 验收仍缺。 |
| LFC-004 | P0 | closed | Food 证据通过唯一持久化投影读取；必需能力证据、Common/Emergency 聚合、能力 permit 和状态 API 使用同一模型总览，启动不推理。完整 Core/World/Chat/Adoption 矩阵已在服务端门禁；PMA-002 记录的已配置远程 Provider 证据通过同一投影消费。 | Registry、持久化投影、chat 路由和 adoption 路由测试覆盖所需后端/模型组合及拒绝边界。 | target=模型轴与服务端门禁；inventory=Food 投影 Adapter、`capability_gate.py`、API 路由；references=契约 Stable state/Commands；verification=`test/app/orchestration/lifecycle/test_capability_gate.py`、`test/infrastructure/persistence/test_model_health_projection.py`、chat/adoption API 测试及 PMA-002 真实 Provider 证据；residuals=none |
| LFC-005 | P0 | in progress | Ollama 仅有 `EXTERNAL` 与 `ELFIENEST_OWNED`，具备准确进程身份和用户级 holder 租约；Doctor/start 不再宽泛杀进程。 | 增加多数据根真实崩溃/孤儿/进程复用及 Setup/Runtime 竞争验收。 | target=共享 Ollama 所有权；inventory=`lifecycle_ollama.py`、Setup lease、Ollama 测试；references=契约 Managed-process ownership；verification=共享租约与 Provider 测试；residuals=多进程崩溃和平台验收仍缺。 |
| LFC-006 | P0 | in progress | Desktop 关闭 Viewer 只影响展示；认证的用户级 Controller IPC 已提供 `ACTIVATE_VIEWER`/`ENSURE_SERVER`/`STOP_SERVER`/`STATUS`（POSIX 使用 UDS，Windows 使用 loopback token endpoint）；Electron single-instance 仍是第二道保护。 | 证明安装版 CLI/App 在支持平台上的交接；若产品契约要求，则把 Windows TCP fallback 换成 named pipe。 | target=Desktop/CLI 入口；inventory=`main.ts`、`controller_ipc.ts`、`desktop_role_lifecycle.ts`、`desktop.py`；references=契约 Entrypoints；verification=44 个 Desktop 测试（含授权 IPC 运行）及 Python IPC/CLI 测试；residuals=干净机器安装版交接与 Windows named-pipe 验收仍缺。 |
| LFC-007 | P1 | in progress | Core 原子预留并发布实际 HTTP/Godot 端口对，绝不终止端口占用者。CLI start 现在打印所选 HTTP 与 Godot WebSocket 端口；web/mobile/status 只消费所选快照 endpoint。 | 在每个支持系统的干净主机执行原生安装/升级/卸载烟测。 | target=endpoint 与打包；inventory=Core endpoint binder、生命周期快照、CLI 交接、release pipeline、原生 launcher hook；references=契约 Entrypoints；verification=loopback/Gateway、端口冲突、lifecycle command 和 launcher-hook 测试；residuals=干净主机打包证据仍缺。 |
| LFC-008 | P0 | in progress | stop 解析所选数据根，校验快照 PID/出生身份/可执行文件/cwd，并在每次发信号前重新校验；PID/端口占用者不作为 authority。 | 在支持主机完成完整孤儿/进程树、PID 复用、端口复用和超时矩阵。 | target=关闭/恢复；inventory=`runtime_supervisor.py`、`service.py`、CLI 目标解析器和进程 adapter；references=契约 Shutdown；verification=supervisor/service/process/target-resolution 测试；residuals=主机级和完整竞争矩阵仍缺。 |
| LFC-009 | P1 | in progress | 版本化生命周期/模型投影与 phase 计时已暴露；start 输出准确运行端口，失败输出保留类型化原因/日志路径。 | 完成原生 runner 矩阵，并随发行产物保留安装态计时证据。 | target=观测/release 门禁；inventory=Runtime projection DTO、前端 Schema/panel、CLI JSON 和 release smoke；references=契约 Observation；verification=API/前端/Desktop、生命周期压力、CLI 和 smoke-runner 测试；residuals=安装态跨平台计时证据仍缺。 |
| LFC-010 | P0 | in progress | 安装版唯一根为 `${ELFIE_HOME:-~/.elfienest}`；源码上下文仅在内存中，源码忽略调用方 `ELFIE_HOME`，只有四个生命周期命令接受 `--data-home`，候选目录隔离在 `.elfienest-cli.local/`。旧选中根/激活文件惰性失效。 | 完成支持主机 App/全局 CLI 交接和最终 A/B PTY/非 TTY 烟测。 | target=数据根任务上下文；inventory=`scripts/elfienest.py`、`elfienest.sh`、target resolver/context、source state、lifecycle data-home adapter 和 Controller IPC；references=契约“数据根与任务上下文”和设计 §4；verification=target-resolution/source-state/CLI/Desktop 测试；residuals=安装主机与 PTY 烟测证据仍缺。 |

任何条目都不能只凭测试关闭。每行都记录 target、inventory、references、verification 和
residuals。外部 residual 是最终发布验收缺口，不阻塞本地 checkpoint；严格发布收口仍须
补齐它们。
