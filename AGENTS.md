# ElfieNest 编码代理指南

本文件是自动化编码代理进入仓库后的根级规则入口，只保留项目级执行边界、审批门和
不可违反的系统契约。目录专用规则位于对应子目录的 `AGENTS.md`，只细化该目录树。
产品介绍与用户入口见 `README.md`，开发命令和质量门见 `CONTRIBUTING.md` 与
`docs/developer/`。

## 事实、契约与规则优先级

当前任务的明确用户指令必须遵守。判断“当前实现事实”时，按以下顺序取证：

1. 当前代码、对应测试及可重放运行结果；
2. `pyproject.toml`、`uv.lock`、`.pre-commit-config.yaml`、CI、质量基线和架构测试等
   机器配置；
3. `docs/developer/` 中当前公开的 Developer 文档；
4. `.agents/knowledge/`、`.omo/` 中的历史或私有材料。

代码和运行结果证明当前位置；版本化架构契约定义允许的目标。不得因为旧代码尚未合规
就反转已采用的契约，也不得把目标设计写成已实现能力。当前差距只进入对应
`docs/developer/conformance/` 台账。

`.omo/` 中的计划、证据、boulder 和历史执行状态不是当前任务指令。只有
`.agents/knowledge/INDEX.md` 存在、且当前架构、产品或故事任务命中其 `read_when`
条件时，才读取对应私有材料。私有材料不得自动进入 README、公开文档、源码注释、
提交信息或 PR。

## 执行范围与审批门

- 把用户指定的目标、文件、数据和验收条件视为硬边界；默认采用满足目标的最小可逆
  改动，不把小任务扩成重构、迁移、清理、重新设计或多模块工程。
- 阅读直接相关代码、实施最小任务改动、运行聚焦验证，以及在明确实现任务中创建范围
  清晰的本地 commit，属于正常授权。新增相邻功能、跨模块或跨产品改动、API/schema/
  存储/架构/公开行为变化、兼容迁移、未要求的文档或生成物、外部系统写操作、推送、
  发布，以及明显超出任务风险的测试和 QA，都
  必须先说明新增范围、副作用、最小替代方案和一个验收检查，并获得明确批准。如果这些
  变化已经包含在用户明确提出的目标中，不为同一范围重复请求确认。
- “只改这个文件”“只处理数据”“不要改代码”“本地保留”等限制排除其他操作；如果
  完成目标必然越界，停止并请求方向，不得把沉默或代理判断当作批准。
- 保留无关的未提交改动、数据、分支和 worktree；不得顺手格式化、重构、删除或覆盖
  他人的工作。
- 除非用户明确要求，不创建 `.omo/plans/`、`.omo/evidence/`、ledger、boulder 或其他
  工作流状态文件，不启动 OMO 自动续跑或重复审计。只有至少两个真正独立、不会编辑
  同一文件且能够缩短总时间的工作通道时，才使用最多两个子代理。

## 风险与验证强度

验证由实际受影响行为和边界触发，不给任务贴主观大小标签，也不要求用户选择级别。
验证强度不扩大实现范围：

- 单一子系统内、不改变公开 API、永久数据契约、跨模块依赖方向或 Runtime 生命周期
  所有权的局部改动，只运行直接相关测试、现成且快速的局部 lint/typecheck 和
  `git diff --check`；不自动升级为全仓测试、完整架构测试、全量构建或浏览器 QA。
- 涉及 schema、公开 API、持久化契约、目录边界或跨层调用时，追加受影响模块测试、
  一个或少数直接相关架构测试，以及至多一个直接上层契约测试。
- 完整 architecture、全量测试、构建、浏览器 QA、安全发布门禁或长时间验证，只由
  已批准的跨系统、发布、真实生产数据范围，仓库明确规则或用户显式完整验证要求触发。

