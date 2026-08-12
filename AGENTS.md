# ElfieNest 编码代理指南

本文件是自动化编码代理进入仓库后的根级通用规则入口。目录专用规则放在对应
子目录的 `AGENTS.md` 中，并只作用于该目录树。ElfieNest 是一个具身
AI 精灵项目，仓库同时包含 Python Core、Electron 桌面宿主、Godot 源项目、
本地开发工具和公开文档站。产品介绍与用户入口见 `README.md`，贡献教程见
`CONTRIBUTING.md`；这里仅保留代理执行任务时必须遵守的边界和审批门。

## 规则优先级

当前任务的明确用户指令必须遵守。判断项目事实时，按以下顺序取证：

1. 当前代码、对应测试及可重放运行结果；
2. `pyproject.toml`、`uv.lock`、`.pre-commit-config.yaml`、
   `.github/workflows/ci.yml`、`.quality-baseline.json` 和
   `test/architecture/` 等机器配置与契约；
3. `docs/developer/` 中当前公开的 Developer 文档；
4. `.agents/knowledge/`、`.omo/` 中的历史或私有材料。

低优先级材料与高优先级事实冲突时，以高优先级为准并修正文档，不要为了
迎合旧设计而改坏当前实现。不得把历史设想当成已实现能力。

以上顺序用于判断“当前实现事实”，不用于反转已采用的版本化架构契约。契约定义允许的
目标，代码和运行结果证明当前状态，两者差距必须进入 `docs/developer/conformance/`；
不得因为旧代码尚未合规，就把目标契约改回旧实现。

`.omo/` 中的 plan、draft、evidence、boulder 和历史执行状态都不是当前任务指令。
除非用户明确点名恢复某个计划，否则不得据此扩大范围、继续旧任务或触发自动续跑。

## 默认执行级别与范围控制

代理必须根据用户已经批准的具体目标和实际改动风险自动判断 S/M/L；用户不需要
使用这些等级名称。等级只决定验证强度和是否适合并行，不会扩大实现范围。信息
不足时按 S 级开始；若用户请求本身明确包含 schema、公开 API 或持久化契约变化，
可直接按 M 级执行，无需为了等级名称再次确认。

### S 级：局部小任务（默认）

适用于单一子系统内、不改变公开 API、永久数据契约、跨模块依赖方向或 Runtime
生命周期所有权的修改。文件数量只是提示，不是判定标准；即使文件少，涉及生产
数据、发布或跨系统协议也不能归为 S 级。

- 只修改用户点名或完成目标绝对必要的文件；新增抽象、新文件或相邻清理不是
  默认授权。
- 只需在回复中给出简短执行步骤；除非用户明确要求，禁止创建或修改
  `.omo/plans/`、`.omo/evidence/`、`.omo/start-work/`、ledger、boulder 或其他
  计划与证据文件。
- 禁止启动 `start-work`、`review-work`、ultrawork、多代理审计或子代理编排；
  用户明确要求使用时除外。
- 验证仅限直接相关测试、已有且快速的改动文件 lint/typecheck 命令，以及
  `git diff --check`；没有现成的局部命令时不得临时升级为全项目检查。
  禁止运行完整 `test/`、完整 `test/architecture/`、全前端测试、全量构建、浏览器
  QA 或发布门禁。
- 验证命令的累计墙钟预算默认不超过 10 分钟。预计或实际超出时停止升级验证，
  报告已完成证据与缺口，等待用户决定。

### M 级：单子系统契约变化

适用于单个子系统内的 schema、公开 API、持久化契约、目录边界或跨层调用变化。

- M 级继承 S 级关于计划文件、证据台账和 OMO 编排的限制；M 级只扩大必要验证
  范围，不自动扩大实现范围或工作流复杂度。
- M 级默认单代理。只有存在至少两个互不依赖、不会编辑同一文件且确实能缩短总
  时间的工作通道时，才可在说明用途后使用最多两个子代理；子代理结果必须替代而
  不是重复主代理工作，禁止自动启动五路复审或多代理审计。
- 运行受影响模块测试、直接相关的一个或少数 architecture 测试，以及至多一个
  直接上层契约测试；不得自动升级为完整 architecture 或全仓测试。
- 验证命令的累计墙钟预算默认不超过 20 分钟。若执行中发现必须新增用户未批准的
  schema、API、持久化或跨层改动，必须先说明新增范围并获得确认；若这些变化本来
  就在用户明确要求内，则不需要二次审批。

### L 级：跨系统、发布或真实生产数据变更

