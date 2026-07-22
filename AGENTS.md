# ElfieNest Project Guide

An embodied AI creature simulation with a three-layer brain architecture, emotional chemistry, and Godot 3D integration.

## Quick Start

```bash
# Prepare the pinned Python 3.9.25 environment and install the CLI
./install.sh

# Verify the unified ElfieNest entrypoint
elfienest version

# Run the main simulation (3 ticks) through the pinned environment
.venv/bin/python main.py
```

The simulation runs without external dependencies - if Ollama is unavailable, it gracefully falls back to a built-in lightweight simulator.

## Architecture

```
ElfieNest/
├── elfie/               # 完整精灵个体
│   ├── profile/         # 个体档案、物种外貌和默认模板
│   ├── brain/           # Neocortex (LLM reasoning), context building
│   ├── nervous_system/  # 传感、动作、过滤、限位和反射
│   ├── body/            # Headless、Native、External 可替换身体
│   ├── communication/   # 精灵自带的消息通信
│   ├── skills/          # 思考过程中使用的技能
├── nest/                # 完整精灵巢活动空间
├── ai_runtime/          # AI 推理、粮食、工具和安全运行时
├── app/                 # 产品功能、接口、基础设施和跨模块编排
├── desktop/             # Electron 桌面宿主
├── godot/               # 独立 Godot 4.6 源项目
├── devtools/            # 隔离的模块实验台
├── docs/                # 中文设计与实现文档
├── scripts/             # 启动、构建、检查和发布脚本
├── test/                # 镜像源码结构的测试
├── build/               # 中间构建产物，Git 忽略
└── dist/                # 最终安装包，Git 忽略
```

## 目录架构边界（强制规则）

- `elfie/` 只实现单个完整精灵，不得加入账户、Web、Godot 场景或桌面生命周期。
- `nest/` 只实现活动空间、巢内状态、环境时钟、互动传播和 Python 侧 Godot 协议。Nest 只能保存精灵 ID 与巢内状态，禁止持有或创建 `ElfieIndividual`。
- 真实精灵实例与 `Nest` 的组合固定放在 `app/orchestration/NestSession`；跨 `elfie/`、`nest/`、`ai_runtime/` 的流程只能进入 `app/orchestration/`。
- 产品功能进入 `app/features/`；API/Web/CLI 进入 `app/interfaces/`；持久化、音频、文件系统和设备身份进入 `app/infrastructure/`；`app/bootstrap/` 只负责依赖装配。
- Godot 房屋、几何、坐标、移动、碰撞和渲染以 `godot/` 为唯一源码来源。禁止在 Python Nest 中创建房屋蓝图、3D 布局或家具资产副本。
- Electron 窗口、平台适配、资源发现和进程监督进入 `desktop/`；账户、聊天、领养和 Nest 规则禁止进入 Desktop。
- AI 模型、供应商、粮食策略、工具、安全和推理循环进入 `ai_runtime/`；禁止恢复旧顶层包名 `runtime/`。
- 禁止恢复旧顶层包名 `elfienest/`。产品名仍为 ElfieNest，但 Python 源码必须按 `app/`、`nest/`、`elfie/`、`ai_runtime/` 分责。
- 正式中间产物只能写入根 `build/`，最终发行物只能写入根 `dist/`，生产数据只能写入 `ELFIE_HOME`。禁止把生成的 Godot Web、Desktop JS 或 Python Core 放回源码目录。
- 新增目录或跨边界依赖前必须同步更新 README、架构文档和 `test/architecture/` 契约测试。

## Key Concepts

### Three-Layer Brain Architecture
1. **Neocortex (Cognition)**: LLM-based reasoning and decision making
2. **Limbic System (Core Systems)**: Emotions (amygdala), energy (hypothalamus), memory (hippocampus), context (thalamus)
3. **Nervous System and Body**: Physical actuators, sensors, reflex arcs

### Main Loop Flow
1. `ElfieNestEngine.start_loop()` drives the application loop
2. Each tick: `Nest.tick()` advances environment time and `NestSession.tick_elfies()` advances active Elfies
3. For each active Elfie, the Engine publishes `BrainClockPulse` and pumps typed Body events without waiting for cognition
4. NervousSystem and Communication publish into `PerceptualWorkspace`
5. BrainCoordinator seals a frame, builds `BrainContext`, and submits one asynchronous cortical turn
6. OutputRouter routes the typed `DecisionPlan` and writes execution receipts back to the workspace

