# AI Runtime 模块

> 中文版：本文件 · [English](README.md)

## 模块定位

`ai_runtime/` 是模型访问、供应商适配、算力/粮食策略、原生工具、安全权限、配置
存储和调用观测的运行时层，为上层提供与具体 Elfie 或 Nest 无关的推理能力。

## 负责与不负责

负责：

- 统一文本、多模态、流式与结构化生成请求；
- 模型目录、Provider 配置、路由策略和本地 Ollama 回退；
- 面向精灵的粮食配方、选择、验证和执行；
- 共享原生工具实现、权限检查和有边界的执行；
- `ELFIE_HOME` 数据路径、Runtime 配置、密钥解析和迁移辅助；
- 模型/工具调用观测、用量统计和本地 Runtime 验证。

不负责：

- 保存精灵身份、情绪、记忆、身体或 Nest 状态；
- 组合真实精灵、活动空间、Godot 或桌面生命周期；
- 实现账户、领养、聊天页面等产品用例；
- 恢复旧顶层 Python 包 `runtime/` 或为它增加兼容导入。

## 目录地图

```text
ai_runtime/
├── gateway/     # RuntimeAgent、请求模型、生成循环、流式与多模态入口
├── models/      # 模型目录、本地模型档案和注册表
├── providers/   # Ollama 与各 Provider 的配置和调用适配
├── policy/      # 任务分类和模型路由策略
├── food/        # 粮食配方、选择、规划、证据和执行
├── tools/       # 搜索、代码、文件和技能演化工具
├── safety/      # 工具权限管理
├── storage/     # ELFIE_HOME、配置、密钥和迁移辅助
├── setup/       # Runtime 初始化入口
├── usage/       # 调用事件和 token 用量观测
├── validation/  # Provider、模型、工具和粮食的本地验证
└── lab/         # Runtime 本地交互实验室
```

共享工具实现当前位于本目录。目标架构会拆解这个迁移包；个人 Skill 定义和学习状态
仍属于对应精灵工作区。

## 行为与迁移权威

Provider、模型、粮食、工具、持久化和验收的规范性定义统一位于
[模型、Food 与工具行为契约](../docs/zh/developer/contracts/ai-runtime.md)。目标所有权
由[系统架构契约](../docs/zh/developer/contracts/system.md)定义；目标架构不存在
`ai_runtime/` 模块。本 README 只描述当前迁移包。当前实现偏差单独记录在
[AI Runtime 实现一致性台账](../docs/zh/developer/conformance/ai-runtime.md)。

## 公开入口

- `ai_runtime.LLMRuntimeConfig`：加载模型、Provider 与 Runtime 策略；
- `ai_runtime.RuntimeAgent`：统一推理入口；
- `ai_runtime.RuntimeRequest`、`ai_runtime.RuntimeResult`：普通生成请求与结果；
- `ai_runtime.gateway.RuntimeAgent`：与根包相同的 Gateway 公开入口；
- `ai_runtime.lab.RuntimeLab`：仅供本地开发验证的交互实验室。

结构化生成使用 `RuntimeAgent.generate_structured()` 及
`StructuredRuntimeRequest`。调用者提交运行时请求，应用层负责把结果转换成
Elfie 认知端口所需的类型。

## 当前依赖方向

```text
app/orchestration ──> ai_runtime.gateway
app/features      ──> ai_runtime 的配置、策略、存储与验证公开入口
ai_runtime.gateway ──> models + providers + policy + food + tools + safety
```

Runtime 核心不依赖 `elfie/` 或 `nest/`，也不应知道真实精灵和活动空间对象。
当前 `ai_runtime/setup/runtime_setup.py` 会调用应用配置存储完成安装期写入；这是
现存的 setup 集成边界，不应扩展到 Gateway、Provider 或工具核心。

## 运行与调试

从仓库根目录运行 Runtime 测试：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q test/ai_runtime/

UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q \
  test/ai_runtime/test_runtime_agent.py \
  test/ai_runtime/test_structured_generation.py
```

本地 Runtime Lab 使用独立开发数据目录，避免读取生产配置：

```bash
ELFIE_HOME=/tmp/elfienest-runtime-lab \
  .venv/bin/python -m ai_runtime.lab
```

环境准备、密钥规则和统一质量门见
[`CONTRIBUTING_zh.md`](../CONTRIBUTING_zh.md)。

## 对应测试

- `test/ai_runtime/`：Gateway、Provider、模型、策略和工具；
- `test/ai_runtime/food/`：粮食配方、规划、证据和执行；
- `test/infrastructure/persistence/`：配置、密钥和数据边界；
- `test/ai_runtime/validation/`：本地验证器与 Runtime Lab；
- `test/architecture/test_project_structure.py`：当前源码根、旧 `runtime/` 包禁令
  和质量门入口。
