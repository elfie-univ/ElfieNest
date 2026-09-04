# 服务生命周期契约

**契约版本：** 1.4
**采用日期：** 2026-08-15
**修订日期：** 2026-09-03
**适用范围：** 安装版与源码 Runtime 生命周期、就绪判定和进程所有权

> **规范性目标。** 本契约固定 Desktop、CLI、Doctor、安装器和状态页面共享的服务状态
> authority 与不变量。原因和说明分别见
> [ADR-0021](../decisions/0021-authoritative-service-lifecycle)与已审阅的
> [状态机设计](../designs/app/service-lifecycle-state-machine)；当前差距只记录在
> [一致性台账](../conformance/service-lifecycle)中。

## Authority、身份与快照

`app/orchestration/lifecycle` 是 Runtime 生命周期状态的唯一写入者，也是 Core、Gateway
和 Godot 启动、停止、重启、恢复与收敛的唯一协调者。Interface、Bootstrap、健康探针和
Infrastructure Adapter 只能作为客户端、构造者或证据提供者，不能推导并持久化第二份
生命周期状态。

每个规范化数据根最多一个 writer 和一个当前 Runtime generation。唯一原子、带 Schema
版本的快照至少包含：

- 规范化 instance ID 与单调 generation；
- Backend 稳定层级及当前 phase/subphase；
- 组件 PID、进程出生/可执行文件/cwd 身份、状态与类型化失败；
- 实际绑定 endpoint 及协议/资源版本；
- 期望目标、已达目标和剩余收敛项；
- correlation ID 与各 phase 单调计时。

快照写入和生命周期命令由规范化数据根锁串行化。安装版 Desktop 先取得用户级产品锁；
进程 authority 再按以下顺序确定：

```text
Desktop product lock -> canonical data-root instance -> Runtime generation
-> validated component process identity
```

PID、端口、进程名、receipt 或锁文件都只是证据。进程控制还必须验证 generation、可执行
文件、进程出生身份和已认证本地控制凭据。客户端按 instance、generation 和协议版本重新
附着；版本不兼容时报告正在运行的版本，不得再启动一套 authority。

可执行文件、cwd 与出生身份必须和所选快照 generation 对比，不能和发起命令的 checkout
对比。后续 CLI 只能通过兼容协议和该数据根的凭据控制该任务。

## 数据根与任务上下文

规范化数据根就是任务身份。每条命令必须先解析且只解析一个目标，之后不得重新解析、按端口
附着，或把 PID、endpoint、候选目录项当成身份。

已打包 App、托盘和安装版全局 CLI 共用唯一生产解析器：

```text
生产数据根 = ${ELFIE_HOME:-~/.elfienest}
```

`ELFIE_HOME` 二选一：设置后安装版只使用该根，否则只使用默认根。不存在“已记忆的生产
数据根”、`selected-data-home` 指针或 `data-home` 命令。每个 OS 用户最多一个打包
Controller 和 Runtime。运行中的 Controller 报告其他数据根时，返回类型化不一致；不得
切换、附着其他任务或启动第二个 Controller。

源码 `./elfienest.sh` 使用独立解析器并忽略调用方 `ELFIE_HOME`。只有 `start`、`serve`、
`restart`、`stop` 接受 `--data-home`；选定根只作为子进程内部 `ELFIE_HOME` 发布。其他
源码命令通过上下文、默认根或候选解析，不接受 `--data-home`。`uninstall` 只在安装版
CLI 提供；不存在公开 `data-home` 命令。

源码目标优先级固定如下：

| 调用方式 | 解析顺序 |
| --- | --- |
| 交互 Shell | 显式生命周期根 -> 会话上下文 -> 可用 `<source-root>/.elfienest.local` -> 确认候选 |
| 单次命令 | 显式生命周期根 -> 可用默认根 -> TTY 确认候选 |
| 无唯一目标的非交互命令 | 打印候选并失败；不得猜测或等待输入 |

TTY 选择始终需要显式确认；唯一候选不等于持久会话上下文。

