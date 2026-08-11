# Elfie 模块

> 中文版：本文件 · [English](README.md)

## 模块定位

`elfie/` 实现一只完整精灵：稳定档案、三层脑、记忆与内稳态、神经系统、可替换
身体、数字通信和认知过程中可用的技能。

本页描述当前包。规范性迁移目标见
[Elfie 内部架构契约](../docs/zh/developer/contracts/elfie.md)，已知实现债务见
[Elfie 一致性台账](../docs/zh/developer/conformance/elfie.md)。其中，技术身体、渠道和
持久化实现最终下移到 Infrastructure，Skills 移入 Brain；这些变化不修改宏观系统契约。

## 负责与不负责

负责：

- 单只精灵的身份、外貌、人格、能力与稳定限制；
- 感知帧、上下文、皮层决策、输出路由和执行回执闭环；
- 情绪、能量、长期记忆和精灵自身时钟；
- 身体身份、能力、类型化命令/事件、Registry、Binding 和神经系统语义；当前
  Headless、Native、External 实现是迁移路径，不是技术实现的最终所有权；
- 精灵自身的数字消息通道和技能白名单。

不负责：

- 账户、Web/API、桌面窗口或产品服务生命周期；
- 保存房间、家具、坐标、Godot 场景或 Nest 居民表；
- 选择产品级模型供应商、保存 Runtime 配置或实现模型工具；
- 组合真实精灵与 Nest；该职责只属于 `app.orchestration.NestSession`。

## 目录地图

```text
elfie/
├── elfie.py             # 单精灵门面与生命周期
├── factory.py           # Profile、Body、Communication、Runtime 装配
├── cognitive_context.py # 认知所需的个体上下文来源
├── cognitive_runtime.py # Coordinator、Router 与 worker 生命周期组合
├── message_types.py     # 跨边界 ID、Actor、时间和错误基础类型
├── profile/             # 身份、物种、外貌和稳定 Profile
├── brain/               # Workspace、上下文、情绪、能量、记忆和决策
├── nervous_system/      # 感知规范化、过滤、反射和物理输出
├── body/                # Headless、Native、External 可替换身体
├── communication/       # 不经过 NervousSystem 的数字消息通道
└── brain/skills/        # 语义 Skill 目录和授权策略
```

## 入口

- `elfie.Elfie`：一只完整精灵的门面和异步生命周期；
- `elfie.ElfieFactory`：创建或从配置目录恢复精灵；
- `elfie.brain.PerceptualWorkspace`：接收并封装类型化感知；
- `elfie.brain.BrainCoordinator`：生成认知帧、上下文和皮层回合；
- `elfie.brain.DecisionPlan`：皮层输出的类型化决策；
- `elfie.brain.output_router.OutputRouter`：把决策路由到身体、通信或内部执行器。

只有 `elfie.Elfie` 与 `elfie.ElfieFactory` 是稳定的生产聚合入口。以上深层导入描述当前
内部实现和聚焦测试使用的模块 API；App 生产代码不得直接协调这些可变内部对象来组装
Elfie。

核心闭环是：

```text
Body -> NervousSystem ----\
                          -> PerceptualWorkspace -> BrainCoordinator
Communication ------------/                         -> DecisionPlan
                                                     -> OutputRouter
ExecutionReceipt ----------------------------------> PerceptualWorkspace
```

物理时钟、感知收集、模型推理和输出执行彼此解耦。历史同步认知入口已从产品
路径移除；调用方应通过类型化感知、认知生命周期和输出回执协作。

类型化边界由 Pydantic v2 frozen model 或 discriminated union 定义。Pydantic
模型是内部契约的唯一事实源；需要 JSON Schema 时对公开模型调用
`model_json_schema()` 按需生成，不在仓库中维护 Schema 文件或导出脚本。

## 依赖方向

```text
app/orchestration ──> elfie
elfie.elfie ──> profile + brain + nervous_system + body + communication
brain/output ──> 抽象 Food、模型、工具与执行端口
```

`elfie/` 不反向导入 `app/`、`nest/` 或 `ai_runtime/`。模型与 Food 访问使用 Elfie
自有 Port，由 Bootstrap 直接注入具体 Infrastructure Adapter；普通模型/工具调用不经过
App Orchestration。

## 运行与调试

从仓库根目录运行单精灵和认知闭环检查：

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q test/elfie/

UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q \
  test/elfie/test_cognitive_lifecycle.py \
  test/elfie/brain/test_perceptual_workspace.py \
  test/elfie/brain/test_coordinator.py \
  test/elfie/brain/test_output_router.py
```

完整环境准备和质量门见 [`CONTRIBUTING_zh.md`](../CONTRIBUTING_zh.md)；跨模块时序见
[`docs/zh/developer/`](../docs/zh/developer/)。

## 对应测试

- `test/elfie/`：单精灵门面、工厂、身份和跨子模块组合；
- `test/elfie/brain/`：感知、上下文、决策、情绪、能量和记忆；
- `test/elfie/body/`、`test/elfie/nervous_system/`：身体与物理边界；
- `test/elfie/communication/`、`test/elfie/brain/skills/`：消息与技能；
- `test/architecture/test_elfie_cognitive_contracts.py`：认知入口、依赖方向、
  Pydantic 契约和磁盘 Schema 禁令。
