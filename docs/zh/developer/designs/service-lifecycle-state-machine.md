# ElfieNest 服务生命周期状态机设计

> 状态：已确认设计
> 确认日期：2026-08-15
> 修订日期：2026-08-18
> 范围：服务状态、Desktop/CLI 入口、进程所有权、故障收敛与启动观测

## 1. 系统资源

| 资源 | 数量与生命周期 |
| --- | --- |
| Core Server | 每个规范化数据根最多一个 Runtime generation |
| Godot authority | 每个 Core generation 最多一个，随 Core 收束 |
| Ollama | 可选；同一 OS 用户下按服务键共享 |
| Desktop Controller | 每个 OS 用户最多一个已打包产品实例 |
| Desktop Viewer | Controller 管理的可关闭、可重开显示窗口 |

Gateway 属于 Core 管理的逻辑组件。PID、端口、锁和 receipt 只是待验证证据，不是服务
状态。`app/orchestration/lifecycle` 是唯一状态写入者；Desktop、CLI、Doctor
和状态页只能调用它或读取其投影。

## 2. 权威稳定状态

Backend 只有三个稳定层级：

| 层级 | 完整条件 |
| --- | --- |
| `OFFLINE` | 没有满足 readiness 的当前 Core generation |
| `CORE_READY` | 数据根单写者、Core 控制/API/Web 入口和实际 endpoint 已就绪 |
| `WORLD_READY` | `CORE_READY`，且当前 Godot generation 已完成认证、协议与场景校验、world 配置、导航以及 actor 目录同步确认 |

模型是独立状态轴，不是第四个 Runtime 层级。模型能力服务依据持久化证据生成权威投影；
证据可综合显式验证、实际调用、新鲜度等，Lifecycle 只消费结果，不复制判定算法。

| 模型组 | 对总状态的影响 |
| --- | --- |
| 常用粮 | 当前有效使用的必需模型路由；全部必须可执行 |
| 保底粮 | 全局应急路由，优先本地 Ollama；决定故障后的续航能力 |
| 非活跃模型 | 未被使用的目录项；失败只显示明细告警 |

| 模型总览 | 条件 |
| --- | --- |
| `UNCONFIGURED` | 没有形成可用的常用粮配置 |
| `READY` | 常用粮全部可执行，保底粮也可执行 |
| `DEGRADED` | 常用粮可执行，但正在使用 fallback，或保底粮不可用 |
| `UNAVAILABLE` | 至少一个当前必需能力没有可执行路由 |

状态页固定先显示系统健康，再显示模型服务。正常完整服务只有在 `WORLD_READY` 且模型
总览为 `READY` 时全绿；Godot 或模型失败不得掩盖仍可使用的 `CORE_READY`。

| 能力 | 最低要求 |
| --- | --- |
| Setup、登录、配置、状态与修复 | `CORE_READY` |
| 3D 世界与身体控制 | `WORLD_READY` |
| 模型聊天 | `CORE_READY` 加请求所需模型路由可执行 |
| 领养 | `WORLD_READY` 加领养强模型和客户端 Godot 预览能力 |

Setup、Normal、Repair 和 Viewer 页面不是服务状态，只是状态消费者。

## 3. 生命周期状态机

启动主线：

```text
OFFLINE
  -> PREFLIGHT
  -> CORE_STARTING
  -> CORE_READY
       |-> WORLD_STARTING -> WORLD_READY
       |-> MODEL_PROJECTING / LOCAL_MODEL_STARTING -> 模型总览稳定状态
```

达到 `CORE_READY` 后，世界与模型并行收敛。`WORLD_STARTING` 固定经过：

```text
GATEWAY_BINDING -> AUTHORITY_SPAWNING -> AUTHENTICATING
-> MANIFEST_VALIDATING -> WORLD_CONFIGURING
-> NAVIGATION_WAITING -> ACTOR_SYNCING -> WORLD_READY
```

运行期断连、崩溃或 revision 变化进入
`WORLD_RECOVERING / WORLD_RECONCILING`；成功回到 `WORLD_READY`，失败回落
`CORE_READY`。

`MODEL_PROJECTING` 只读取权威证据，不发送真实推理请求。本地保底粮只同步确认 Ollama
服务、endpoint 和所需模型库存；真实验证由配置、显式诊断、后台刷新或实际调用触发并
回写证据，不能阻塞 Core 启动。

关闭主线：

```text
任意运行态 -> QUIESCING -> WORLD_STOPPING
-> MODEL_LEASE_RELEASING -> CORE_STOPPING -> OFFLINE
```

`QUIESCING` 立即拒绝新写操作。关闭按所有权逆序、有界执行；未取得的资源跳过。`FAILED`
是命令结果和组件错误，不是第四个稳定状态。