显式目标或已有会话上下文具有决定权；在该目标失败时不能 fallback 到其他任务。每个成功
解析的交互目标成为仅存在内存中的会话上下文；失败或无效解析不能替换它。

可用性按命令判断：`start`/`serve` 可创建默认根；`stop` 要求已验证 generation，空闲默认
根不能阻止选择其他运行候选；`restart` 要求已识别任务。`web`、`mobile`、`desktop` 只打开已有健康目标，绝不启动或修复。
`status`、数据和配置命令只要求可用数据根；没有可停
止候选时明确报告没有服务运行。

Shell history 和候选发现只使用可选的 owner-only 子目录
`<source-root>/.elfienest.local/runtime/cli/`。显式数据根不要求存在它；缺少它不影响
数据根，存在它也不能授予权限或选择任务。候选每次显示前重新验证；不读取旧状态位置，
目标选择和命令执行分开。

## 稳定状态与模型健康

Backend 稳定层级只有三个：

| 层级 | 完整条件 |
| --- | --- |
| `OFFLINE` | 没有满足 Core readiness 的当前 generation |
| `CORE_READY` | 数据根 writer、Core 控制/API/Web 入口和已发布 endpoint 就绪 |
| `WORLD_READY` | `CORE_READY`，且当前 Godot generation 已完成认证、协议/场景兼容、world 配置、导航和 actor 同步确认 |

过渡 phase 与类型化失败不是额外稳定层级。Setup、Normal、Repair 和 Viewer 是展示模式，
不是服务状态。

模型健康是独立轴，由 App Food/模型能力服务根据持久化技术证据生成权威投影。
Lifecycle 只消费投影，不能复制评分算法，也不能在启动时发送真实推理请求。

| 模型组 | 对总览的影响 |
| --- | --- |
| 常用粮 | 当前必需路由必须全部可执行 |
| 保底粮 | 全局应急路由，优先本地 Ollama；全绿时必须可执行 |
| 非活跃模型 | 失败只显示明细告警，不降低运行健康 |

模型总览为 `UNCONFIGURED`、`READY`、`DEGRADED` 或 `UNAVAILABLE`。`READY` 要求常用粮
和保底粮均可执行；常用粮正在使用 fallback 或保底粮不可用时为 `DEGRADED`；任一当前
必需能力没有可执行路由时为 `UNAVAILABLE`。

启动可确认已配置的本地 Ollama 服务、endpoint 和所需模型库存，但真实推理验证只能由
配置、显式诊断、有界后台刷新或实际模型调用触发。结果回写模型证据 authority，且不能
阻塞 Core readiness。

## 命令、收敛与能力门禁

启动命令分别声明 `desired_target` 和 `wait_target`：`CORE`、`WORLD` 或 `NORMAL`。
`NORMAL` 是 `WORLD_READY` 加模型总览 `READY` 的派生条件。

```text
OFFLINE -> PREFLIGHT -> CORE_STARTING -> CORE_READY
  |-> WORLD_STARTING -> WORLD_READY
  |-> MODEL_PROJECTING / LOCAL_MODEL_STARTING -> 模型总览稳定状态
```

达到 `CORE_READY` 后，世界与模型独立收敛。Godot 失败回落 `CORE_READY`；模型失败只改变
模型健康；Core 失败回到 `OFFLINE`。

| 命令竞争 | 必须行为 |
| --- | --- |
| 同数据根重复 start | 附着同一 generation；只允许提升目标 |
| 启动中 stop | 在安全检查点取消，只清理该 generation 已取得的资源 |
| restart | 先达到 `OFFLINE`，再分配下一 generation |
| 关闭中 start | 等待或返回类型化 `BUSY_STOPPING`；generation 不重叠 |
| status/health | 严格只读；不得启动、修复或杀死组件 |

唯一强类型能力需求注册表把每项产品操作映射到最低 Backend 层级和模型要求；唯一服务端
评估器据此返回 generation 级 permit 或类型化拒绝。UI 禁用只是投影，不能代替服务端
门禁。能力检查不得自动启动组件；有不可逆边界的流程必须在提交前重新验证。

## 入口与安装资源

