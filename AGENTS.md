# ElfieNest 编码代理指南

本文件是自动化编码代理进入仓库后的单一规则入口。ElfieNest 是一个具身
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

只改局部时先运行对应测试，再运行 `test/architecture/`。质量门及文档构建命令
以 `CONTRIBUTING.md` 为准；机器上的最终事实源是 `pyproject.toml`、
`.quality-baseline.json`、`.pre-commit-config.yaml` 和 CI。不得另写一套代码
规范或用文档描述覆盖机器配置。

## 目录与依赖边界

- `elfie/` 只实现单个完整精灵：档案、大脑、神经系统、身体、通信和技能；
  不得加入账户、Web、Godot 场景或桌面生命周期。
- `nest/` 只实现活动空间、巢内状态、环境时间、互动传播和 Python 侧 Godot
  接口；只能保存精灵 ID 与巢内状态，不得持有或创建真实精灵对象。
- 真实精灵与 `Nest` 的组合属于 `app/orchestration/`；跨 `elfie/`、`nest/`
  和 `ai_runtime/` 的产品流程也必须在这里编排。
- `app/features/` 放产品用例，`app/interfaces/` 放 API、Web、CLI，
  `app/infrastructure/` 放持久化、音频、文件系统和设备能力，
  `app/bootstrap/` 只做依赖装配。
- `ai_runtime/` 放模型、供应商、粮食策略、工具、安全和推理循环。
- `app/interfaces/desktop/` 只负责可见 Electron 窗口、系统 UI 集成与公开
  lifecycle client，不承载 Supervisor、Godot authority、账户、聊天、领养或 Nest 规则。
- `godot_project/` 是独立 Godot 源工程，也是房屋、几何、坐标、移动、碰撞和渲染的唯一源码来源；禁止在
  Python 中复制场景、3D 布局或家具事实。
- `devtools/` 是隔离的模块实验台；`docs/` 是公开文档网站内容；
  `test/` 必须镜像源码结构，根目录不得新增 `test_*.py`。

### Runtime / Observer authority contract

- `app/orchestration/lifecycle` 是 Runtime 生命周期、健康状态与收束的唯一
  编排者；只有该边界可以启动、停止或重启 Core、Gateway 与 Godot authority。
- `godot_runtime` 只负责选择和承载 Godot authority；不得持有 Nest 业务状态，
  不得成为产品流程或协议路由层。
- `nest/godot_gateway` 是 Python 与 Godot Runtime 的唯一协议边界。Python 只能
  发送高层语义命令、接收已发生的物理事实；不得在 Python 复制空间、导航、碰撞或
  渲染事实。
- `app/interfaces/desktop` 是可见的 Observer 与 lifecycle client：只能读取获授权
  的范围状态、发出获允许的高层意图；不得持有 authority 凭据、启动 Runtime 组件，
  或导入 Gateway 内部协议实现。
- `app/interfaces/`、`app/features/`、`app/infrastructure/` 可以使用公开配置、目录
  和只读 DTO；不得因此构造或接管 Engine、Gateway、Godot authority，或发送原始
  Runtime 协议帧。
- 新增跨边界 import、生命周期所有者或 Observer 能力前，必须先扩展
  `test/architecture/`，再同步中英文 Developer 文档，并由用户确认架构影响。

- 中间构建产物只能写入根 `build/`，最终发行物只能写入根 `dist/`，生产数据
  只能写入 `ELFIE_HOME`；不得把生成物写回源码目录。
- 生产数据的唯一根是 `${ELFIE_HOME:-~/.elfienest}`：根级 `nest.db` 只保存
  Nest 身份、账号/归属、运行与房间状态；每只精灵使用稳定 `elfie_id` 的
  `elfies/<elfie_id>/` 工作区，聊天唯一事实源为
  `conversations/history.sqlite`。名称只能出现在档案或登记表，不能参与目录寻址。
- 不创建 `users/` 聊天目录，不在 Nest 根保留新的聊天副本；浏览器和手机自己的
  历史不回传为本机用户目录。`nest.db.chat_messages` 是已废弃表，禁止创建、读取、
  写入或迁移；历史表在数据库升级时直接删除。