| 竞争或故障 | 确定行为 |
| --- | --- |
| 同数据根重复 start | 附着同一 generation；只允许提升目标 |
| stop 发生在启动中 | 在安全检查点取消并清理该 generation 已取得的资源 |
| restart | 必须先达到 `OFFLINE`，再分配新 generation |
| start 发生在关闭中 | 等待或返回 `BUSY_STOPPING`；generation 不重叠 |
| Core 崩溃 | 回到 `OFFLINE`，收束其 Godot 树 |
| Godot 崩溃 | 回落 `CORE_READY` 并进行有界恢复 |
| 模型故障 | 更新模型证据与总览，不改变 Backend 稳定层级 |
| health/status | 严格只读 |

启动请求同时声明后台 `desired_target` 和调用方 `wait_target`：`CORE`、`WORLD` 或
`NORMAL`。`NORMAL` 表示 `WORLD_READY` 加模型总览 `READY`。Desktop 首次 Setup 只请求
`CORE`；普通 Desktop 在 `CORE_READY` 显示真实界面并后台收敛 `NORMAL`。安装版
`elfienest start` 同样以 `NORMAL` 为后台目标、以 `CORE` 为默认返回目标。

## 4. 任务上下文与目标选择

一个任务由一个规范化数据根标识。代码 checkout、PID 和端口都只是属性或证据，不能选择
任务。所有入口共用同一条处理线：

```text
判定安装版/源码模式 -> 解析唯一数据根 -> 检查当前命令是否可用
-> 只在该根执行 -> 输出该根及其当前 generation
```

记录的启动 executable/cwd 用于验证 generation，比较对象是被观测进程，不是后来发起
命令的 checkout。不同 worktree 可以并行管理不同数据根；跨 CLI 进程显式选择同一数据根
时，任务身份仍是该数据根。

安装版没有任务选择器。Desktop、托盘和全局 CLI 都通过同一用户级解析器解析
`${ELFIE_HOME:-~/.elfienest}`，并共用产品锁。配置 `ELFIE_HOME` 后，它完全替代默认根；
不得 fallback 读取、双写或保存持久“当前根”。相对值统一以用户主目录为基准，因此从不同
工作目录启动的 Desktop 与 CLI 仍得到同一结果。运行中 Controller 与当前解析根不一致时
必须报错，不能借此创建第二份安装版实例。恢复时通过现有托盘停止，或先恢复旧全局设置再
执行 CLI stop；新解析器不能跨根终止旧任务。

源码模式忽略调用方 `ELFIE_HOME`，只在目标选定后把结果发布给子进程。命令面如下：

| 源码命令组 | 接受 `--data-home` | 默认根可用条件 |
| --- | --- | --- |
| `start`、`serve` | 是 | 始终可用，可以初始化默认根 |
| `restart` | 是 | 已识别的生命周期任务 |
| `stop` | 是 | 经验证的运行中/收敛中 generation |
| `status` | 否 | 已识别快照，包括 `OFFLINE` |
| `web` | 否 | 已识别/可启动任务；只确保该任务，再使用其快照 endpoint |
| `mobile` | 否 | 当前快照已发布所需 endpoint |
| 配置、Setup、Doctor、Owner、DB、`data-home inspect/recover` | 否 | 数据根适合该操作；Runtime 无需运行 |

源码交互 Shell 在内存中持有一个 `session_data_home`。每个成功解析的交互目标（显式、
可用默认根或用户明确确认的候选）都在命令执行前替换它；后续命令沿用，直到下一目标解析
成功或 Shell 退出。解析后的命令失败不能 fallback，也不能清空该上下文。单次进程没有
会话上下文。两种方式都只在源码默认根适合当前命令时选择它，否则有 TTY 时展示重新验证
后的候选，即使只剩一个候选也要求确认；无 TTY 时打印相同候选并以“需要选择”失败。

仅所有者可访问的 `<source-root>/.elfienest-cli.local/` 控制目录位于所有产品数据根之外，
用于保存源码 Shell history 和候选目录。候选目录只保存已知规范化数据根及无害展示元数据，
不保存活动指针、PID、endpoint 或凭据。显式或默认根验证后可以刷新目录；选择前重新检查
目录形态、快照身份、generation 和命令适用性，并去重，绝不按端口探测身份。控制目录
丢失或写入失败只影响 history/便利性，不能改变或停止 Runtime；仅进入源码 Shell 也不能
初始化 `<source-root>/.elfienest.local`。

两个例子固定最容易出错的边界：

- `start --data-home A` 后执行 `web`，目标是 A；随后
  `restart --data-home B` 会把会话切到 B，A 继续运行。
- 单次 `stop` 不能因为默认根空闲就直接失败；它应列出经验证的运行中 A/B。没有候选时
  报告“没有运行中服务”。显式目标或会话目标空闲时，只报告该准确事实，不能改选。

`data-home activate` 必须删除，因为它会形成第二份持久“当前数据根” authority；
`data-home inspect` 和 `recover` 保留，但只通过上下文解析目标。

## 5. 入口行为