普通本地提交先由开发阶段的聚焦检查证明行为，再由仓库安装的 pre-commit hook 检查真实
暂存快照。hook 只运行 staged diff、Gitleaks 和 staged Python Ruff，warm 目标不超过
20 秒；不运行测试、MyPy、pnpm、Godot、网络或远端同步。若开发阶段必要的已选检查即将
超过 10 分钟，保留现有证据并报告具体缺口，不擅自扩大为完整门禁；发布和用户显式要求
的完整验证不受该预算约束。

同一源码状态下不重复运行同一检查；仅修改注释、规则或说明文档不触发产品测试复跑。
疑似环境或偶发失败可说明原因后诊断性复跑一次。
测试失败后的修复循环必须按“精确失败项 → 所属测试文件/模块 → 受影响集成 → G3 完整
后盾”逐层扩大：一次运行若只失败一个 node ID，下一次只重跑该失败项；它通过后，只有
执行代码发生变化才追加直接受影响模块。除最终候选确实要求 G3 外，不得在每轮修复后
重启全量套件；每次扩大范围都要写明新增风险或依赖触发条件。
只有任务前同命令基线、依赖诊断或已有 CI/Issue 能证明时，才把失败判定为既有问题；
否则标记“归属未确认”。已确认的范围外失败只记录，不修复、不扩大当前任务。