## Running Tests

首次运行测试前，先按锁文件安装 CPython `3.9.25` 和开发依赖：

```bash
uv sync --locked --extra dev
```

```bash
# Run all tests in the locked Python 3.9.25 environment
uv run --no-sync pytest test/

# Run specific test file
uv run --no-sync pytest test/elfie/brain/emotion/test_emotion_system.py

# Run with verbose output
uv run --no-sync pytest test/ -v
```

Tests require no external services - they use mock agents.

## Worktree Completion Workflow

When working from a Git worktree, do not leave completed work only in the
worktree branch. After a feature is finished, verified, and confirmed by the
user:

1. Commit the completed work in the worktree branch.
2. Push the branch to the remote repository.
3. Merge or otherwise sync the confirmed changes back to the original main
   branch so other branches and worktrees can see them.
4. Report the commit, branch, push status, and merge/sync status to the user.

If the user has not confirmed the result yet, keep the changes local and state
that they are not merged back. Do not assume worktree-only changes are visible
from the main checkout.

## Git 提交与推送（强制规则）

- 用户要求“提交”“提交代码”“commit 一下”或“保存到 Git”时，必须读取并遵循 `.agents/skills/git-submit-and-push/SKILL.md`。
- 每次完成并验证一组改动后，必须主动评估它是否已构成边界清晰、没有已知问题的提交节点；是则自动 commit 并 push，不等待用户再次下达“提交”命令。
- 禁止提交仍在调试、测试失败、存在已知 bug 或尚待用户确认的半成品。对于需要用户目视验收的界面改动，用户说“没 bug 了”“可以了”或“验收通过”即视为提交和推送确认。
- 除非用户明确要求“只提交本地”或“不要推送”，否则“提交”默认包含创建 commit 并立即 push 当前分支。
- 禁止在本地 commit 成功后停止；只有远端 push 成功并验证分支不再 ahead 才算完成。
- push 失败时必须继续处理可恢复问题，无法恢复时明确说明代码仍未被团队共享。
- 最终报告必须包含 commit 哈希、分支、远端推送状态、测试结果和剩余未提交改动。

### Test Structure

测试文件按照源代码包结构组织，镜像源代码目录：

```
test/
├── elfie/
│   ├── brain/
│   │   ├── emotion/         # 情绪系统测试
│   │   ├── context/         # 上下文与认知协调测试
│   │   ├── memory/          # 记忆测试
│   │   └── energy/          # 能量测试
│   ├── body/
│   │   ├── anatomy/         # 解剖学测试
│   │   └── reflex/          # 反射弧测试
│   ├── nervous_system/
│   │   ├── actuators/       # 执行器测试
│   │   ├── sensors/         # 传感器测试
│   │   └── reflex/          # 反射测试
│   └── body/
│       ├── native/          # Native 身体测试
│       ├── headless/        # Headless 身体测试
│       └── external/        # External 身体测试
├── nest/                    # 活动空间和 Godot 协议测试
├── ai_runtime/              # AI 运行时测试
├── app/                     # 产品功能、接口、基础设施和编排测试
├── devtools/                # 隔离开发工具测试
├── godot/                   # Godot 源资源契约测试
├── architecture/            # 目录和依赖边界契约
└── e2e/                     # 产品全链路测试
```

**新增测试规则**：
- 测试文件必须放在对应包路径（镜像源代码结构）
- 每个测试目录必须有`__init__.py`
- 使用绝对导入：`from elfie.brain.emotion import ...`
- 禁止在`test/`根目录直接放置测试文件

## Configuration

### LLM Runtime
- Production config is loaded from `${ELFIE_HOME:-~/.elfienest}/config.yaml`
- Falls back to environment variables: `OLLAMA_HOST`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `QWEN_API_KEY`
- Default local model: `qwen3.5:0.8b` via Ollama

### Creature Configs
- `elfie/profile/defaults/personality.yaml` - 默认 Big Five 人格和说话风格
- `elfie/profile/defaults/capabilities.yaml` - 默认动作能力
- `elfie/profile/defaults/system_limits.yaml` - 默认关节、能量和疲劳限制
- 每只精灵自己的稳定配置保存在其数据目录的 `profile.yaml`

