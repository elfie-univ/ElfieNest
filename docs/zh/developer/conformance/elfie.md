# Elfie 内部架构一致性

> [Elfie 内部架构契约](../contracts/elfie)的开放迁移台账。它记录已关闭切片与当前精确缺口，不降低
> 目标。ELF-001 至 ELF-009 记录 Ports/Adapters 迁移；ELF-010 之后记录当前 2.6 契约采用的生命系统工作。

## 一致性收口

| ID | 严重度 | 状态 | 当前偏差 | 关闭条件 | 证据 |
| --- | --- | --- | --- | --- | --- |
| ELF-001 | P1 | closed | App 编排与接口生产调用方只使用受控的 `elfie.public`/`nest.public` 表面，深层领域导入已由机器门禁保护。 | `Elfie`/`ElfieFactory` 成为唯一生产聚合入口，只暴露批准的类型化能力，并删除和拦截深层调用方导入。 | target=ELF-001 Facade；inventory=Elfie 生产调用方；references=深层导入扫描；verification=Factory 与架构测试；residuals=none |
| ELF-002 | P0 | closed | Brain 在 `elfie/brain/reasoning/skill_port.py` 拥有强类型 Skill 边界；官方流程源以 `config/brain/skills/<name>/SKILL.md` 内置，原伪 Skill 包已删除。 | 元数据先公开，再通过只读原生 `load_skill` 操作加载；frontmatter/名称/正文校验、目录隔离和不执行脚本有聚焦测试。Skill 不是 Tool 定义，也不授予 Tool 权限。 | target=ELF-002 Skill 所有权；inventory=skill_port.py 与 config/brain/skills；references=旧包和标记协议扫描；verification=Bundled Catalog 与 Reasoning 测试；residuals=none |
| ELF-003 | P0 | closed | Brain 已分别暴露强类型 `FoodPort`、`ModelPort`、`ToolPort`；可执行 Tool 定义显式位于 Infrastructure 注册表，Bootstrap 向模型 Adapter 注入限定作用域的原生 Tool 视图。 | `ToolDefinition`/`ToolCall`/`ToolRequest`/`ToolResult` 是强类型契约，Adapter 保留全局与每只 Elfie 的安全否决，普通和结构化路径使用原生 Provider 往返，历史标记循环已移除。 | target=ELF-003 认知 Port；inventory=Brain Port、Tool 注册表与 Bootstrap Adapter；references=工具边界扫描；verification=模型/工具/验证契约测试；residuals=none |
| ELF-004 | P0 | closed | `elfie/brain/memory/` 已移除 SQLite/Schema/Record 映射；语义算法依赖 `MemoryStorePort` 与类型化 Memory 记录。 | Brain Memory 测试使用类型化内存 SQLite Adapter，持久化测试位于 Infrastructure，系统技术 import 精确基线清零，最终知识库重新打开行为仍有覆盖。 | target=ELF-004 Memory 所有权；inventory=elfie/brain/memory 与 Infrastructure 持久化；references=技术 import 基线；verification=类型化 Memory 重开测试；residuals=none |
| ELF-005 | P0 | closed | Profile 加载和路径解析由 Infrastructure/Bootstrap 拥有；`assemble_profile` 与 `ElfieFactory` 只接收类型化档案/依赖。 | `ProfileStorePort` 仍是领域边界，打包默认值来自资源，Elfie 初始化和 Factory API 不再接收存储路径或具体 Profile Repository。 | target=ELF-005 Profile 边界；inventory=Profile Store 与 Bootstrap；references=路径/import 扫描；verification=Profile round-trip 测试；residuals=none |
| ELF-006 | P0 | closed | 身体语义、Registry 和 Binding 留在 Elfie，Godot/设备/产品托管实现位于领域外；Elfie 仅保留确定性、无 I/O 的 Headless 测试身体。旧解剖与步态分支已删除。 | 多身体身份/绑定与类型化事件/回执测试通过；Body 实现不导入传输、凭据、进程所有权或 Nest 世界事实；旧分支和引用扫描为空。 | target=ELF-006 Body authority；inventory=elfie/body 与身体 Adapter；references=身体依赖扫描；verification=身体切换测试、旧路径扫描；residuals=none |
| ELF-007 | P0 | closed | `elfie/communication/` 只拥有标准 Envelope、策略、Hub/Router、有界 Inbox/Outbox 与注入的渠道 Port；微信/Telegram 和消息投递传输位于 `infrastructure/communication/`，版本化且认证的 App 会话/WebSocket 路由在进入投递 Facade 前解析成员与目标。 | 保持通信 Port/Adapter 方向、认证入站、身份/去重和投递顺序测试通过。 | target=ELF-007 Communication authority；inventory=通信与投递 Adapter；references=入站身份扫描；verification=去重/顺序测试；residuals=none |
| ELF-008 | P1 | closed | `ElfieFactory` 已成为围绕不可变 `ElfieAssembly` 的类型化领域 Builder；存储路径、Godot API 和分阶段 Runtime 配置在调用前解析。 | Factory create/restore 测试通过，返回的聚合完整但未启动，生产组合根仍由 Bootstrap 拥有。 | target=ELF-008 Factory composition；inventory=elfie/factory 与 Bootstrap；references=组合根扫描；verification=assembly/restore 测试；residuals=none |
| ELF-009 | P1 | closed | Profile、Body、Communication、Nest Session、Runtime observation 及 Infrastructure Port 模型的公开边界均使用命名不可变模型或受限 JSON 值。永久 Port 棘轮拒绝 `Any`、`object` 和具体对等 Adapter 签名；身体/通信/Bootstrap 证据已有机器门禁。 | 保持严格 Port 棘轮和证据通过；内部算法局部映射不属于公开边界契约。 | target=ELF-009 typed boundaries；inventory=公开 Port 模块；references=Port 棘轮；verification=架构模型测试；residuals=none |
| ELF-010 | P0 | closed | `ElfieProfile` 现在只包含不可变身份、来源、外貌和具身事实。Selfhood 与 Energy seed 由 `elfie/brain/` 拥有，通过 Infrastructure 分开持久化并由 Bootstrap/Factory 加载；混合 Profile 默认值和三个宽字段已删除。 | 所有可变值均由 Selfhood/Energy owner 接收，不保留 fallback 或双 authority。 | target=Elfie Profile/Selfhood/Energy 所有权条款；inventory=elfie/profile、elfie/brain/selfhood、elfie/brain/energy、领养与恢复路径；references=无 Profile 人格/能力/系统限制字段或旧默认值；verification=Selfhood、Factory、领养、Lab 和架构套件通过；residuals=none |
| ELF-011 | P0 | closed | 私有认知协调与上下文组装已经归 Brain；类型化单域 Turn 和宿主强制响应范围已建立，旧根认知文件已删除。 | Brain 生命周期、Lane、Scope 和决策边界聚焦测试通过；Elfie Lab 展示通信闭环的来源域、Scope、决定与投递回执。后续 Brain 能力扩展必须保持这一边界门禁。 | target=ELF-011 Brain Turn 所有权；inventory=elfie/brain/runtime 与 Lab；references=根认知扫描；verification=Brain lifecycle/Lab 测试；residuals=更新后的 Activity 来源域和具身控制要求由 ELF-018 跟踪 |
| ELF-012 | P0 | closed | Body Registry/Binding 现在为当前身体分配 authority generation；NervousSystem 只接收当前身体代际，输出执行器拒绝切换后的旧回执，中断也回到原身体；失败切换保留旧身体。 | 阶段三 Headless/真实 Godot 验收通过；身体切换、旧事件拒绝、旧回执拒绝、连接失败回滚以及唯一当前身体均有聚焦测试和真实 `world_ready`/`intent_terminal` 证据。 | target=ELF-012 唯一身体 authority；inventory=身体 Registry/Binding 与 Godot Adapter；references=generation guard；verification=身体切换和 Godot E2E 测试；residuals=none |
| ELF-013 | P1 | closed | `elfie/genesis/` 现在拥有经过校验的一次性创建 Bundle、初始化 Manifest、有界人生补全计划和幂等记忆提交器。领养流程把 Profile、Brain Selfhood/Energy seed 与 Genesis 记忆各写入最终所有者一次；普通 `Elfie` 运行期只接收类型化 seed。 | Genesis 创建临时 Bundle 并在最终所有者提交后退出。 | target=Genesis 一次性创建条款；inventory=elfie/genesis、initialization、领养 workspace 与 Brain seed Adapter；references=Bundle 校验、Manifest 重复保护和最终所有者持久化；verification=Genesis、领养、持久化和 Lab 套件通过；residuals=none |
| ELF-014 | P0 | closed | Brain 现在拥有 Persistent Activity 语义 Port 和输出边界；Lab 为每只 Elfie 注入独立 SQLite Adapter。已校验 Draft 幂等提交，等待任务通过类型化 Activity 状态事件唤醒，Communication/Embodied 子结果结算 Activity 进度，重启后不重复投递。 | Activity、持久化和 Lab 聚焦测试覆盖跨回合状态、唤醒、Scope 校验、回执终态、重启恢复和无重复投递。 | target=ELF-014 Activity 所有权；inventory=Brain Activity 与 Lab Adapter；references=回执结算；verification=Activity/持久化/重启测试；residuals=当前来源域迁移由 ELF-018 跟踪 |
| ELF-015 | P1 | closed | 首个有界恢复 Motivation 驱力和有界 Cognitive Consolidation 切片现在都有 Brain 所有者与 Lab 证据。整理工作仅处理睡眠窗口中的 Episodic 记忆，不能产生外部副作用；更多主动驱力与成长仍是独立范围。 | Motivation 以冷却/满足状态控制候选；Cognitive Consolidation 以 Checkpoint 候选和固定经历预算形成 Activity 候选，并且只有整理回执完成后才提交 Memory。Brain/Lab 聚焦测试与 Web build 通过；夜间路径不创建消息、身体动作或 Activity。 | target=ELF-015 有界自主工作；inventory=Motivation 与 Consolidation；references=Activity-only 输出 guard；verification=Brain/Lab 与 Web 测试；residuals=当前来源域迁移由 ELF-018 跟踪 |
| ELF-016 | P0 | closed | Brain 已拥有单个 Turn 内有界的 `ReasoningRun`：原生 Model/Skill/Tool 调用、真实 Observation、验证和完成/失败收束均在 Brain 内部完成，外部行动仍只能由结算后的决定进入既有边界。 | 聚焦 Brain/Lab 测试展示原生 Tool→Observation 和流程 Skill 加载，标记文本不再是执行协议，虚假外部执行声明不产生外部回执，模型不可用进入明确 `failed/no_op`，紧急事件形成独立新 Turn。纯文本 Provider 输出保持惰性/降级。 | target=ELF-016 有界推理；inventory=Brain reasoning 与原生 Model/Skill/Tool Observation loop；references=外部决定 guard；verification=Reasoning/Lab/原生验证测试；residuals=none |
| ELF-017 | P0 | closed | Orientation 与 Selfhood 已成为独立 authority；Energy、Memory、Orientation、Selfhood、Motivation 与 Cognitive Consolidation 进入统一连续状态 Checkpoint；短时 Emotion 明确只存在于进程内，并在睡眠或重启时回到人格基线。自我定位从当前 Body generation、会话、地点与 Activity 生成候选，并在 Turn Settlement 中提交。 | 聚焦状态、结算和跨模块恢复测试覆盖明确所有者、来源/版本规则、长期 owner 恢复、Emotion 进程内重启、陈旧 Checkpoint 拒绝，以及单轮消息不能改写人格/规范。 | target=ELF-017 连续生命状态；inventory=Brain 状态 owner 与 continuity；references=checkpoint/settlement guard 与 ADR-0030；verification=状态与跨模块恢复测试；residuals=none |
| ELF-018 | P0 | open | 三个 Brain 域和动态能力目录链路已经实现；真实 Godot 房间已经在第一阶段 Brain-owned Mock 模式下证明移动、Body 终态回传、定向听觉、语义视觉、触觉和具身位置。 | 保持恰好 `Communication`/`Embodied`/`Activity`；`ACCEPTED`/`STARTED` 只留在账本；通过 EventWorkspace 发布一个具身终态和兼容身体事实；单独补齐模型驱动控制证据。听觉/视觉/触觉/位置场景已经有证据。 | target=ADR-0033 与 Brain/Elfie/System/Nest-Godot 1.7/2.4/1.10/1.2 契约；inventory=Brain workspace/决定类型、Body/NervousSystem、Godot Adapter/Transport/Gateway 与执行计划；references=动态能力目录、域化回执、Brain-owned Mock 控制器和真实房间 E2E harness；verification=相关 Python 回归 825/825、架构套件 229/229；真实 Godot 房间 E2E `build/e2e/brain-godot-live` 有场景清单、`world_ready`、实际移动、`speech_reach`、`visual_observation`、定向 Body 输入和动作终态；另有 compile/lint；residuals=外部物理身体、第二版异步提交/回执流以及模型驱动具身控制仍未闭合 |

