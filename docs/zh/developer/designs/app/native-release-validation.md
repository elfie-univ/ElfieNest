# 原生发布验证与安装版核心用户旅程

> 状态：阶段 0–2、重复启动恢复检查、最小安装版 Viewer 就绪 marker、证据绑定和 Soak 趋势分类器
> 已在本地实现。原生主机、完整 UI、真实升级和长窗口证据仍需完成；本页不声称下面每个门禁都已存在或通过。当前差距由
> [服务生命周期一致性台账](../../conformance/service-lifecycle.md#原生发布验收队列)跟踪。

> 设计关系：**所属模块：**App；**上级设计：**整个系统全局设计（独立的上级设计，本次未移动）；
> **下级设计：**无；**规范性契约：**[服务生命周期契约](../../contracts/service-lifecycle.md)；**当前架构：**[运行时与数据](../../architecture/runtime.md)；
> **一致性台账：**[服务生命周期一致性](../../conformance/service-lifecycle.md)；**领域资料来源：**Product 发布旅程。

## 1. 目标与发布结论

ElfieNest 只有一套共享产品核心，但有四个原生发布 target：

- `darwin-arm64`；
- `darwin-x64`；
- `win32-x64`；
- `linux-x64`。

源码测试通过、安装包成功生成或到达 `WORLD_READY`，都只能证明自己的边界。发布候选必须
同时具备两类证据：

1. **原生安装包与生命周期完整性**——安装、启动、进程所有权、停止、重新安装、卸载和
   平台集成；
2. **安装版产品连续性**——首次 Setup、模型配置、领养、聊天、持久化、重启与真实升级。

目标首次用户路径是：

```text
原生安装
  -> 首次 Setup
  -> 确定性模型配置
  -> Owner 登录
  -> 领养一只 Elfie
  -> 收到一次经过 Brain 的聊天回复
  -> 使用同一数据根重启
  -> 恢复 Setup、Elfie、Nest 与会话状态
```

任何单一测试层都不能冒充整条路径的证明。

## 2. 六层验证体系

| 层级 | 回答的问题 | ElfieNest 必需证据 | 当前位置 |
| --- | --- | --- | --- |
| 单元测试 | 一个函数或类是否正确？ | 解析、校验、状态迁移、路径规则和平台 Adapter。 | 已有覆盖；保持聚焦、确定性。 |
| 集成测试 | 多个模块是否遵守协作契约？ | Core、SQLite、Gateway、Godot 协议、Setup、Provider、领养和聊天边界。 | 已有覆盖，包括源码级 Setup/领养及 Brain/聊天切片。 |
| 原生安装 smoke | 打包后的产品最基本能否活起来？ | 安装、安装版 Controller 启动、`WORLD_READY`、Controller/Core/Godot PID、有界停止、已记录进程零残留、重新安装和卸载。 | 四 target 本地实现已存在；仍需原生 runner 证据。 |
| 安装版产品旅程 | 新用户能否走完支持的核心路径？ | 安装包内完成 Setup、模型连接、一次领养、一次回复、历史持久化和重启恢复。 | Driver 与原生 smoke 接线已实现；干净原生证据仍需外部运行。 |
| 真实升级测试 | 版本变化后用户状态是否仍在？ | 安装上一版本、写入受支持状态、安装候选、恢复并继续旅程。 | 当前只有同版本覆盖安装；缺少旧版到候选的证明。 |
| Soak 长稳测试 | 经过真实时间后是否仍稳定？ | PID/generation 连续性、CPU/RSS/句柄或 FD 趋势、组件健康、错误/崩溃增量和恢复。 | 脱敏趋势分类器已实现；目标主机观察仍需外部运行。 |

只有六层证据都绑定同一个候选 SHA 和准确安装包哈希时，它们才组成发布验证体系。它们仍
不能取消少量真实桌面人工验收。

兼容性、韧性、安全与证据身份是贯穿六层的发布维度，不是其中某一层的替代品。原生门禁还
必须证明支持主机矩阵、安装收据与系统 Shell 集成、生命周期竞态与恢复、无敏感信息的诊断，
以及从源码 SHA 到发布安装包的一条不可变证据链。

## 3. CI 的确定性模型边界

### 3.1 决策

安装版产品验收不能在打包 Core 内注入进程内假模型 Adapter。那样会绕过需要证明的
Provider 持久化、Endpoint 选择、HTTP 序列化、能力投影和发布装配。

CI 应当在临时 loopback 端口启动仓库拥有的**脚本化协议模型服务**，安装版应用仍通过用户
使用的版本化 Provider 与 Food 接口配置它：

```text
安装版 ElfieNest
  -> 持久化 Provider/Food 配置
  -> 生产模型 HTTP Adapter
  -> 127.0.0.1 脚本化模型服务
  -> 符合 Schema 的确定性回复
```

这个服务是远程模型边界的测试替身，不是第二套产品模型实现。它只由测试 job 启停，由系统
为端口 `0` 分配实际端口，只绑定 loopback，不访问公网，也绝不打进 ElfieNest 安装包。如果
生产 Provider 契约要求凭据，旅程会通过真实 Secret 边界保存一个固定的合成测试凭据；它不
是真实外部 Secret，但仍必须从全部证据中脱敏。

### 3.2 脚本化回复

服务按真实协议请求和声明的 Schema 路由，不能只用松散的“第几次调用”判断。最小场景是：

| 请求 | 确定性回复 | 验收断言 |
| --- | --- | --- |
| Provider inventory/probe | 为一个合格模型返回符合协议的模型清单、文本探测与结构化能力结果。 | Connection、准确 Endpoint 模型、Common Food 与 Emergency Food 通过持久化投影变成可执行状态。 |
| 领养候选回复 | 结构化回复包含已接受的候选 ID，以及当前候选字段（物种、生命阶段、地球年年龄、性别、外貌、性格和消息）；接受的候选还携带确定性的临时身份展示（原名、建议名和自我介绍）。 | 至少一位受邀候选走完确定性回复与 admission。 |
| Owner chat | 一条非空、第一人称 Elfie 完整回复。 | 请求穿过 WebSocket、App、NestSession、Brain 和生产模型 Adapter，且不会静默启用 Provider streaming。 |
| 未知 Schema、工具或 Endpoint | 测试服务明确失败。 | 新增模型行为不能静默得到通用成功回复。 |

候选生成、回复和接受选择仍由生产代码拥有，且不调用模型边界。脚本服务只用于 Provider
能力检查和 Owner 聊天。服务缺失、能力不合格、JSON 无效、出现未知请求或尝试 fallback 时，
门禁直接失败；绝不能因为没有模型就跳过核心旅程。

模型服务只记录请求类别、Schema 名、模型 ID、耗时、响应类别和通过/失败次数。上传证据中
不得保留 Prompt、Cookie、凭据或会话内容。

Harness 拥有模型服务 PID 与实际绑定端口，等待其就绪，并在成功与失败路径都证明其退出。
旅程必须达到产品契约要求的模型聚合状态，包括可执行的 Common 与 Emergency 路径；仅创建
一条 Provider 记录不算就绪。

### 3.3 能证明与不能证明的边界

该设计能确定性证明模型配置、能力选择、请求/响应传输、结构化解析、领养和聊天组合；不能
证明真实云 Provider 的回复质量、计费、额度或实时可用性。

可以另设一条非 PR 的**真实 Provider canary**，用有界最小请求发现日常连通性变化。它使用
受保护 Secret，不对 fork PR 运行，不记录 Secret 或 Prompt，并与确定性发布验收分开报告。
它不能替代 PMA-002 要求每次发布运行的代表性真实 Provider 能力矩阵。Provider 故障不能被
误报成安装包损坏。

## 4. 安装版产品旅程

每个原生 target 都针对全新的临时 `ELFIE_HOME` 和安装后可执行文件运行同一条 API 级旅程，
不得使用 `scripts/serve.py` 或进程内 `TestClient`。安装版子进程从 checkout 外的中性目录
启动，并移除源码开发环境变量；它的可执行文件、cwd、manifest source revision 与资源根都
必须指向安装包。每个 OS 至少有一个轮换场景使用包含空格和非 ASCII 字符的数据根路径。

1. 安装准确候选包，校验系统收据/注册、安装版版本、manifest、source revision、launcher
   与包拥有的 Shell 集成。
2. 启动安装版 Desktop Controller，要求到达 `WORLD_READY`，并取得 Controller、Core、
   Godot authority PID。
3. 读取 Setup 状态并要求 `need_setup=true`；使用签发的 Setup Cookie 与 CSRF Token，不绕过
   首次运行认证。
4. 完成 Owner、默认“不下载本地模型”选项和默认 Nest 草稿；确认安装并要求 Setup 完成。
5. Owner 登录，通过生产 API 配置 loopback 脚本 Provider、合成凭据、准确 Endpoint 模型、
   Common Food 与 Emergency Food。
6. 要求领养与聊天所需模型能力投影及预期模型聚合状态就绪；断言打包默认值没有复制到用户
   配置根，缺失资源也没有从源码 checkout 补齐。
7. 创建一组候选、发出邀请、校验接受的结构化回复并领养一只 Elfie。
8. 要求该 Elfie 同时出现在成员列表和运行中的 Nest/Runtime 投影。
9. 打开已认证的生产 Chat WebSocket，发送一条消息，收到一条非空完整 Elfie 回复，要求
   用户/Elfie 两条消息都写入持久历史，并只保留无敏感信息的 Provider/模型/角色执行收据。
10. 记录非敏感稳定 ID，正常停止，证明全部已记录自有进程退出。
11. 使用同一数据根重启；要求 `need_setup=false`、登录成功、同一 Elfie、同一历史和第二次
    成功回复。
12. 卸载应用；要求系统包收据/注册、包拥有文件、快捷方式、desktop entry、launcher 与
    PATH 修改消失，而所选用户数据根仍存在。
13. 停止脚本模型服务并证明没有测试自有进程残留。确认数据保留且证据脱敏后，Harness 只能
    删除它自己的临时数据根。

旅程只使用一个 Owner、一只 Elfie 和两轮聊天。用户管理、三只领养上限、全部 Setup 分支、
Provider Benchmark 和完整 UI 套件仍由聚焦测试负责；在这里重复只会增加耗时，不增加安装包
组合证据。

## 5. 平台覆盖矩阵

共享行为只做一次完整功能深度验证；安装器、进程、IPC、路径或平台适配可能改变结果的部分，
必须在对应原生 target 上验证。

原生验收开始前，发行范围必须列出准确支持的 OS 版本；Linux 还必须列出准确 DEB 发行版与
桌面会话。阶段 0 冻结的首个内测矩阵如下；它是验证范围，不自动扩大公开支持承诺：

| target | 固定 CI 镜像 | OS/会话 | 命名人工样本 |
| --- | --- | --- | --- |
| `darwin-arm64` | `macos-14` | macOS 14 arm64 | macOS 14.8.x arm64 |
| `darwin-x64` | `macos-15-intel` | macOS 15 x64 | macOS 14.8.x x64（若作为支持样本保留） |
| `win32-x64` | `windows-2025` | Windows Server 2025 runner；Windows 11 x64 用户样本另列 | Windows 11 x64 |
| `linux-x64` | `ubuntu-24.04` | Ubuntu 24.04 x64，Xvfb；Dedicated 无显示 | Ubuntu 24.04 GNOME/X11 或同等命名会话 |

Workflow 必须记录实际 runner image version、架构、OS build 和桌面/会话。以 `-latest` 结尾
的 runner label 不是支持策略；矩阵之外只能报告“未覆盖”，不能写成“支持”。

| 验证 | macOS arm64 | macOS x64 | Windows x64 | Linux x64 | 原因 |
| --- | --- | --- | --- | --- | --- |
| 共享单元/集成/完整产品套件 | — | — | — | 一次完整参考运行 | 产品逻辑共享；受影响聚焦测试仍正常执行。 |
| 安装包内容和原生安装 smoke | 必需 | 必需 | 必需 | 必需 | 安装格式、路径、权限和 authority 托管不同。 |
| 收据、launcher、快捷方式/PATH 与原生卸载 footprint | 必需 | 必需 | 必需 | 必需 | 静默安装成功不能证明系统集成与清理。 |
| 安装版 API 产品旅程和重启 | 必需 | 必需 | 必需 | 必需 | 数据根、权限、IPC 和包内资源受 target 影响。 |
| 完整 Setup→领养→聊天 UI 旅程 | — | — | — | Xvfb 下必需 | React 行为共享，一条完整浏览器路径足够。 |
| 最小安装版 Viewer 检查 | 必需 | 必需 | 必需 | 必需 | 证明原生激活、管理页 ready marker、无致命 Console/Crash 事件以及平台渲染的 Observer 表面。 |
| 托盘、激活、关闭和单实例 | 人工抽样 | 人工抽样 | 人工抽样 | 人工抽样 | Headless 会话无法可靠代表系统 Shell 集成。 |
| 交互式安装器与系统 launcher 路径 | 人工抽样 | 人工抽样 | 人工抽样 | 人工抽样 | 静默 CI 不覆盖 PKG/NSIS/包管理器界面及 Launchpad/开始菜单/应用菜单启动。 |
| 上一版本→候选升级 | 必需 | 必需 | 必需 | 必需 | 安装器替换和用户路径是原生差异。 |
| 真实 Provider canary | — | — | — | 一次定时参考运行 | Provider 行为与 OS 无关。 |
| 长时间 Soak | 选择一个 macOS 架构 | — | 必需 | 必需 | 每个 OS 一个架构覆盖长生命周期；两个 Mac 架构仍保留 smoke。 |
| 签名、公证、下载来源启动 | 公开发布时必需 | 公开发布时必需 | 公开发布时必需 | 仓库/包签名策略 | 需要最终签名产物和真实系统信任界面。 |

Linux 必须覆盖两种 World authority：Xvfb 下图形 Electron authority，以及完全无显示的
Dedicated headless authority。只检查文件存在不能替代 Dedicated 的真实启停。

## 6. 原生生命周期韧性矩阵

普通安装版旅程证明正常路径。独立的一次性目标主机矩阵保护服务生命周期契约要求的负向与
恢复行为，绝不针对维护者日常使用的正常安装。

| 场景 | 必需结果 | 最小原生覆盖 |
| --- | --- | --- |
| App 与安装版 CLI 并发启动；第二个 App 激活 | 只有一个 Controller 和 generation；目标升级或激活只附着，不产生重复 Core/Godot。 | 每个 OS |
| 启动期间 Stop、停止期间 Start、有界 Restart | 串行结果、类型化取消/`BUSY_STOPPING`、generation 不重叠、自有残留为零。 | Windows 与一个 POSIX target，全部 target 保留聚焦 Adapter 测试 |
| Godot authority 异常退出 | Core 如实保持 `CORE_READY`；认证恢复在预算内到达新的合法 World generation，且不形成循环。 | 每个 OS authority 模式，包括 Linux Dedicated |
| Core 异常退出 | Controller 记录故障且只做有界恢复；不产生重复 Controller/Core，不虚报 `WORLD_READY`。 | 每个 OS |
| Renderer/Viewer 进程失败 | Server 与 World 所有权不变；记录 Crash 证据，Viewer 可再次激活。 | 每个桌面 OS |
| 脚本模型 Endpoint 消失后恢复 | Backend 保持独立，模型健康与 Chat 失败类型化；不改网络设置即可在 Endpoint 恢复后成功。 | 一条共享参考场景加原生短 Soak 轮换 |
| 旧 receipt、PID 复用、无关端口占用和不兼容存活版本 | 不向无关进程发信号或附着，返回契约规定的类型化结果。 | 永久聚焦测试加 Windows/POSIX 原生样本 |
| 安装资源缺失/损坏 | 安装版 Preflight 给出修复/重装提示，绝不回退到 checkout。 | 每种包布局；每个 OS 一次原生执行 |
| 旧 Controller 运行时安装/更新候选 | 识别准确 Controller，要求有界收敛到 `OFFLINE`；无法停止时拒绝覆盖。 | 每个 OS 安装器 |
| Harness 失败路径清理 | 清理包、测试服务、临时凭据和测试自有进程，不触碰无关进程或用户数据。 | 每个原生 job |

故障注入只允许准确的测试自有 PID 与一次性数据根。任何场景都不得修改 VPN、代理、DNS、
hosts、路由、防火墙、TUN、PAC 或其他网络服务。

## 7. 真实升级验收

同版本重新安装仍是有价值的幂等性 smoke，但不能称为升级测试。真实升级使用两个不可变产物：

```text
安装上一受支持版本
  -> 使用脚本 Provider 完成 Setup
  -> 领养一只 Elfie 并写入聊天
  -> 旧 Controller 运行时首次尝试候选更新
  -> 要求安全拒绝或有界停止交接
  -> 安装器契约要求时再干净停止
  -> 安装准确候选包
  -> 要求版本发生变化
  -> 恢复 Owner、Provider/Food、Nest、Elfie 和历史
  -> 再发送一条消息
  -> 卸载且不删除用户数据
```

证据记录旧产物、候选产物、Tag/SHA、包哈希和数据 fixture 版本。源码生成的数据库 fixture
不能替代上一版本真实安装包。在尚未承诺支持公开旧版本时，先明确保留一个内测基线包作为
该门禁的起点。

门禁还必须证明 Provider credential reference 升级后仍可使用但不会暴露其值，以及打包默认
值已替换而用户配置得到保留。Downgrade 兼容和跨破坏性 Schema 发行的回滚不在这里隐含承诺；
只有另行批准相应产品契约后才进入范围。

## 8. Soak 与恢复验收

### 8.1 定时短 Soak

标准 runner 的定时任务可以让代表性安装版旅程持续 30–60 分钟，每五分钟采样：

- Controller/Core/Godot authority PID 和 generation；
- 状态、已达目标、failures 和组件健康；
- CPU、RSS、peak RSS、线程和进程数；
- Windows handle 数或 POSIX open FD 数；
- 模型请求、Chat 进度与确定性回复完成情况；
- error/fatal、异常退出和自动恢复增量；
- 新的相关崩溃报告；
- 日志、Crash Dump、数据库与整个数据根的大小趋势。

负载固定且有界：周期 status、低频确定性聊天、支持时的 Viewer 激活/关闭，以及一次受控重启。
阈值判断趋势和不连续变化，不根据一次瞬时 CPU 采样下结论。
阶段 0 冻结的首版预算为：warm-up 5 分钟；短 Soak 30 分钟、每 5 分钟采样；单次故障恢复
不超过 120 秒；意外重启上限为 0（仅允许一个事先声明的受控重启）；安装版进程树空闲 CPU
p95 不超过 25%，活动窗口 p95 不超过 100%；warm-up 后 peak RSS 增长不超过 15%，POSIX FD/
Windows handle 总量增长不超过 20%；诊断日志增长不超过 25 MiB/24 小时。24 小时主机 Soak
沿用同一阈值，并额外要求数据根增长能由固定 fixture 解释。任何超预算、未解释 generation
变化、authority 丢失或 fatal/error 增量都会保持 NAT 行开放。没有冻结预算的观察只能作为
特征数据，不能算发布门禁通过。

### 8.2 目标主机长 Soak

24 小时观察不能作为一个 GitHub-hosted job：GitHub-hosted 单 job
[最长六小时](https://docs.github.com/en/actions/reference/limits)。长期验收运行在受维护的
self-hosted 或目标测试机上，由 GitHub 负责调度分段和收集脱敏摘要。整个过程不得修改 VPN、
代理、DNS、防火墙、路由或其他网络服务。

两条 Lane 必须保持分离：

- **被动现场观察**严格只读，只采样已经安装并运行的用户会话；
- **主动测试主机 Soak**使用一次性数据根和脚本 Provider，可以产生有界 Chat 流量并执行已
  声明的恢复矩阵。

任何一条 Lane 的证据都不能静默冒充另一条。支持范围包含时，每个桌面 OS 还应在测试主机
记录一次 Sleep/Wake 或会话锁定恢复样本。

未解释的 PID/generation 变化、持续资源趋势、authority 丢失、Core 不健康、fatal/error
持续增长或安装版崩溃，都会让对应 Conformance 行保持开放。预期重启必须在动作前标记，并在
约定预算内恢复。

## 9. CI 频率与发布门

| 触发 | 选择的验证 | 发布行为 |
| --- | --- | --- |
| 普通 Pull Request | 聚焦单元/集成测试和受影响共享 Lane。 | 不发布。 |
| 发布敏感 Pull Request | 四 target 构建、安装 smoke、安装版产品旅程；一条共享 UI 旅程。 | 不发布，只保留准确 SHA 证据。 |
| Main post-submit/夜间 | 缺失的完整后盾 Lane、短 Soak、Linux Dedicated 路径和轮换恢复场景。 | 不发布。 |
| 手动候选、无 Tag | 完整四 target 验收及供审查的短期产物。 | 不发布。 |
| Tag 前最终候选 | 完整矩阵、真实升级、所需 Soak 摘要、人工 OS 清单，以及公开范围内签名门。 | 只有所有阻断行关闭后才能继续。 |
| Tag push | 只复用或重跑绑定 Tag SHA 的证据，只发布准确已验证产物和校验和。 | GitHub Release。 |

发布敏感路径包括安装器配置、release 脚本、Desktop 入口、生命周期/进程/IPC、包内资源、
Setup、Provider/Food、领养、聊天持久化、Godot Runtime 导出、Schema/存储契约和验证工具自身。
未知可执行影响 fail closed 到完整原生 Lane。

原生 job 使用冻结矩阵对应的固定 runner 镜像 label，不能依赖浮动 `-latest`。最终聚合 job
下载四份版本化 JSON 摘要，校验 Schema、target 唯一性、候选 SHA、安装包 SHA-256 与结果，
通过后才允许发布。Job 绿色本身不能替代发布证据。

## 10. 证据、安全与存储

每个门禁输出小型脱敏 JSON 摘要，记录候选 SHA、安装包 SHA-256、target、测试版本、固定
runner image/OS build、阶段耗时、稳定态、PID/generation 变化、资源聚合、请求类别和最终
结果。失败时可以增加有界日志
尾、截图与崩溃元数据。Token、Cookie、Provider 凭据、writer credential、Prompt 和用户
内容绝不上传。

证据 Schema 必须版本化并由独立验证器校验。脱敏测试注入已知哨兵凭据、Authorization Header、
Cookie 与 Prompt 内容，证明它们不会出现在摘要、日志尾、截图、文件名或上传 Artifact 元数据
中。成功和失败路径都执行清理与证据校验。

成本与保留规则：

- 公开仓库的普通原生门禁只使用标准 GitHub-hosted runner；larger runner 需要单独成本批准；
- 构建和测试尽量留在同一个原生 job，PR 安装包无需跨 job 上传；
- 成功 PR 只保留小型 JSON 摘要七天；
- 失败诊断有界保留七天；
- 完整安装包只为手动候选保留为 Actions artifact，通常三到七天；
- 已发布安装包进入 GitHub Release，不再作为长期 Actions artifact 重复保存；
- Cache 使用限定 key 和仓库额度；安装包与用户数据绝不进入 Cache；
- 昂贵原生 job 启动前取消或合并已过期 PR 运行。

截至 2026-08-25，GitHub 官方说明：公开仓库使用标准 GitHub-hosted runner
[不收执行分钟费用](https://docs.github.com/en/billing/concepts/product-billing/github-actions)。
Artifact 的存储和保留仍需主动控制，且
[larger runner 始终计费](https://docs.github.com/en/billing/reference/actions-runner-pricing)。
因此即使标准 runner 的执行分钟免费，也必须优化存储和队列时间。

## 11. 实施计划与收口顺序

每个阶段都形成可单独审查的本地改动和聚焦证据。完成阶段不产生 push、Pull Request、合并、
Tag 或发布授权。

### 阶段 0——冻结范围、主机矩阵与证据契约

- 列出准确的内测 OS 版本、Linux DEB 发行版/桌面会话及原生 runner 镜像。
- 冻结版本化证据 Schema、包/SHA 聚合规则、长短 Soak 预算和人工验收模板。
- 将每个 NAT 行映射到现有 LFC、CFG 与 PMA 契约行。

**门禁：**任何原生结论都不再使用未定义范围的“Windows”“Linux”“macOS”“稳定”或“通过”。

### 阶段 1——脚本化模型边界

- 实现 loopback 协议服务和按 Schema 路由的脚本回复。
- 覆盖 inventory/probe、准确能力证据、Common/Emergency 路由、确定性领养回复、完整回复 Chat、
  畸形请求和未知请求。
- 使用合成凭据走生产 Secret Store，并证明服务不能绑定非 loopback、访问外网或记录敏感字段。

**门禁：**生产 Provider/模型 Adapter 对该服务的测试通过，未知 Schema fail closed。

### 阶段 2——安装版产品旅程 Driver

- 从现有诊断流程提取可复用 HTTP/WebSocket Session，但不能把源码 `serve.py` 当作安装证据。
- 针对安装包和临时数据根驱动 Setup、Provider/Food、领养、聊天与重启。
- 从中性 cwd 启动并移除源码环境；校验收据、安装资源来源、Setup Token/CSRF、历史与执行收据。
- 输出脱敏类型化证据，在失败时保留诊断，并在成功/失败路径清理所有测试自有进程。

**门禁：**一个一次性本地/参考 target 不直接写数据库即可完成旅程和重启恢复。

### 阶段 3——原生包与主机集成

- 在 `darwin-arm64`、`darwin-x64`、`win32-x64`、`linux-x64` 运行旅程。
- 增加发布敏感 PR 路由和不发布的手动候选入口。
- 校验系统收据、快捷方式/desktop entry/PATH、普通用户启动、卸载 footprint，并增加 Linux
  Dedicated 无显示真实生命周期场景。

**门禁：**四个准确包哈希都通过原生 smoke 与安装版旅程；Linux 同时通过图形和 Dedicated
authority。

### 阶段 4——生命周期恢复矩阵

- 实现重复启动、命令竞态、Core/Godot/Renderer 恢复、模型断开、旧身份、端口冲突与安装版
  Preflight 场景。
- 在旧 Controller 运行时验证更新交接。
- 故障注入限定准确 PID、一次性数据根和原生 target。

**门禁：**适用的 LFC-001/002/003/005/006/007/008/009/010 residual 具备可重放原生证据，
否则继续明确保持开放。

### 阶段 5——UI 验收

- 在 Linux Xvfb 自动化一条完整 Setup→模型配置→领养→聊天 UI 路径。
- 每个原生 target 增加最小安装版 Viewer 非白屏/激活检查。
- 失败时上传有界截图与 Console 诊断。

**门禁：**共享 UI 旅程通过，每个 target 都证明 Viewer 能启动；托盘/系统行为继续明确人工。

### 阶段 6——真实升级与持久化

- 选择不可变的上一受支持安装包。
- 只通过安装版产品旅程写入状态。
- 升级到候选，证明持续聊天和数据保留。

**门禁：**四个 target 都通过旧版到候选恢复。

### 阶段 7——证据、CI 身份与成本控制

- 每份摘要绑定候选 SHA 和安装包 SHA-256。
- 增加保留期、取消、并发和仅失败上传规则。
- 增加独立四 target 证据聚合、固定 runner 镜像、Actions 使用量/存储审查步骤和预算告警指引。

**门禁：**失败证据足够诊断且不含敏感信息，普通 PR 不保留原生安装包。

### 阶段 8——Soak 与资源预算

- 先冻结预算，再增加 30–60 分钟定时负载、趋势分类器和有界数据/日志增长检查。
- 在 macOS、Windows、Linux 目标主机分别完成 24 小时观察。
- 分开被动只读观察与主动一次性主机 Soak；分类每次重启、generation 变化、错误增量和崩溃。

**门禁：**约定观察窗结束且没有未解释的生命周期/资源趋势；否则对应行保持开放。

### 阶段 9——最终原生与公开发行收口

- 每个 OS 完成真实桌面托盘/窗口/单实例人工检查。
- 完成交互式安装器/系统 launcher 与支持主机样本。
- 运行 PMA-002 代表性真实 Provider 能力矩阵；最小 canary 仍只作为可用性信号。
- 只有明确授权公开发布时才加入签名、公证、quarantine/SmartScreen 与校验和门禁。
- 审查所有 Conformance 行并保留尚未完成的外部证据。

**门禁：**预定发行范围没有开放的 P0 或 release-blocking 原生条目。

## 12. 完整定义

只有满足以下条件，验证体系才对内部 Beta 完整：

- 共享完整功能套件及选中的架构/安全门通过；
- 准确支持主机/runner 范围与资源/恢复预算已冻结；
- 四个安装包 target 都通过原生安装 smoke；
- 每个 target 都证明收据/Shell 集成、普通用户启动和干净移除包 footprint；
- 四个 target 都通过安装版 Setup/领养/聊天/重启旅程；
- 一条共享 UI 旅程和四个最小原生 Viewer 检查通过；
- 选择的真实升级基线在四个 target 上通过；
- macOS、Windows、Linux 都有已分类的 Soak 证据；
- 原生生命周期韧性矩阵和 PMA-002 代表性真实 Provider 矩阵都有当前证据；
- 人工 OS 集成 residual 已记录；
- 准确候选/包身份和脱敏证据已保留；
- 适用 Conformance 行全部关闭，或按发行范围明确延期。

这是有力的发布信心边界，不表示已经测试每种设备、驱动、桌面环境、安全软件或真实 Provider。
