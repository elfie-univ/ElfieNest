# 参与 ElfieNest

> 中文版：本文件 · [English](CONTRIBUTING.md)

感谢你愿意改进 ElfieNest。这个仓库同时包含 Python Core、Electron
桌面宿主、Godot 源项目和公开文档站。请先确认改动属于哪个边界，再开始写代码。

## 开始之前

1. 阅读根目录的 `AGENTS.md`，了解强制架构、安全和操作规则。
2. 阅读相关模块的 `README.md`；公开架构说明位于 `docs/developer/`。
3. 先搜索已有 Issue，确认问题没有被重复报告。
4. 对行为变化先补失败测试，再做最小实现。

## 开发环境

ElfieNest 使用 `scripts/bootstrap.sh` 统一管理所有依赖，分两种模式：

- **dev（贡献者）**：Python dev + 前端 + Godot 编辑器/Web 导出 + Electron dev deps
- **build（源码/安装包构建）**：当前原生 target 的发行工具链

### 快速启动

```bash
./elfienest.sh              # 自动检测并补齐依赖，进入交互菜单
```

首次源码开发运行会安装必需的开发依赖。公共 Ollama 保持可选，并只在 Setup 中由用户明确选择。

### 手动依赖管理

```bash
# 检查依赖状态
./scripts/bootstrap.sh check --tier=dev

# 补齐缺失依赖
./scripts/bootstrap.sh ensure --tier=dev
```

Bootstrap 会在各 package 目录中解析仓库锁定的 pnpm 版本。没有兼容的 pnpm
命令时，它只通过 `npx` 临时运行精确锁定的版本，绝不安装或覆盖全局 pnpm。

私有根目录 `package.json` 只负责锚定统一的 Node.js 20+ 与 pnpm 10.12.1 工具链，
不持有业务依赖。Web 前端、桌面宿主、文档站和 Developer Tools 仍各自保留独立的
清单与锁文件。可用下面的只读检查确认这些声明没有分叉：

```bash
bash scripts/check_node_toolchain.sh
```

### Python 环境契约
`requires-python`、锁文件、CI 或启动脚本中的 3.9.25 契约。所有安装、开发、测试、
代码审查与脚本均通过 `scripts/bootstrap.sh` 和仓库 `.venv/bin/python3` 运行；
不要调用系统 `python`/`python3`、复用其他虚拟环境或设置 `ELFIENEST_PYTHON` 覆盖入口。

### 前端开发

前端使用 Node.js 20+ 和 pnpm：

```bash
cd app/interfaces/web/frontend
pnpm install --frozen-lockfile
pnpm build       # 构建到 build/web/
pnpm test        # 运行前端测试
```

### 文档站

文档站使用 Node.js 20 和 pnpm 10.12.1：

```bash
cd docs
pnpm install --frozen-lockfile
pnpm build
```

不要手工改写锁文件。只有依赖确实改变时，才更新相应锁文件并在 PR 中解释原因。

## 选择正确目录

- `elfie/`：单个完整精灵的档案、大脑、神经系统、身体、通信和技能。
- `nest/`：活动空间、巢内状态、环境时间和互动传播；不得持有真实精灵对象。
- `app/orchestration/`：组合真实 `Elfie`、`Nest` 与注入能力的跨模块流程。
- `app/features/`：产品用例；`app/interfaces/`：API、Web、CLI；
  `app/infrastructure/`：持久化、文件系统、音频和设备能力。
- `infrastructure/`：模型、工具、持久化、Godot、设备、通信与平台 Adapter。
- `app/interfaces/desktop/`：可见 Electron 窗口、平台适配与公开 Runtime
  lifecycle client；不持有 Runtime 进程。
- `godot_project/`：独立 Godot 源工程；房屋、几何、坐标、碰撞、移动和渲染的唯一源项目。
- `devtools/`：与普通用户产品隔离的模块实验台。
- `docs/`：唯一会进入公开文档网站的内容。
- `test/`：镜像源码结构的测试；根目录不得直接新增 `test_*.py`。

新增顶层目录或跨边界依赖前，必须同步更新架构契约测试、相关 README 和 Developer 文档。

## 代码规范

### Python