跨多个子系统、发布流程、安装包、真实生产数据或全链路协议的任务属于 L 级。
只有用户明确批准对应的大范围目标后，才允许完整 architecture、全量测试、构建、
浏览器 QA、多代理复审、安全发布门禁或长时间运行验证。多代理仍需有真实独立通道，
不得为了“更全面”重复调查或重复验证。

### 范围外失败与验证去重

- 只有任务开始前记录的同命令基线也失败、依赖检查确认失败路径与当前 diff 无关，
  或已有 CI/Issue 证据证明问题先于当前任务，才能判定为既有失败；否则标为
  “归属未确认”，不得武断归因，也不得为确认归属而破坏当前工作区。
- 已确认的范围外既有失败只记录具体命令、错误和证据；不修复、不扩大任务，也不
  作为当前局部任务的完成阻塞项。
- 同一份源码状态下默认不重复运行同一测试命令。首次失败疑似环境、并发或偶发
  问题时，允许说明原因后诊断性复跑一次；相关源码变化后可以正常重跑。修改注释、
  计划、证据或说明文档不得触发产品测试重跑。
- 如果完成目标必然需要突破当前级别或用户边界，必须先暂停并请求授权，不能用
  “顺手清理”“保持兼容”或“最终验证”为理由自行扩大范围。
- 完成前根据实际 diff 重新判断一次等级并补足对应的最小验证。达到用户的验收条件
  后立即停止；范围外改进只能作为建议报告，不得继续实现。

## 方案确认前禁止执行

当用户表达的是“讨论方案”“一起设计一下”“先出设计文档”“先规划”“帮我想想”
“不要急着做”“我们还没定”等产品、架构、交互或实现方案尚未确认的语境时，
代理必须停留在只读分析、方案文档、取舍说明、问题清单和待确认决策上。

- 在方案未被用户明确确认前，禁止修改源码、样式、测试、配置、Godot 资源、
  构建产物或公开文档；除非用户明确要求把方案写入某个文档文件。
- 在方案未被用户明确确认前，禁止启动开发服务器、运行浏览器/视觉 QA、
  运行 Godot、安装依赖、执行测试、构建、格式化、提交、推送或发布。
- 不能把“可以实现”“新增页面”“加入口”“复用组件”等实现性描述自动理解为
  授权开工；只要对功能、交互、页面结构、成本或优先级仍在讨论，就必须先等待
  用户确认。
- 若用户要求“设计一下”但没有指定保存位置，默认只在回复中给出设计方案；
  若用户要求写入规范或设计文档，只能编辑该文档本身，不得顺手实现方案。
- 从方案阶段转入执行阶段必须有明确话语，例如“按这个做”“开始实现”“执行方案”
  “改代码”“落地到页面”。没有这类确认时，任何执行都视为越权。

## MVP 阶段兼容性原则

在用户明确宣布进入稳定发布和兼容维护阶段前，ElfieNest 按快速 MVP 阶段执行。
当前目标是尽快做出可用、可看、可验证的本地单机产品，而不是维护稳定版升级体验。

- 除非用户明确要求保留真实生产数据，否则旧数据库、旧目录、旧缓存、旧配置、
  旧字段和旧接口默认没有兼容义务。默认做法是更新当前调用方、删除旧实现并重建
  开发数据。
- 禁止自行新增 migration、fallback read、dual write、旧字段 alias、deprecated
  adapter、兼容 Repository、schema-version branch 或长期保留的兼容壳。任何兼容
  工作都属于范围扩张，必须先说明成本和删除条件，并获得用户明确批准。
- 遇到“迁移旧数据才能继续”时，优先推荐备份后重建数据目录；不得自动展开
  schema/workspace 迁移工程。用户明确要求分层迁移时，临时兼容只能存在于获批的
  过渡阶段，并必须有明确调用方清单和删除门槛。
- 对开发、测试和临时 `ELFIE_HOME` 数据，可以按任务需要直接重建；对用户真实
  生产数据 `${ELFIE_HOME:-~/.elfienest}`，任何删除、覆盖或不可逆重置仍必须先
  获得用户明确确认，并优先采用可恢复的移动/备份。
- 实现方案以简单、可维护、可快速验收为先；不要因为假设未来兼容需求，把一个
  UI 或局部功能任务扩大成账户主键、历史库迁移、全链路协议升级等大工程。

## 私有知识的条件路由

