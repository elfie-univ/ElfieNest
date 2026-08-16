# 服务生命周期契约

**契约版本：** 1.0
**采用日期：** 2026-08-15
**适用范围：** 安装版与源码 Runtime 生命周期、就绪判定和进程所有权

> **规范性目标。** 本契约固定 Desktop、CLI、Doctor、安装器和状态页面共享的服务状态
> authority 与不变量。原因和说明分别见
> [ADR-0021](../decisions/0021-authoritative-service-lifecycle)与已审阅的
> [状态机设计](../designs/service-lifecycle-state-machine)；当前差距只记录在
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
- 组件身份、状态与类型化失败；
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
| 托盘 Stop Server / 安装版 `elfienest stop` | 先隐藏 Viewer，再有界关闭准确的生产 Server 和 Controller |
| 源码 `./elfienest.sh` | 只用于开发；同数据根附着，不同显式数据根可并行，`serve` 保持前台所有权 |
| 安装或升级 | 检测经验证的运行中 Controller，提示用户停止并有界等待 `OFFLINE`；无法收敛时拒绝覆盖 |

产品锁与 App 路径、版本和端口无关。第二个 App 副本只激活现有 Controller，不能再启动
生产 Server。安装版 App 与全局 CLI 指向同一生产数据根；源码开发数据根保持隔离。

各平台原生安装器必须提供全局 `elfienest` launcher，不存在源码安装路径。正式启动只
使用已打包的可执行文件和静态资源，不得安装 Python/Node 依赖、导出 Godot 或构建产品
资源。资源缺失或不兼容时，preflight 返回类型化修复/重装动作。用户明确发起的 Ollama
模型下载不属于产品构建。

端口只是已发布 endpoint，不是实例身份。自动模式原子绑定 OS 选择的可用端口并记录
结果；显式开发端口被占用时返回类型化冲突。任何入口都不能仅凭端口占用杀死进程或附着。

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

`QUIESCING` 拒绝新写操作。清理按所有权逆序执行，跳过本 generation 未取得的资源。
stale 证据只有在身份校验后才能降级；只能收束准确旧 generation 的进程树，永不终止
第三方或其他实例进程。

每次入口调用产生一个 correlation ID，每次 Server 启动产生一个 generation。单调计时
覆盖产品/数据根锁、preflight、Core、Viewer、模型、Godot、请求目标和各关闭 phase。
状态输出稳定层级、phase、组件事实、模型总览、endpoint、耗时、类型化失败和一条安全
下一步动作。

永久测试必须保护本契约中的 authority 路径和文档不变量；一致性台账关闭前，行为测试
必须覆盖 App/CLI 重复启动、命令竞争、stale receipt、endpoint 冲突、部分失败、重新附着、
孤儿收束、安装/升级交接、安装资源 preflight 和有界关闭。