- Developer Tools 的唯一默认根是 `${ELFIE_DEV_HOME:-~/.elfienest-dev}`，并在其下
  分别保存 `elfie_lab/`、`nest_lab/`、`runtime_lab/` 数据。它们不得读取或写入
  `ELFIE_HOME`；仅可为拒绝误配置而比较生产根。新增路径必须由
  `ai_runtime.storage.data_home` 解析，并同步 `test/architecture/` 与
  `docs/developer/` 的数据契约。

禁止恢复旧顶层 Python 包 `runtime/` 或 `elfienest/`。新增顶层目录、改变上述
职责或引入跨边界依赖前，必须先更新 `test/architecture/` 契约，再同步相关
README 与 `docs/developer/`，并由用户确认架构影响。

## 实现和测试要求

- 行为变化先写能失败的测试，再做最小实现；测试放在对应
  `test/<module>/` 路径并使用绝对导入。
- Python、TypeScript、GDScript 的具体规范、质量基线与验证命令只引用
  `CONTRIBUTING.md`、`pyproject.toml`、`.quality-baseline.json`、
  `.pre-commit-config.yaml`、CI 和架构测试，不在本文件复制教程。
- 不覆盖或回滚他人的未提交改动，不顺手格式化、删除或重构任务范围外文件。
- 修改行为、命令、配置或目录边界时，同步更新面向开发者的当前文档；能力
  声明必须能由代码、测试或可重放场景证明。

## Godot 操作门

打开、运行、调试、截图或关闭 Godot 前，必须先读取并执行
`.agents/skills/godot-project-operator/SKILL.md`。按该技能检查现有进程和
`godot_project/project.godot` 声明的版本；未经用户同意不得用不匹配版本编辑项目，
不得创建重复实例。操作前后检查 Git 状态，禁止保留 `.godot/`、导入缓存或
编辑器自动产生的无关改动。

Godot 相关规则的机器边界由 `godot_project/project.godot`、源码资源和
`test/architecture/` / `test/godot/` 验证；技能负责安全操作流程，二者都不能
被旧设计文档替代。

## 文档、公开边界与调试工具

- 公开文档的默认语言为英文，同时维护简体中文版本。README 类文件使用
  `README.md`（英文，默认）+ `README_zh.md`（中文）成对；根目录社区文档
  同样使用 `_zh.md` 后缀（如 `CONTRIBUTING.md` / `CONTRIBUTING_zh.md`）。
  `docs/` VitePress 文档站使用 `locales` 机制：英文为站点根目录，中文位于
  `docs/zh/`。
- **任何对公开文档（README、社区文档、docs 站页面）的内容变更，必须在同一
  改动中同时更新中英文两份。** 仅更新一侧视为未完成；PR 必须列明双语同步
  情况。
- 路径、标识符、API、协议字段和第三方产品名可以保留英文并用中文说明。
- `docs/` 只发布最终读者需要、与当前实现一致且经用户审阅的内容。会议记录、
  提示词、模型中间稿、历史草案、合作材料和未开发剧情留在私有区域。
- JSON Schema 等内部数据结构不得为了说明代码而在文档站维护冗余副本；
  代码中的类型模型是内部契约事实源。
- 单精灵调试平台只服务本地 `elfie` 模块开发，必须使用独立入口、本地网址、
  前端资源和数据目录。禁止修改或复用 `app/interfaces/web/static/` 的普通
  用户页面，禁止在生产入口或普通用户导航中暴露调试平台。

任何公开能力、剧情秘密、截图或页面上线前，都需要负责人目视审阅。无法证明
已实现的能力应明确标为规划，或不公开。

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

本次文档体系重建的用户审批门是：用户完整审阅文档前，禁止 stage、commit、
push 或发布网站。完成实现与本地验证后只报告工作区状态和验收入口，等待用户
明确确认。未来其他任务仍按当时的用户指令、本文件和 Git 技能判断，不继承
本次临时禁令。

## 完成前检查

交付前必须确认：

1. 改动位于正确目录，没有引入禁止的跨边界依赖或旧顶层包；
2. 对应测试、`test/architecture/` 和适用的质量门实际通过；
3. 文档与代码事实一致，私有材料未进入公开路径；
4. Gitleaks 与其他安全检查没有被绕过；
5. 没有混入他人改动、缓存、生成物或 Godot 导入噪声；
6. 用户要求的人工审阅、提交和发布审批点已经满足。