## Genesis v1 差距

| ID | 严重度 | 状态 | 当前偏差 | 关闭条件 | 证据 |
| --- | --- | --- | --- | --- | --- |
| ELF-019 | P0 | open | 已发布的 `config/genesis/` 资料包现为唯一创建来源，旧生产路径已移除（CFG-006 已关闭）。剩余缺口是端到端人生可行性、接受输入/版本绑定、完整个人知识/关系/Episode/Selfhood 投影，以及由 Nest 确认的入驻。当前先持久化 Genesis 结果，再尝试 Runtime 注册；Runtime 恢复独立进行。 | 在现有单一创建链上完成下方剩余语义与入驻门禁；保留断源恢复、已激活资料包绑定及最终所有者 authority，不增加第二来源路径。 | target=Elfie 2.6、Application 1.12、Configuration 1.7、ADR-0033/0040；inventory=Bootstrap 源、Adoption 候选/会话、Genesis 编译/初始化、Memory、Admission、Nest、UI；references=`config/genesis/program.yaml`、ADR-0033/0040、`app_wiring/adoption.py`、`compiler.py`、`initializer.py`、`resident_admission/service.py`；verification=聚焦现状测试、资料包/可行性、五步语义、Memory Recall 和中断入驻验收；residuals=下方七个剩余收口切片。 |