`.agents/knowledge/INDEX.md` 是可选的本机私有索引。只有文件存在，并且当前
任务属于架构、产品或故事等知识任务时，才按索引条目的 `read_when` 条件读取
命中的材料；未命中就不要展开读取。索引不存在时，依靠代码、测试、机器配置
和公开文档正常工作，不得创建占位文件或中断任务。

`.agents/knowledge/` 与 `.omo/` 默认不公开。禁止把其中的秘密、合作材料、
未发布世界观、历史草案、模型提示词或中间设计稿自动复制、摘录、链接到
`README.md`、`docs/`、源码注释、提交信息或 PR。公开内容必须经过用户明确审阅。

## 环境、启动与验证

Python 固定为 CPython 3.9.25，依赖以 `uv.lock` 为准。前端使用 Node.js 20+ 和 pnpm。
所有依赖由 `scripts/bootstrap.sh` 统一编排，分两种模式：

- **dev（贡献者）**：Python dev + 前端 + Godot 编辑器/Web Export + Electron dev deps
- **build（源码/安装包构建）**：当前原生 target 的发行工具链

### 开发者快速启动

```bash
./elfienest.sh              # 自动检测并补齐依赖，进入交互菜单
./elfienest.sh serve        # 自动检测并补齐依赖，前台运行服务
./elfienest.sh start        # 自动检测并补齐依赖，后台启动服务
```

首次运行会自动安装必需的开发依赖。公共 Ollama 是 Setup 中可选的明确选择，不能在
bootstrap 阶段静默安装。

### 手动依赖管理

```bash
./scripts/bootstrap.sh check --tier=dev     # 检查依赖状态
./scripts/bootstrap.sh ensure --tier=dev    # 补齐缺失依赖
./scripts/bootstrap.sh report --tier=dev    # 输出 JSON 格式报告
```

### 用户安装

```bash
./install.sh                # 完整安装应用 + 全局命令
```

安装后可全局运行 `elfienest` 命令。

### Python 运行时不可变契约

- 未获得用户对“全仓 Python 升级”的明确批准，禁止修改 `.python-version`、
  `pyproject.toml` 的 `requires-python`、`uv.lock`、CI、安装器或启动脚本中的
  CPython 3.9.25 契约；不得借单个功能、依赖或本机版本顺手升级 Python。
- Agent、开发者、CR、测试和所有产品/开发脚本必须经仓库受控的 `uv` 与
  `.venv/bin/python3` 执行。不得以系统 `python`、`python3`、Conda、pip 环境或
  任意 `ELFIENEST_PYTHON` 覆盖作为产品入口。
- 需要修复缺失、损坏或版本不匹配的开发环境时，标准路径是
  `./elfienest.sh version`；需要安装本机原生应用时运行 `./install.sh`。
  `uv run --no-sync` 只能在该锁定环境已经存在时使用。

验证范围按“默认执行级别与范围控制”执行。只有当前改动涉及目录边界、跨层 import、
持久化边界、公开协议或生命周期所有权时，才运行直接相关的 architecture 测试；
普通局部修改禁止运行完整 `test/architecture/`。质量门及文档构建命令以
`CONTRIBUTING.md` 为准；机器上的最终事实源是 `pyproject.toml`、
`.quality-baseline.json`、`.pre-commit-config.yaml` 和 CI。不得另写一套代码
规范或用文档描述覆盖机器配置。

## 目录与依赖边界

### 系统目标架构

跨根模块迁移以中英文
[`System architecture contract`](docs/developer/contracts/system.md) 为长期权威：

```text
app/              上层产品入口、用例、编排与装配
elfie/ + nest/    中间领域核心
infrastructure/   模型、工具、持久化、Godot、设备、通信与平台 Adapter
```

一套运行中的 ElfieNest 永远只有一个精灵巢。

- `Elfie`、`ElfieFactory`、`Nest` 等稳定强类型 Facade 可以直接承担入站 Port 角色；
  没有多实现、独立版本、进程边界或调用方隔离需求时，禁止为形式对称重复定义 Protocol。
- `elfie/`、`nest/` 和 App Feature/Orchestration 分别拥有自己实际需要的出站 Port；
  根 `infrastructure/` 实现这些 Port，`app/bootstrap/` 统一创建并注入具体 Adapter，
  `app/orchestration/` 只编排运行流程。
- Infrastructure 各能力包不得导入或构造彼此的具体 Adapter；跨能力依赖使用窄 Port，
  由 Bootstrap 组合。
- `elfie/` 与 `nest/` 不得互相导入，也不得导入 `app/` 或具体 Infrastructure；底层
  Adapter 可以反向导入自己实现的核心 Port，这是依赖倒置，不是领域反向依赖。