- 使用 Python 3.9 可用的语法和类型；稳定模块边界使用明确类型，不传裸字典。
- 新增或修改的函数必须有准确类型，不使用 `Any` 掩盖模型不清晰的问题。
- 数据入口优先解析为 Pydantic v2 模型；内部契约以代码中的 Pydantic 模型为唯一事实源。
- 错误应携带可操作上下文；不得吞掉异常或只打印后继续。
- 单个 Python 文件以 250 行纯源码为上限；超过时按职责拆分。
- 测试使用绝对导入，并放在与源码对应的 `test/<module>/` 路径。

仓库存在一份机器可读的历史质量债务基线 `.quality-baseline.json`。它不是豁免清单：
已有诊断可以逐步消除，但任何新增 Ruff、Ruff format 或 MyPy 诊断都会使检查失败。
不要用 `--write-baseline` 接纳自己的新问题；只有专门的质量债务变更才能更新基线。

### TypeScript

- 保持 `strict` 类型检查，不使用无说明的 `any` 或非空断言。
- Electron 只负责桌面生命周期和平台边界，不承载产品业务规则。
- 修改 `app/interfaces/desktop/` 后运行其现有测试和 TypeScript 检查，并在 PR
  中列出命令。

### GDScript

- Godot 只负责场景、几何、坐标、碰撞、移动和渲染。
- 打开、运行或截图 Godot 前，必须先按
  `.agents/skills/godot-project-operator/SKILL.md` 检查版本和现有进程。
- 不提交 `.godot/`、导入缓存或编辑器自动产生的无关改动。

## 测试与质量门

提交前至少运行：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/architecture/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync python scripts/check_quality_baseline.py
PRE_COMMIT_HOME=/tmp/elfienest-precommit uv run --no-sync pre-commit run --all-files
```

再运行与你的改动直接相关的单元、集成或端到端测试。文档改动还要运行：

```bash
cd docs
npx --yes pnpm@10.12.1 build
```

不得使用 `--no-verify`，不得用宽泛 ignore、删除测试或更新质量基线来隐藏失败。

## 文档和公开内容

- 公开文档的默认语言为英文，同时维护简体中文版本。README 类文件使用
  `README.md`（英文，默认）+ `README_zh.md`（中文）成对；根目录社区文档
  同样使用 `_zh.md` 后缀。`docs/` VitePress 站点使用 `locales` 机制：
  英文为站点根目录，中文位于 `docs/zh/`。
- **任何对公开文档（README、社区文档、docs 站页面）的内容变更，必须在同一
  改动中同时更新中英文两份。** 仅更新一侧视为未完成；PR 必须列明双语同步
  情况。
- `docs/` 只写最终读者需要的当前内容，不存放会议记录、提示词、模型中间稿或历史草案。
- `.omo/` 和 `.agents/knowledge/` 是本机私有区域，禁止在公开文档中链接、摘录或复制。
- 能力声明必须由当前代码、测试或可重放场景证明；未发布能力必须明确标为规划，或不公开。
- 修改行为、命令、目录边界或配置时，同步更新对应 README 和 Developer 文档。

## 分支和提交范围

- 一个 PR 只解决一个边界清晰的问题；避免顺手格式化或重构无关文件。
- 不覆盖他人的未提交改动，不提交本机配置、生成物、缓存或生产数据。
- 提交信息说明“为什么改”，而不只是罗列文件名。
- 界面或文档网站改动必须先由负责人目视验收；未确认前保持本地改动，不提交、不推送。

## Pull Request 必须包含

- 问题与范围，以及明确不在本次处理的内容。
- 受影响模块和架构边界。
- 实际执行的测试命令及结果。
- README、Developer 文档和用户文档是否需要同步。
- 是否涉及配置迁移、用户数据、安全边界或公开能力声明。
- 界面改动的截图或可复现验收步骤。

## 禁止事项

- 提交 API Key、Token、密码、私有地址、用户数据或未脱敏日志。
- 恢复旧顶层包 `runtime/` 或 `elfienest/`。
- 在 `nest/` 持有或创建真实精灵，或在 Python 中复制 Godot 场景/几何事实。
- 在 `app/interfaces/desktop/`、Godot 或调试平台中绕过产品和安全边界。
- 发布私有世界观、合作材料、未实现能力或模型生成的中间设计稿。
- 绕过 pre-commit、Gitleaks、架构测试或用户审阅门。

提交贡献即表示你同意遵守 `CODE_OF_CONDUCT_zh.md`，并按 Apache License 2.0
提供你的贡献。