**收口状态：** open
## 机器覆盖

系统层扫描器禁止反向根导入并精确棘轮 Elfie 直接技术 import；Elfie 技术 import 精确
基线现已清零。聚焦认知测试保护身体/通信公开契约、严格 Pydantic 边界、Facade 大小、
依赖方向和 Brain 所有的 ToolPort 面；Memory Fake 测试、Infrastructure 持久化测试以及
模型/工具端到端路径为已关闭切片提供证据。

早期 Ports/Adapters 与生命系统条目继续保留既有证据；既有契约在 ELF-010、ELF-013 中
的 Profile/Genesis 所有权缺口已在当前 v0.2 结构实现中关闭；Genesis v1 完整行为仍由
ELF-019 跟踪。真实 workspace 政策和外部模型/具身验收仍是独立门禁；具身控制缺口见
ELF-018。本台账不是第二个运行时 authority，也不授权新增兼容字段。2.6 契约复用这些边界
和既有 Baseline，不创建第二套历史债务 Baseline。

## 已完成的 Ports/Adapters 顺序

1. 盘点并冻结 `Elfie`/`ElfieFactory` 公开面；
2. 把 Skills 移入 Brain，分离授权与执行；
3. 以 Food、模型、工具 Port 替换宽 Runtime 桥；
4. 提取 Memory 与 Profile 持久化 Adapter；
5. 在保留稳定 Body Port 的前提下提取身体技术 Adapter；
6. 在保留标准 Envelope 与渠道路由的前提下提取通信平台 Adapter；
7. 完成 Factory/Bootstrap 装配并删除生产深层导入；
8. 关闭严格模型、Fake、Adapter 与端到端证据缺口。