- `ai_runtime/` 已按职责拆解并删除；不得恢复该旧根，也不得创建
  `infrastructure/ai_runtime/`。`elfie/` 与 `nest/` 内仍存在的领域内部技术实现
  是已登记迁移路径，只能按获批切片收缩，不得复制成新的所有权。
- `godot_project/` 永久保持独立 Godot 源工程和物理 authority，不是迁移目录；只有
  Python 侧 Gateway、宿主、产物和协议 Adapter 目标进入 `infrastructure/godot/`。

下面各项描述当前目录职责；与目标物理位置不同的部分由
[`System conformance`](docs/developer/conformance/system.md) 跟踪，禁止一次性搬迁。

- `elfie/` 只实现单个完整精灵：档案、大脑、神经系统、身体、通信和技能；
  不得加入账户、Web、Godot 场景或桌面生命周期。
- `nest/` 只实现活动空间、巢内状态、环境时间、互动传播和 Python 侧 Godot
  语义 Port；只能保存精灵 ID 与巢内状态，不得持有或创建真实精灵对象。
- 真实精灵与 `Nest` 的组合属于 `app/orchestration/`；跨 `elfie/`、`nest/`
  或其他 authority 的产品流程也必须在这里编排。单只精灵通过注入 Port 读取 Food、
  调用模型或执行工具，不经过 Orchestration。
- `app/features/` 放产品用例，`app/interfaces/` 放 API、Web、CLI，
  `app/orchestration/` 放跨 authority 编排，`app/bootstrap/` 只做依赖装配；具体持久化、
  模型、工具、Godot、设备、通信和平台实现位于根 `infrastructure/`。
- Provider/模型访问与 Runtime 技术实现位于 `infrastructure/models/`，工具执行位于
  `infrastructure/tools/`，Food 管理和报告位于 App Feature；Elfie 通过自有
  `FoodPort`、`ModelPort`、`ToolPort` 使用注入能力。
- `app/interfaces/desktop/` 只负责可见 Electron 窗口、系统 UI 集成与公开
  lifecycle client，不承载 Supervisor、Godot authority、账户、聊天、领养或 Nest 规则。
- `godot_project/` 是独立 Godot 源工程，也是房屋、几何、坐标、移动、碰撞和渲染的唯一源码来源；禁止在
  Python 中复制场景、3D 布局或家具事实。
- `devtools/` 是隔离的模块实验台；`docs/` 是公开文档网站内容；
  `test/` 必须镜像源码结构，根目录不得新增 `test_*.py`。
- 依赖边界按实际目标判定，不只看静态 import。`python -m`、脚本路径、subprocess、
  Node 子进程、Shell 命令、`importlib` 和 `runpy` 指向仓库模块时，必须遵守与直接
  import 相同的全仓所有权和依赖方向；不得把禁止目标藏进字符串，也不得为某个当前
  违规目录写专用黑名单。无法静态解析的启动目标必须通过窄 Port 或由 Bootstrap
  拥有的强类型启动计划注入。

### Runtime / Observer authority contract

- `app/orchestration/lifecycle` 是 Runtime 生命周期、健康状态与收束的唯一
  编排者；只有该边界可以启动、停止或重启 Core、Gateway 与 Godot authority。
- Godot authority 宿主与产物位于 `infrastructure/godot/lifecycle/` 和
  `infrastructure/godot/artifacts/`，协议接入位于 `infrastructure/godot/gateway/`；
  它们不得持有 Nest 业务状态或成为产品流程。
- Python 与 Godot Runtime 只能通过共享、版本化、认证的 Gateway
  发送高层语义命令、接收已发生的物理事实；不得在 Python 复制空间、导航、碰撞或
  渲染事实。
- `app/interfaces/desktop` 是可见的 Observer 与 lifecycle client：只能读取获授权
  的范围状态、发出获允许的高层意图；不得持有 authority 凭据、启动 Runtime 组件，
  或导入 Gateway 内部协议实现。
- `app/interfaces/`、`app/features/` 可以使用公开配置、目录
  和只读 DTO；不得因此构造或接管 Engine、Gateway、Godot authority，或发送原始
  Runtime 协议帧。
- 新增跨边界 import、生命周期所有者或 Observer 能力时，只添加或更新直接相关的
  architecture 契约测试。仅当公开协议、永久数据契约或用户可见开发者行为变化时，
  才同步中英文 Developer 文档；内部依赖调整不得自动扩大为文档任务。

