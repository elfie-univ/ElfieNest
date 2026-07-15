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
├── main.py              # Entry point - orchestrates runtime, elfie, and engine
├── elfie/               # ElfieIndividual - the creature with embodied cognition
│   ├── brain/           # Neocortex (LLM reasoning), context building
│   ├── body/            # Anatomy (biped/quadruped), somatic reflexes
│   ├── interface/       # Actuators (speech, motion), sensors, signal filters
│   └── config/          # Personality, capabilities, system limits (YAML)
├── elfienest/           # ElfieNestEngine - physics tick simulation
│   ├── engine.py        # Main loop, HTTP audio server, WebSocket API
│   ├── room.py          # Multi-creature room state management
│   └── godot_api.py     # WebSocket bridge for Godot 3D client
├── runtime/             # LLMRuntimeAgent - multi-provider LLM orchestration
│   ├── agent.py         # Main agent with tool calling loop
│   ├── config.py        # Provider configs (Ollama, OpenAI, DeepSeek, Gemini, Qwen)
│   ├── model_router.py  # Energy/complexity-based model selection
│   └── plugins/         # Tools: web_search, code_sandbox, skills_evolution
└── test/                # Unit tests for embodied perception
```

## Key Concepts

### Three-Layer Brain Architecture
1. **Neocortex (Cognition)**: LLM-based reasoning and decision making
2. **Limbic System (Core Systems)**: Emotions (amygdala), energy (hypothalamus), memory (hippocampus), context (thalamus)
3. **Body (Interface)**: Physical actuators, sensors, reflex arcs

### Main Loop Flow
1. `ElfieNestEngine.start_loop()` drives physics ticks
2. Each tick: `room.tick()` updates energy/emotion decay
3. For each active elfie: `perceive_and_respond()` triggers:
   - Brainstem reflex check (instant physical response)
   - Sensory signal filtering (noise reduction)
   - Thalamus context assembly
   - Neocortex LLM decision
   - Morphological action validation
   - Motor execution and speech synthesis

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
│   │   ├── cognition/       # 认知测试
│   │   ├── memory/          # 记忆测试
│   │   └── energy/          # 能量测试
│   ├── body/
│   │   ├── anatomy/         # 解剖学测试
│   │   └── reflex/          # 反射弧测试
│   └── interface/
│       ├── actuators/       # 执行器测试
│       └── sensors/         # 传感器测试
├── elfienest/               # 引擎测试
└── runtime/                 # 运行时测试
```

**新增测试规则**：
- 测试文件必须放在对应包路径（镜像源代码结构）
- 每个测试目录必须有`__init__.py`
- 使用绝对导入：`from elfie.brain.emotion import ...`
- 禁止在`test/`根目录直接放置测试文件

## Configuration

### LLM Runtime
- Config loaded from `runtime/runtime_config.json` (gitignored)
- Falls back to environment variables: `OLLAMA_HOST`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `QWEN_API_KEY`
- Default local model: `qwen3.5:0.8b` via Ollama

### Creature Configs
- `elfie/config/personality.yaml` - Big Five personality traits, speech style
- `elfie/config/capabilities.yaml` - What actions the creature can perform
- `elfie/config/system_limits.yaml` - Joint limits, energy constraints

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
- 禁止为了实现调试平台而修改或复用 `elfienest/ui/static/` 下的普通用户前端页面。
- 禁止在普通用户导航、生产服务入口或安装后的用户界面中暴露调试平台。
- 调试平台可以复用项目的视觉变量和基础技术栈，但不能依赖 `ElfieNestEngine`、Godot、群聊房间或普通用户鉴权流程才能运行。

## Security: 密钥与敏感信息管理（强制规则）

> **绝对禁止将 API Key、Secret、Token、密码等敏感信息以明文形式写入代码或配置文件中并提交到 Git。**

### 强制规则

1. **禁止明文密钥**：任何 API Key（如 `sk-xxx`、`pk-xxx`、`AIzaxxx`、`AKIAxxx`、`ghp_xxx` 等）不得以字符串字面量出现在 `.py`、`.yaml`、`.yml`、`.json`、`.md` 等任何被 Git 跟踪的文件中。
2. **使用环境变量**：所有密钥必须通过环境变量读取（`os.environ.get("API_KEY")`），或从已 gitignore 的本地配置文件加载（如 `runtime/runtime_config.json`、`.env`）。
3. **配置文件占位符**：示例配置中使用占位符（如 `<your-api-key-here>`、`${API_KEY}`），不得填写真实密钥。
4. **已 gitignore 的敏感文件**：`config.yaml`、`.env`、`runtime/runtime_config.json` 已在 `.gitignore` 中，不得移除。
5. **Pre-commit 钩子**：项目已安装 `.git/hooks/pre-commit`，提交前自动扫描密钥模式。如检测到疑似密钥，提交将被阻止。不要使用 `--no-verify` 绕过。

### 正确做法

```python
# ✅ 正确：从环境变量读取
api_key = os.environ.get("OPENAI_API_KEY", "")

# ✅ 正确：从 gitignored 配置文件加载
config = load_config("runtime/runtime_config.json")  # 该文件已被 gitignore
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