每一步都是独立获批的垂直切片：定义或冻结使用方 Port，实现并注入一个 Adapter，迁移
全部调用方，删除旧路径，再只关闭对应条目。

## 生命系统实现顺序

1. Brain Kernel 与通信生命闭环关闭 ELF-011 的单域 Turn 和根认知所有权部分；
2. 思考中枢通过有界 Model/Skill/Tool Observation 关闭 ELF-016，不增加新的外部行动线路；
3. 虚拟具身闭环为第一具生产身体关闭 ELF-012 的唯一当前身体 authority；
4. 连续生命状态已关闭 ELF-017 并建立 Selfhood/Energy/Orientation 所有者；严格 Profile 清理已在 ELF-010 的 v0.2 结构切片中关闭；
5. 跨回合活动在 Motivation 可以创建主动工作之前关闭 ELF-014；
6. 有界 Motivation 与 Cognitive Consolidation 关闭 ELF-015；
7. Genesis 的 v0.2 结构切片已关闭 ELF-013：语义编译归位 `elfie/genesis`，创建输入仅存在于事务内，并具备最终 owner/断源恢复证据。

## Genesis v1 收口顺序

Genesis v1 收口顺序如下。CFG-006 已关闭；其余项目仍是独立开放的实施门：

1. **强类型资料与单路径切换（CFG-006；已关闭）**：已发布的
   `config/genesis/program.yaml` 清单及其 18 个成员已接入创建/可用性强类型视图。
   Adoption 与 Genesis 只使用这一来源；旧生产配置已移除，Myelle 仍以 draft 排除。
   验收：资料包完整性、封闭清单、发行 manifest 覆盖，以及持久化 Adoption/Memory E2E。