- 中间构建产物只能写入根 `build/`，最终发行物只能写入根 `dist/`，生产数据
  只能写入 `ELFIE_HOME`；不得把生成物写回源码目录。
- 生产数据只能通过统一 resolver 定位；SQL 只能存在于持久化层。具体数据根、
  数据库职责和 Developer Tools 隔离规则见 `infrastructure/persistence/AGENTS.md`。

禁止恢复旧顶层 Python 包 `runtime/` 或 `elfienest/`。宏观架构 v1 已冻结；新增顶层
目录、改变模块所有权、authority、依赖方向、生产组合/生命周期所有权或系统级 Port
语义时，必须先建立新的独立 ADR，同步升级中英文契约版本，并使用治理专用提交，之后
才能另行迁移产品代码。只有公开接口、永久数据契约或开发者可见行为变化时才同步
README 与中英文 Developer 文档。任何超出用户已批准目标的架构变化仍须先确认。

架构治理与实现变更的隔离作用于整个仓库，不只作用于 `app/` 或传统生产根目录。
先识别架构契约、ADR、`AGENTS.md`、Scanner、架构测试、治理 CI 和普通说明文档，
其余所有被跟踪文件都属于实现侧，包括 `devtools/`、普通 `scripts/`、根启动/工具链
配置、非架构测试、Manifest、资产、文档站代码和非治理 Workflow。治理与实现两侧不得
出现在同一提交或 Pull Request。旧架构 Baseline 保持为实现侧文件，产品迁移只能
缩减；新增目录、后缀或可执行表面不能依靠未分类来绕过治理检查。

## 实现和测试要求

- Bug 修复和新增可观察行为先写能失败的测试，再做最小实现。纯机械重命名、删除
  死代码、等价内部重构和仅文档修改可以复用现有测试，不强制制造失败测试；测试
  放在对应 `test/<module>/` 路径并使用绝对导入。
- Python、TypeScript、GDScript 的具体规范、质量基线与验证命令只引用
  `CONTRIBUTING.md`、`pyproject.toml`、`.quality-baseline.json`、
  `.pre-commit-config.yaml`、CI 和架构测试，不在本文件复制教程。
- 不覆盖或回滚他人的未提交改动，不顺手格式化、删除或重构任务范围外文件。
- 只有公开命令、用户可见行为、公开 API 或永久数据契约变化时，才同步更新面向
  开发者的当前文档。内部重构、测试调整和临时实现不得自动扩大为文档任务；能力
  声明仍必须能由代码、测试或可重放场景证明。
- 用户明确要求修改根目录 README 或社区文档时，英文默认文件与对应 `_zh.md`
  必须成对更新；`docs/` 下的具体规则见 `docs/AGENTS.md`。

## 安全与敏感信息

禁止把 API Key、Secret、Token、密码、私有地址、用户数据、未脱敏日志或生产
配置写入任何被 Git 跟踪的文件。密钥从环境变量或 `ELFIE_HOME` 下被忽略的
用户配置加载；示例只能使用明显占位符。

`.pre-commit-config.yaml` 使用官方 `gitleaks/gitleaks` pre-commit hook，
CI 通过 `pre-commit run --all-files` 执行它。仓库配置不等于本机已安装
`.git/hooks/pre-commit`；需要本地钩子时按 `CONTRIBUTING.md` 准备环境。
禁止使用 `--no-verify`、删除扫描器或修改忽略规则来绕过检查。安全扫描只是
提交前的机器门，发现或怀疑泄密时仍须停止发布并请求用户确认。

## 提交、推送与人工审批

准备提交或推送时，先读取
`.agents/skills/git-submit-and-push/SKILL.md`，检查工作区、测试、敏感信息、
分支和远端状态。只有变更完整、验证通过且满足用户授权与审阅门时，才能按该
技能暂存、提交和推送；明确要求“不提交”或“审阅后再提交”时，该人工审批点
优先，保持改动在本地。

## 完成前检查

交付前必须确认：

1. 改动位于正确目录，没有引入禁止的跨边界依赖或旧顶层包；
2. 已按 S/M/L 级别完成最小充分验证；只有确实改变架构边界时才要求相关
   architecture 测试通过，范围外既有失败已经如实记录；
3. 文档与代码事实一致，私有材料未进入公开路径；
4. Gitleaks 与其他安全检查没有被绕过；
5. 没有混入他人改动、缓存、生成物或 Godot 导入噪声；
6. 用户要求的人工审阅、提交和发布审批点已经满足。