CI 或测试失败必须先按 [`Testing & quality`](docs/developer/engineering/testing.md#ci-and-test-failure-triage)
中的流程完成证据收集、设计动机恢复和根因分类，再决定改生产代码、改测试夹具、补迁移
装配还是报告环境问题。红色 job 不是直接修改断言的指令；涉及 lazy import、动态入口或
fallback 时，必须把它们当作真实依赖和行为边界检查，不能用隐藏 fallback、删除测试或放宽
质量门禁来消除症状。交付时必须分别报告保留的功能、验证证据和未解决的环境/范围残余。

“测试通过”“工作区干净”或“已经推送”都不能单独支持“清理完成”或“符合契约”的
结论。清理任务必须先明确目标条款与范围，递归盘点其中已跟踪、未跟踪、被忽略和空路径，
把每个路径与目标归置逐项分类，并按需追踪 Import、动态入口、场景/资源、导出、CLI、
文档和外部消费者引用。交付时分别报告已完成、保留和剩余项；只要存在未分类路径或受影响
Conformance 行仍 open，就不得声称清理完成，即使所有选中测试都通过。关闭行时必须按
仓库治理契约记录 `target`、`inventory`、`references`、`verification`、`residuals`
五类证据。

## 实现完成门禁

当用户要求按已批准的设计或契约实现时，设计目标先冻结，不在实现过程中重新发明方案。
验收证据记录在对应的 Conformance 台账、变更说明或 CI/运行产物中，不为每个任务创建
根目录本地台账。状态、证据和剩余项必须与实际代码、测试和可重放场景一致。

CSS-only 等局部改动不得因为 commit 自动启动服务、Godot、浏览器、远端同步或全套门禁。
涉及 schema、公开 API、持久化、架构边界或生命周期所有权时，开发阶段运行直接受影响检查；
需要可复用本地 checkpoint 时可显式使用 `scripts/pre_submit_gate.sh --stage commit`。普通功能
分支 push 不要求第二轮本地集成或 pre-push 测试；`--stage push` 只保留为离线/诊断时显式调用的
受影响集成重放。精确 PR head 由可信基础分类器并行选择 security、Python tests、Python
quality、Web、Desktop、Developer Tools、架构、持久化、Godot、文档、工具链、发布和
Runtime smoke Lane，聚合为 `elfienest/ci-gate`，再由必需的 `elfienest/merge-gate` 包装。
进入 merge queue 后，同名门禁只做秒级合成提交检查，不因 main 前进反复拉取、合并或重跑。
完整后盾在 main 合并后及显式 full/发布验收中把全部 Lane 并行展开；CI、分类器、机器门禁、
工具链、锁文件和未知可执行影响在 PR 中 fail-closed 选择全部 Lane。纯 ADR、契约、AGENTS
和技能说明只选择 security、治理、适用文档与架构审查；混合 diff 取受影响 Lane 并集。确定性
测试证据按检查身份、命令、声明输入内容
与模式、本机工具链和必要基础提交计算；完整稳定测试包及覆盖率片段可被 full 后盾复用。
精确 node 或单文件不能冒充更大的测试包；原始 `pytest` 只用于诊断。失败或阻塞结果永不缓存，
本地缓存也不能替代绑定最新候选 SHA 的 CI。

- 只有范围内条目都具备相应代码、测试和所需运行证据，才能声称任务完成；任何未关闭的
  P0、未验证的发布条件或未分类的残余都必须在交付报告中保留，不能被“基本完成”掩盖。
- 单元测试、构建成功、工作区干净或提交成功都不能单独证明完成。跨平台、安装、崩溃、
  并发、压力和真实服务调用必须按设计要求分别验收。
- 当前环境无法验证的条件必须标为 `阻塞`，写明缺失环境和下一步证据；不得用局部测试
  抵销未完成的验收。
- 进度询问只改变汇报，不自动关闭或丢弃未完成条目；除非用户明确暂停或改变范围，已批准
  的实现应继续到所有条目关闭或明确阻塞。
- 最终交付必须逐条报告已完成、保留和阻塞项，并给出可重放的验证证据。`.omo/` 只能
  作为可选的私有进度材料，不能成为完成依据或替代本规则、契约、台账和机器门禁。

完成前按实际 diff 重新判断风险并补足最小验证；达到验收条件后停止。若验证即将超出
预算，报告现有证据和缺口，由用户决定是否扩大。

当用户处于“讨论方案”“先规划”“帮我想想”“不要急着做”“我们还没定”等语境时，
只做只读研究、方案、取舍和待确认决策。除非用户明确要求写入某个方案文档，否则不得
修改源码、样式、测试、配置、Godot 资源或公开文档，也不得启动服务、安装依赖、运行
测试/构建/格式化、进行浏览器或 Godot 验收、提交、推送或发布。只有“按这个做”“开始
实现”“改代码”等明确确认才能进入执行阶段。

## 0.x 首版开发阶段

ElfieNest 当前目标是完成一套可安装、可运行、可观察、可继续演进的首个可发布版本，
而不是维护稳定版升级体验。阶段名称不免除真实数据、已版本化协议或已承诺发布渠道的
保护义务。

- 未发布的内部实现、仅开发使用的数据、旧缓存和已经同步更新全部调用方的内部路径，
  默认不保留兼容层；删除旧实现并重建开发数据。
- 对已版本化 API/Gateway 协议、安装格式、真实用户数据和已发布产物，先识别现有契约
  与消费者。破坏性变化必须在用户批准的任务范围内协调调用方、版本和数据处理，不能
  由普通局部任务顺手改变。
- 未经用户或当前生产契约明确要求，不新增 migration、fallback read、dual write、
  旧字段 alias、deprecated adapter、兼容 Repository、schema-version branch 或长期兼容壳。
- 开发、测试和临时 `ELFIE_HOME` 可以按任务需要重建；对真实生产数据
  `${ELFIE_HOME:-~/.elfienest}` 的删除、覆盖、不可逆重置或迁移，必须先取得明确批准，
  并优先采用可恢复的备份或移动。

实现默认遵循以下顺序：

1. 先追踪当前真实调用链、事实源和已有测试，再设计改动；
2. 新增依赖或自行实现通用能力前，先检查仓库现有依赖、封装、官方文档和类型定义；
   只有新依赖确实降低整体复杂度和维护成本时才引入；
3. 在满足当前需求的前提下选择最简单实现，不为猜测的未来需求增加抽象、配置项、
   Port、兼容层或间接层；
4. 新产品能力优先交付一条可运行、可观察、可独立验收的端到端垂直切片，不以空目录、
   占位接口或半条调用链作为完成结果；
5. 临时实现不得破坏已冻结边界、创建第二事实源或演变成隐性公开契约；确需临时时，
   明确适用范围、替换触发条件和删除门槛。

## 环境、数据与产物硬约束

- Python 固定为 CPython 3.9.25，依赖以 `uv.lock` 为准。未经“全仓 Python 升级”的
  明确批准，不得修改 `.python-version`、`requires-python`、锁文件、CI、安装器或启动
  脚本中的版本契约。
- Agent、开发者、测试和产品脚本必须使用仓库受控的 `uv` 与 `.venv/bin/python3`，
  不得使用系统 Python、Conda、pip 环境或任意 `ELFIENEST_PYTHON` 覆盖作为产品入口。
  环境损坏时使用 `./elfienest.sh version`；依赖检查和安装由 `scripts/bootstrap.sh`
  统一编排；`uv run --no-sync` 只能在锁定环境已经存在时使用。前端使用 Node.js 20+
  和仓库固定的 pnpm。Ollama 只能作为 Setup 中的明确选择，不能静默安装。
- 源码开发的 `bootstrap.sh check --tier=dev` 必须把锁定的开发工具和仓库管理的
  pre-commit hook 一并视为就绪条件；缺失时由 `./elfienest.sh` 通过现有
  `ensure --tier=dev` 路径修复。Git clone 本身不会安装 hook；首次提交前不得绕过该检查。
- 开发、测试、Desktop、Godot 和构建命令以 `CONTRIBUTING.md`、对应 README 与
  `docs/developer/tooling.md` 为准，不在本文件复制另一套教程。
- 中间构建产物只写根 `build/`，最终发行物只写根 `dist/`，生产数据只写统一 resolver
  定位的 `ELFIE_HOME`；生成物不得写回源码目录。
- 应用内置默认配置的目标唯一源码根是小写 `config/`，发行时唯一副本是
  `resources/config/`；用户配置唯一写入根是 `${ELFIE_HOME}/configs/`。首次运行不得
  复制默认值，业务/领域代码不得自行解析路径或 YAML，现存迁移缺口只按双语
  [`Configuration management contract`](docs/developer/contracts/configuration-management.md)
  与对应 Conformance 收敛，禁止新增散落配置、重复默认值或通用深合并入口。
- SQL 只能存在于持久化层。数据根、数据库职责和 Developer Tools 隔离规则见
  `infrastructure/persistence/AGENTS.md`；Developer Tools 不得读写生产 `ELFIE_HOME`。

## 系统与 authority 边界

中英文 [`System architecture contract`](docs/developer/contracts/system.md) 是跨根模块
所有权和依赖方向的长期权威；Nest 内部所有权、Godot 语义线路和事件路由由中英文
[`Nest–Godot semantic-world contract`](docs/developer/contracts/nest-godot-semantic-world.md)
细化；服务稳定态、入口与受管进程所有权由中英文
[`Service lifecycle contract`](docs/developer/contracts/service-lifecycle.md)细化。系统形态为：

```text
app/              产品入口、用例、编排与装配
elfie/ + nest/    中间领域核心
infrastructure/   模型、工具、持久化、Godot、设备、通信与平台 Adapter
godot_project/    独立 Godot 源工程与物理 authority
```

一套运行中的 ElfieNest 永远只有一个精灵巢。

- `elfie/` 只拥有一只完整精灵的档案、认知、记忆、身体、通信和技能；`nest/` 通过
  空间与设施、巢内生活规则、时间与环境、精灵与巢交互四个功能所有者管理世界语义，
  公共事件机制横贯四者但不是第五个业务模块。两者不得互相导入，也不得导入 `app/`
  或具体 Infrastructure。真实 Elfie 对象与 Nest 状态只在 `app/orchestration/` 组合。
- 稳定强类型的 `Elfie`、`ElfieFactory`、`Nest` Facade 可以直接承担入站 Port；没有
  多实现、独立版本、进程边界或调用方隔离需求时，不为形式对称复制 Protocol。
- `app/features/` 拥有产品用例，`app/interfaces/` 处理协议，`app/orchestration/` 只编排
  跨 authority 流程，`app/bootstrap/` 是唯一生产组合根。具体 Adapter 只位于根
  `infrastructure/`；Infrastructure 能力包不得导入或构造其他能力包的具体 Adapter。
- 单只 Elfie 通过自有 `FoodPort`、`ModelPort`、`ToolPort` 等窄 Port 直接使用注入能力；
  App 管理配置，但不成为普通推理链路的中转层。
- `godot_project/` 是房屋、几何、坐标、移动、碰撞、导航和渲染的唯一源码来源。
  Python 只通过共享、版本化、认证的 Gateway 发送高层语义命令并接收已发生事实，
  不复制物理或渲染事实。共享连接不能混淆语义线路：已知目标身体回执/感知直达所属
  Elfie；语义行动、视觉、虚拟听觉和环境事实进入 Nest 窄边界；Runtime 生命周期事件
  只进入 App Lifecycle。禁止默认广播原始 Runtime 事件。
- `app/orchestration/lifecycle` 是 Core、Gateway 与 Godot authority 启停、重启和收束的
  唯一编排者。Desktop/Observer 只是受限 lifecycle client 和只读观察面，不持有
  authority 凭据、不启动 Runtime、不发送原始协议帧。Interface 与 Feature 也不得构造
  或接管 Engine、Gateway、Godot authority。Backend 稳定层级只有 `OFFLINE`、
  `CORE_READY`、`WORLD_READY`；模型健康由模型能力服务从持久证据投影，Lifecycle 只消费。
- 已打包 Desktop Controller 对每个 OS 用户全局唯一，Viewer 关闭不停止 Server；安装版
  `elfienest start` 激活同一 Controller 而不打开 Viewer。源码 `./elfienest.sh` 只用于
  隔离开发数据根，不能成为第二套生产入口。
- Nest 拥有持久语义事实和技术无关的聚合快照；当前加载、保存、回滚与恢复时机及
  `NestStateStorePort` 归 `app/orchestration/nest_session`，具体 SQL/SQLite Adapter 归
  `infrastructure/persistence/`，由 Bootstrap 注入。App 不得因此直接修改 Nest 内部状态
  或成为家庭事实的第二 authority。
- 禁止恢复旧顶层 Python 包 `runtime/`、`elfienest/`、`ai_runtime/`、`godot_runtime/`
  或 `app/infrastructure/`，也不得创建 `infrastructure/ai_runtime/`。
- 依赖边界按实际目标判定，不只看静态 import。`python -m`、脚本路径、subprocess、
  Node 子进程、Shell 命令、`importlib` 和 `runpy` 指向仓库模块时，必须遵守与直接
  import 相同的全仓所有权和依赖方向；不得把禁止目标藏进字符串，也不得为某个当前
  违规目录写专用黑名单。无法静态解析的启动目标必须通过窄 Port 或由 Bootstrap
  拥有的强类型启动计划注入。

新增顶层目录、改变模块所有权、authority、依赖方向、生产组合/生命周期所有权或系统级
Port 语义时，必须先建立独立 ADR，同步升级中英文架构契约版本并使用治理专用提交；产品
迁移另行实施。只有公开接口、永久数据契约或开发者可见行为变化时才同步 README 和中英文
Developer 文档。任何超出已批准目标的架构变化仍须先确认。

## 实现、测试、文档与安全

- Bug 修复和新增可观察行为先写能失败的测试，再做最小实现。纯机械重命名、删除死代码、
  等价内部重构和仅文档修改可复用现有测试。测试放在对应 `test/<module>/` 路径并使用
  绝对导入；根目录不得新增 `test_*.py`。
- 只有当前改动涉及目录边界、跨层 import、持久化边界、公开协议或生命周期所有权时，
  才运行直接相关 architecture 测试。Python、TypeScript 和 GDScript 规范及质量门只以
  `CONTRIBUTING.md`、机器配置和 CI 为准。
- 只有公开命令、用户可见行为、公开 API 或永久数据契约变化时，才同步当前 Developer
  文档。用户要求修改根 README 或社区文档时，英文默认文件与对应 `_zh.md` 成对更新；
  `docs/` 下规则见 `docs/AGENTS.md`。能力完成声明必须有代码、测试或可重放场景证明。
- 禁止把 API Key、Secret、Token、密码、私有地址、用户数据、未脱敏日志或生产配置写入
  Git 跟踪文件。Secret 只从环境变量或 `ELFIE_HOME` 下被忽略的用户配置加载，示例只
  使用明显占位符；不得用 `--no-verify`、删除扫描器或修改忽略规则绕过 Gitleaks 或
  其他安全检查。发现疑似泄密时停止发布并请求用户确认。

## 提交、推送与交付

本地 commit 的范围、验证和暂存遵循本文件、目录规则及 `CONTRIBUTING.md`。准备功能分支
push 或处理 GitHub 认证、网络及 worktree 权限错误时，读取
`.agents/skills/git-submit-and-push/SKILL.md`；准备创建/复用 PR、进入 merge queue 或核验
main 时，读取 `.agents/skills/git-main-delivery/SKILL.md`。两项技能只处理各自 Git 动作与
故障恢复，不复制或替代机器质量分类。ElfieNest 禁止使用全局 `direct-main-merge`：受保护
main 只能经过仓库规定的 PR 与原生 merge queue。

### 用户授权按 Git 动作严格分层

- “开始实现”“按计划执行”授权本地编辑、聚焦验证和合理的本地 commit；“commit”或
  “提交”只到本地 commit；“push”或“推送”只更新当前功能分支，不创建 PR。
- 只有当前用户消息明确要求“创建 PR”时，才创建或复用当前分支的一个 PR，并在创建后停止；
  只有当前用户消息明确要求“合并 main”“合并到远程主分支”或同义的明确主线动作时，才可
  对冻结候选创建/复用一个 PR、等待 CI、进入 merge queue 并核验 main。“完成”或“交付”
  本身不产生 Git 权限。
- 计划、ADR、技能或历史记录不能产生 Git 远端授权。否定指令优先；“不提交”“不推送”
  “不要创建 PR”“先给我看”等约束必须停在其指定边界。
- 授权绑定当前任务、仓库、功能分支、动作和最终候选 SHA，只覆盖同一动作内的有界重试，
  并在成功、取消、任务/范围/目标变化或候选 SHA 变化时终止。merge queue 生成的合成 SHA
  不是候选变化。不得把 commit、push、PR 和 merge 之间的跨越解释为“不重复确认”。
- 一个功能分支可以跨会话、跨天保留并包含多个逻辑清晰的本地 commit；它不会因时间、
  commit 数量、push 或 main 前进而自动产生 PR。一次主线合并授权最多创建或复用一个 PR。
  若技术上确实需要多个 PR，先报告准确 PR 数量、边界与原因；未获得该准确数量的明确批准时
  保持零个新 PR。
- 同一已授权动作内不重复确认普通步骤。门禁失败先按“代码失败、环境阻塞、远程拒绝、
  危险操作”分类；只有密钥/外部账号、真实数据删除、强制改写历史、候选变化或没有安全
  替代方案时才暂停请求方向。
- 沙箱权限申请是工具执行层的授权，不是产品范围确认。先尝试普通命令；确需升级时，
  使用最小且可复用的权限范围完成当前 Git 流程，不把每一个 `fetch`、`add`、`commit`
  或 `push` 重新包装成一轮产品确认。

交付前确认：

1. 改动位于正确目录，没有引入禁止依赖、第二事实源或退役路径；
2. 已按实际风险完成最小充分验证，范围外失败归属如实；
3. 文档与代码事实一致，私有材料和敏感信息未进入公开或跟踪路径；
4. 没有混入无关改动、缓存、生成物或 Godot 导入噪声；
5. 用户要求的审阅、提交、推送和发布审批点均已满足。