2. **地理与人生可行性基础（`elfie/genesis`）**：使用 100 格（83 格可出生）、物种
   允许区、16 条有序旱路链、同小区相邻小路及 4 个登记渡口；陆路每边 2 步行日，
   水路每边 3 水行日。验收：已知路径、湖心岛普通渡运、湖面旱路阻断、云冠城不可访问、
   未登记地下城入口及各可用年龄段的出生/照护/学习/赴地可行路径均可核对；不能用
   直线或最近点造路。
3. **候选门（Adoption、`GenesisEngine`）**：校验硬选择和支持的年龄/外貌，每批最多
   12 次完整候选尝试，现有内部 96 次外貌提案不另计；尽量形成五位不同且各有合法
   人生见证的候选；五个问卷答案只影响人格。保留邀请 1–3 位及确定性回复。
   验收：五位差异、年龄至少 2 岁、无解说明、不可行候选不展示、Myelle draft 不开放。
4. **接受冻结（Adoption、Admission 预约）**：在私有持久封套中原子绑定候选/名字、
   资料包/策略/编译器版本、种子、时间锚和幂等键；名字按 Unicode、控制字符及保留字符
   规则作为数据校验。已公布回复不改写；重启或候选过期
   不得重造已接受身份。验收：重复/变更点击、过期、撤包和重启只能继续或拒绝同一预约。
5. **人生轨迹（`elfie/genesis/compiler.py`）**：在允许区域中均匀选区，再在区内均匀
   选出生格；按时间建立私人住所、适龄照护、适用时的一名真实师傅与学徒年限、职业及
   实际行程。可达不等于去过；赴地要本人同意、年龄至少 2 岁和 3 个本地日简单准备。
   验收：边界格、缺照护/师傅/路线和幼体场景可解释地失败；所选路线与事件槽位均合法。
6. **个人计划（`elfie/genesis`、Selfhood）**：按取得时证据判断四类知识条件，难度只
   抽一次，居民段落全取或不取；从实际生活生成人物/关系、必要完整 Episode、个人生活
   事实与闭集 Selfhood 映射。经历通常至少五段，幼体例外，不凑数；不凑人数或默认人格。
   模型只润色已固定事实。验收：无结果自证前提、虚造路人、幼体凑经历、生活事实丢失
   或未知人格映射。
7. **Bundle、Memory 与确定性（`elfie/genesis/initializer.py`）**：联合校验身份年龄、
   时序、路网、关系、知识、Selfhood 和所有者引用；采用版本化规范 SHA-256 分域抽样和
   有界依赖回溯。只用现有 Memory 原子 source-first 入口提交知识、关系、经历三类，
   索引各归真实证据，不默认挂第一段经历。验收：固定向量、重试等价、失败原子性、
   断源重开、Recall 不泄露未取得事实或技术标记。
8. **入驻事务（`resident_admission`、Adoption、Nest）**：现有状态机补真实 Nest 床位
   预约/确认、执行栅栏、撤包顺序、补偿、状态查询与取消；三方结果齐备后 `committed`
   才成为激活栅栏，Runtime 连接随后进行。验收：并发/重复调用、各崩溃窗口、发布前后
   取消及部分结果不可见。
每片先刻画现有路径，再只改所属 owner；不加回退、双读、第二生成器或 Profile/Canon
运行期依赖。ELF-013 的结构切片继续关闭；ELF-019 仍待剩余生成与入驻证据后收口。
CFG-006 已在[配置管理台账](configuration-management)中关闭。
真实既有 workspace 迁移与 Myelle 角色资产完成是独立范围，不藏进 Genesis v1 切换。