## Godot Integration

The engine runs dual servers:
- **HTTP port 8000**: Static audio file serving (edge-tts synthesized speech)
- **WebSocket port 8765**: Real-time bidirectional communication with Godot client

When Godot connects, actions are sent as `go_to`, `speak_event` events. Without Godot, runs in terminal-only mode.

## Godot 操作技能（强制规则）

- 打开、运行、验证、截图或关闭 Godot 前，必须读取并遵循 `.agents/skills/godot-project-operator/SKILL.md`。
- 必须先检查已有 Godot 进程；禁止使用 `open -n` 创建重复实例。
- 编辑器和游戏运行窗口只能按任务需要保留一个。短时 headless 验证必须同步等待退出。
- 必须核对 `project.godot` 声明的 Godot 版本；版本不匹配时，未经用户明确同意不得打开可编辑项目。
- 操作前后检查 Git 工作区，禁止擅自保留 Godot 自动生成的项目版本或导入元数据变更。

## 设计文档语言（强制规则）

- 后续新增或改写的产品设计、交互设计、架构设计、技术方案等设计文档，正文必须使用简体中文。
- 文件路径、代码标识符、API 名称、协议字段和第三方产品名可以保留英文，但必须用中文说明其含义。
- 禁止新增只有英文正文、没有中文说明的设计文档。

## 开发者调试平台隔离（强制规则）

- 单精灵调试平台仅供本地开发和调试 `elfie` 模块使用，不属于普通用户产品界面。
- 调试平台必须使用独立启动入口、独立本地网址、独立前端资源和独立数据目录。
- 禁止为了实现调试平台而修改或复用 `app/interfaces/web/static/` 下的普通用户前端页面。
- 禁止在普通用户导航、生产服务入口或安装后的用户界面中暴露调试平台。
- 调试平台可以复用项目的视觉变量和基础技术栈，但不能依赖 `ElfieNestEngine`、Godot、群聊房间或普通用户鉴权流程才能运行。

## Security: 密钥与敏感信息管理（强制规则）

> **绝对禁止将 API Key、Secret、Token、密码等敏感信息以明文形式写入代码或配置文件中并提交到 Git。**

### 强制规则

1. **禁止明文密钥**：任何 API Key（如 `sk-xxx`、`pk-xxx`、`AIzaxxx`、`AKIAxxx`、`ghp_xxx` 等）不得以字符串字面量出现在 `.py`、`.yaml`、`.yml`、`.json`、`.md` 等任何被 Git 跟踪的文件中。
2. **使用环境变量**：所有密钥必须通过环境变量读取（`os.environ.get("API_KEY")`），或从已 gitignore 的用户数据配置加载（如 `${ELFIE_HOME}/config.yaml`、`${ELFIE_HOME}/.env`）。
3. **配置文件占位符**：示例配置中使用占位符（如 `<your-api-key-here>`、`${API_KEY}`），不得填写真实密钥。
4. **已 gitignore 的敏感文件**：`config.yaml`、`.env` 和本机 Runtime 配置已在 `.gitignore` 中，不得移除对应保护规则。
5. **Pre-commit 钩子**：项目已安装 `.git/hooks/pre-commit`，提交前自动扫描密钥模式。如检测到疑似密钥，提交将被阻止。不要使用 `--no-verify` 绕过。

### 正确做法

```python
# ✅ 正确：从环境变量读取
api_key = os.environ.get("OPENAI_API_KEY", "")

# ✅ 正确：从 gitignored 配置文件加载
config = load_config(os.environ["ELFIE_HOME"] + "/config.yaml")
```

```yaml
# ✅ 正确：使用占位符
api_key: ${OPENAI_API_KEY}  # 从环境变量注入
```

### 错误做法

```python
# ❌ 错误：明文硬编码
api_key = "<never-hardcode-api-key>"
```

```yaml
# ❌ 错误：明文写在配置文件中
api_key: <never-hardcode-api-key>
```

## Notes

- Comments and config files are in Chinese
- The `.elfie_memories.json` file persists episodic memories between runs
- `download_novel.py` is a standalone utility, not part of the simulation