| 入口 | 最终语义 |
| --- | --- |
| Desktop | 先取得用户级产品锁；第二个 App 只激活现有 Controller |
| Viewer 关闭 | 只关闭显示，Server、Godot 和模型租约不变 |
| 安装版 `elfienest start` | 启动或激活同一 Controller，确保托盘与生产 Server 存在，但不打开 Viewer |
| 托盘 Stop Server / 安装版 `elfienest stop` | 先隐藏 Viewer，再有界关闭准确的生产 Server 和 Controller |
| 源码 `./elfienest.sh` | 仅作开发入口；同数据根附着，不同数据根可并行，`serve` 信号只停止自己拥有的 generation |
| 安装/更新 | 原生安装器提供全局 `elfienest`；经确认停止生产 Server 并等待 `OFFLINE`，否则拒绝覆盖 |
| Doctor | 通过同一 Lifecycle 执行受限修复，不建立第二套启停逻辑 |

Desktop Controller 的全局锁与 App 路径、版本、数据根和端口无关。安装版 App 与全局
CLI 使用同一个生产根解析器；源码 CLI 管理隔离的开发数据根。

正式安装包必须包含启动所需的可执行文件和静态资源；启动时不得安装依赖、导出 Godot
或构建产品资源。缺失时在 preflight 返回可修复错误。用户明确发起的 Ollama 模型下载
不属于产品构建。

端口只是 endpoint。自动模式由服务原子 bind OS 可用端口，并发布到所选数据根快照；
显式 CLI 端口被占用时失败，restart 可以得到不同的自动端口对。`web` 只允许确保已经
解析的目标，`web`、`mobile`、`status` 只能消费该目标快照。任何入口都不得按端口推断
实例、附着或杀死占用者。

## 6. 身份与所有权

实例身份按以下层次确定：

```text
Desktop product lock
-> canonical data-root instance_id
-> Runtime generation
-> component process identity
```

同一数据根只有一个 writer。进程控制必须同时校验 generation、PID birth time、可执行
文件和认证控制凭据。

Godot 是 Core 的受管子进程，但父子关系本身不足以保证清理；必须结合存活管道/watchdog、
POSIX process group 或 Windows Job Object、精确身份校验和有界停止。

Ollama 只有两种来源：

- `EXTERNAL`：启动前已经健康，ElfieNest 永不停止；
- `ELFIENEST_OWNED`：ElfieNest 直接启动并记录准确 generation。

多个 Runtime 通过用户级租约共享同一 `ELFIENEST_OWNED` Ollama。任一实例退出只释放
自己的租约，最后一个有效租约释放后才停止服务。Setup 下载任务也持有租约。不存在
`PERSISTENT_MANAGED` 或 `SESSION_OWNED` 第三状态；所有持有者同时崩溃时，下一次启动
或 Doctor 必须先精确复用或收束该 orphan。

## 7. 故障收敛

| 故障类别 | 收敛规则 |
| --- | --- |
| 健康的同实例已运行 | 直接附着，不重复启动 |
| stale PID/lock/receipt | 校验进程身份后降级证据 |
| 准确旧 generation 孤儿 | 只清理该进程树 |
| 其他实例或第三方进程 | 永不杀死 |
| 隐式端口冲突 | 原子绑定新 endpoint |
| 显式端口冲突 | 返回类型化错误 |
| Godot/模型部分失败 | 保留可用 Core，并只关闭依赖能力 |
| 数据根或打包资源异常 | 在创建局部 generation 前失败 |
| 数据损坏 | 仅显式数据修复；先停止、确认和备份 |

停止前必须验证所选快照的 generation、PID 出生身份、可执行文件/工作目录身份和本地控制
凭据，再按逆序释放该 generation 自有资源。复用 PID 或被重新占用的端口属于外部证据，
必须保持不动；只有经验证的拥有进程退出后，socket 才由 OS 释放。

`start/restart --force` 只执行安全 Runtime 与 endpoint 修复，不删除数据。Core 完全
不可用时由 Desktop 本地恢复 shell 提供修复入口。

## 8. 观测与验收

每次入口调用使用 correlation ID，每次 Server 启动使用 generation，并以单调时钟记录：
锁、preflight、Core、Viewer、模型、Godot 各子阶段、目标 ready 和关闭各阶段。

状态输出必须同时给出稳定层级、当前 phase/subphase、组件状态、实际 endpoint、阶段耗时、
类型化失败和下一条安全修复动作。每个生命周期结果还必须标明已解析的规范化数据根；
start、restart 与 status 同时输出 generation、组件 PID 和实际 endpoint。
只有同一快照确认请求状态后才能输出成功；类型化原因必须保留在数据根日志和结果中，不能
被吞掉。

设计必须保证：

- 两个 App 副本不能产生两个生产 Server；
- 同数据根不能产生两个 writer，不同数据根可以并行；
- 安装版 `ELFIE_HOME` 与默认生产根严格二选一；
- 调用方 `ELFIE_HOME` 不能重定向源码开发命令；
- 默认根未命中不能阻止 `stop` 出现候选选择；
- 新旧 generation 永不重叠；
- PID、端口和进程名不能授予停止权；
- Godot 或模型失败时 Core 仍可配置和修复；
- Viewer 关闭不影响 Server；
- 共享 Ollama 不被任一单独实例提前关闭；
- 每次启动与关闭都得到可解释的终态或类型化失败。