| 入口 | 必须行为 |
| --- | --- |
| 已打包 Desktop | 取得全局产品锁，启动/附着生产 Server，创建托盘并打开 Viewer |
| Viewer 关闭或展示层退出 | 只关闭展示；Server、Godot 和模型租约不变 |
| 安装版 `elfienest start` | 启动/激活同一 Controller、托盘和生产 Server，不打开 Viewer；默认 `desired=NORMAL`、`wait=CORE` |
| 安装版 `elfienest restart` | 通过 Controller 生命周期停止准确的生产 Server，再启动/激活同一 Controller 和 Server，不打开 Viewer；发布新 generation 的实际端口 |
| 安装版 `elfienest web` / `mobile` / `desktop` | 只打开已经运行的目标；绝不启动或修复 Server、Controller 或 Runtime；找不到目标或没有健康 endpoint 时直接报错 |
| 托盘 Stop Server / 安装版 `elfienest stop` | 先隐藏 Viewer，再有界关闭准确的生产 Server 和 Controller |
| 源码 `./elfienest.sh` | 只用于开发；同数据根附着，不同显式数据根可并行，`serve` 保持前台所有权 |
| 安装或升级 | 检测经验证的运行中 Controller，提示用户停止并有界等待 `OFFLINE`；无法收敛时拒绝覆盖 |

产品锁与 App 路径、版本、数据根和端口无关。第二个 App 副本只激活现有 Controller；安装版
与源码解析器保持隔离。

各平台原生安装器必须提供全局 `elfienest` launcher，不存在源码安装路径。正式启动只
使用已打包的可执行文件和静态资源，不得安装 Python/Node 依赖、导出 Godot 或构建产品
资源。资源缺失或不兼容时，preflight 返回类型化修复/重装动作。用户明确发起的 Ollama
模型下载不属于产品构建。

端口只是 endpoint，不是身份或清理目标。自动 restart 可以发布新端口；旧端口永远不能选择
任务。显式端口冲突返回类型化错误；任何入口都不能按端口杀进程或附着。

## 受管进程所有权

Godot 是准确 generation 的 Core 受管子进程，只能通过 Lifecycle 自有 Port 操作。
Infrastructure 提供平台机制：已认证存活 watchdog、POSIX process group 或 Windows Job
Object、准确身份验证及有界优雅/强制停止。父子关系本身不是清理保证。

Ollama 只有两种来源：

- `EXTERNAL`：ElfieNest 行动前已经健康，ElfieNest 永不停止；
- `ELFIENEST_OWNED`：ElfieNest 启动并记录准确进程身份。

多个 Runtime 通过用户级租约共享同一个 `ELFIENEST_OWNED` 服务。每个实例只释放自己的
租约，最后一个有效租约释放后才停止服务；Setup 下载也持有租约。全部持有者崩溃后，
下一次启动或 Doctor 必须先验证并复用或收束孤儿。禁止第三种所有权模式和按名称广泛杀进程。

## 关闭、恢复与观测

关闭必须串行且有界：

```text
任意运行态 -> QUIESCING -> WORLD_STOPPING
-> MODEL_LEASE_RELEASING -> CORE_STOPPING -> OFFLINE
```

`QUIESCING` 拒绝新写操作；清理按逆序且限定 generation。PID 已死亡/复用或端口属于其他
进程时只报告并保持不变；端口不能被“杀死”，也不能终止第三方进程。

每次入口调用产生 correlation ID，每次 Server 启动产生 generation。状态和生命周期日志
写入已解析数据根，包含身份、endpoint、耗时、类型化失败和一条安全下一步动作。

start、restart、stop 只有在所选快照确认承诺状态后才能报告成功。失败必须保留在快照和
日志中，并连同目标根与 correlation ID 返回 CLI；不得泛化成功或静默附着其他任务。

永久测试必须保护本契约中的 authority 路径和文档不变量；一致性台账关闭前，行为测试
必须覆盖 App/CLI 重复启动、命令竞争、stale receipt、endpoint 冲突、部分失败、重新附着、
孤儿收束、安装/升级交接、安装资源 preflight 和有界关闭。
