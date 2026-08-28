# Elfie Memory 一致性

> 状态：当前分支实现已完成；真实 Ark 机器硬门已通过，但当前候选的软质量门有一项 `memory_grounding=3`，第一阶段仍因修复、人工复核和生产切换阻塞<br>
> 基线：2026-08-27<br>
> 目标：[Elfie Memory 设计](../designs/elfie-memory-architecture)

这是临时迁移台账，记录当前实现相对于 Memory 设计的精确缺口以及关闭所需的证据。它不重定义 Memory 模型，不授权修改数据库，也不是开发过程日志。

## 实施台账

| ID | 严重度 | 状态 | 当前差距 | 目标与关闭门槛 | 证据 / 参考 | 残余 |
| --- | --- | --- | --- | --- | --- | --- |
| MEM-001 | P0 | 已关闭 | 目标 Adapter 已用审查后的 Episode、节点、Assertion 和 Evidence 表替代旧实体/子类型及嵌入边布局。 | 目标表、约束、所有权和可重建词法投影已实现，不存在第二套边事实源。 | target=设计第 9.1–9.2 节；inventory=`infrastructure/persistence/memory/schema.py`、`node_store.py`、`edge_store.py`；references=持久化扫描；verification=目标 schema/往返/重开测试及 332 项组合受影响测试；residuals=已有线上旧库仍需下方的显式导入/切换。 | 开发目标无残余。 |
| MEM-002 | P0 | 已关闭 | 闭合 Episode 具备完整内容、来源 ID、哈希、幂等和重启安全写入；已完成互动候选和 Genesis 种子都走先保存来源的路径。 | 一个经过校验的 Episode 是详细历史来源；Memory 不负责合并原始回合。 | target=设计第 3、9.4 节；inventory=`sqlite_episode_store.py`、`memory_system.py`、`genesis/initializer.py`；references=Episode 和 E1 垂直切片测试；verification=重复提交、哈希、低强度候选、Genesis 来源链和重开测试；residuals=上游事件边界仍负责闭合事件；旧 `record_episode` 仅作兼容接口。 | 目标路径无残余。 |
| MEM-003 | P0 | 已关闭 | 节点、别名、描述、提及、带限定 Assertion、Evidence 和多对多关联已持久化；身份合并会重定向历史并保留冲突。 | 独立支持、极性、视角、时间和反驳关系不会被裸三元组覆盖。 | target=设计第 4、9.1–9.2 节；inventory=`sqlite_graph_store.py`、`schema.py`；references=source-first 图测试；verification=跨 Episode 别名/身份解析、合并重定向、有来源断言和冲突/证据往返测试；residuals=旧数据库已经覆盖的历史版本不能自动恢复。 | 旧数据可能存在不可恢复冲突。 |
| MEM-004 | P0 | 已关闭 | 有界 Worker 领取 Episode，校验有来源模型提案或使用保守确定性抽取，再以可重试的有来源投影在单事务中提交。 | 规范身份、证据绑定、相容合并和冲突保留是确定性的；来源 Episode 在失败时不丢失。 | target=设计第 5、9.4 节；inventory=`elfie/brain/memory/consolidation.py`；references=source-first Worker 测试；verification=模型来源校验、全局语义 ID、租约恢复、合并/冲突和来源保留测试；residuals=Provider 与调度仍是注入/运维选择；严格谓词注册表属于后续强化，不是 P0 依赖。 | 写事务不会等待无界模型调用。 |
| MEM-005 | P0 | 已关闭 | `RecallRequest` 已执行确定性的 Basic/Text 候选检索，再做有界 Local Graph 遍历、来源获取、关系/时间过滤和限制控制。 | 文本覆盖罕见/未解析表述；图遍历覆盖明确关系；来源和冲突保持可见。 | target=设计第 6、9.5 节；inventory=`sqlite_retrieval_store.py`、`node_store.py`、`sqlite_graph_store.py`；references=source-first 检索测试；verification=罕见词/别名、人物关系网、知识对象、种子、时间窗口、跳数/限制和代表性延迟检查；residuals=Global/社区和向量检索仍是后续投影。 | 当前词法投影有意保持简单且可重建。 |
| MEM-006 | P0 | 已关闭 | `RecallBundle` 及确定性渲染器已实现；Reasoning Memory reader 消费独立的带真实来源 ID 的类型化项目。 | 上层通过语义契约取得有界节点、Assertion、路径、Episode、Evidence 和冲突，不读取原始 SQL。 | target=设计第 6、9.5 节；inventory=`memory_records.py`、`recall_renderer.py`、`reasoning/memory_context.py`；references=推理和渲染测试；verification=稳定渲染、字符硬上限、来源和类型节点不合成虚假来源测试；residuals=最终自然语言叙述仍由 Reasoning 负责。 | Memory 边界无残余。 |
| MEM-007 | P0 | 开发已关闭 | 已实现新库导入器、只读源保护、数量/摘要/哈希对账、租约恢复和保留操作。 | 导入按 Episode 优先、可审计且可回退；不修改旧库，不引入长期双写。 | target=设计第 9.6 节；inventory=`migration.py`、`sqlite_memory_store.py`；references=ADR-0018 和持久化规则；verification=旧库导入、可迁移 Episode 哈希匹配、证据映射、重开和归档/遗忘测试；residuals=生产数据切换未执行，需单独明确批准。 | 未接触线上用户库。 |
| MEM-008 | P0 | 阻塞 | 确定性结构门禁和已授权的真实 Ark 运行通过机器硬门，但当前候选有一条软质量样本未达标；负责人体验复核尚未完成，因此第一阶段尚未晋级。 | 可重放脱敏报告必须在 Stage 1 晋级前证明结构门禁、来源锚定、关系/冲突、重启和延迟。 | target=设计第 9.7 节及 `docs/.internal/elfie-stage1-memory-backed-chat-execution-plan.md`；inventory=`devtools/evals/stage1_chat_ark.py`、场景集和聚焦测试；references=`build/evaluations/stage1-chat/e1-ark-real-136eebaa/report.json`；verification=确定性 E1 86 项测试通过、33/33 个重复机器场景通过，真实 Ark 候选运行有 1 次 provider 空响应并由既有失败收束路径恢复，裁判 33 次调用；机器硬门通过，但 `world-species-common` 第 2 次的 `memory_grounding=3`（最差，其余维度达门槛），持久化扫描退出码 0；该场景单独 3 次诊断复测的机器门和软质量门均通过；residuals=修复并重新运行完整软质量门、负责人体验复核和单独批准的生产数据切换仍待完成。 | Ark 鉴权和结构化裁判返回均通过，报告未写入密钥。 |

## 当前基线后的优化台账

下面记录基线之后的当前开发优先级；它们不是对 `MEM-001`–`MEM-008` 已关闭/阻塞状态的改写。

| ID | 优先级 | 状态 | 当前差距 | 下一验收门 |
| --- | --- | --- | --- | --- |
| OPT-001 | P0 | 已关闭 | 有界切片现已让冻结的 E1 fixture 走类型化 Elfaria World Canon/Genesis 路径，移除推理提示中与 Profile/Canon 重复的身份事实，覆盖跨文件发布失败时的清理，并通过确定性 E2/E3 门。 | OPT-001 无后续实现门；负责人体验复核归 MEM-008 第一阶段门。 |
| OPT-002 | P0 | 已关闭 | WorkingContext 已能闭合有界话题 Episode，在推理前先落盘来源，抽取带归因的主人/人物事实，保留别名并支持显式纠正链。 | 确定性持续学习回归的八类 source-first 场景全部通过；第一阶段整体负责人体验复核仍归 MEM-008。 |
| OPT-003 | P1 | 暂缓 | 长期压缩、遗忘、归档、增长和延迟还未做长期运行验证。 | 在 OPT-001/002 通过后，建立有界增长和可恢复生命周期评测。 |
| OPT-004 | P1/P2 | 暂缓 | 真实精灵巢观测、活动和多精灵互动尚未进入当前聊天闭环。 | 第二阶段真实巢场景接入后，再验证具身记忆和世界事件来源。 |

OPT-001 与 OPT-002 可以并行开发，但必须使用各自功能分支和独立评测；两者完成后再进行组合回归。OPT-003
和 OPT-004 在此之前不启动。

OPT-001 第一版证据（2026-08-28）：target=OPT-001 计划第 3–5 节；inventory=`config/world/elfaria.yaml`、
配置 registry/schema、`elfie/genesis/{contracts.py,initializer.py}`、
`infrastructure/persistence/elfie_workspace/adoption_profiles.py`；references=Elfaria 世界 Canon/物种卡与类型化
Genesis 测试；verification=类型化 fixture 编译测试、15 项聚焦领养/评测测试、受影响的 Memory/Reasoning 测试、
Ruff、`git diff --check` 及既有持久化扫描；Canon 共 42 条事实，每个已发布物种的领养按资格选择 40 条知识 seed，
并生成 5 段 Episode、13 个私有关系对象；注入发布失败测试覆盖物料化清理，推理提示不再重复 Profile/Canon 已提供的
Selfhood 身份事实。未做生产回填；OPT-002 已关闭，OPT-003/004 按计划暂缓。
类型化 `stage1-e1.v2` fixture 已通过确定性门，并完成一次真实 Ark 单重复运行（26 次 provider 调用；机器门和裁判门均通过），
报告位于 `/private/tmp/elfie-e1-real-20260828-final2/report.md`。
OPT-001 的确定性 E2/E3 门也已通过：2 个 published 物种、每物种 96 条合资格知识问法、240 条 unknown 边界问法，
以及 24 个传记组合（每物种 4 个 life stage × 3 个 seed），报告位于 `/private/tmp/elfie-opt001-e2e3-20260828/report.json`。
负责人体验复核仍是 MEM-008 的第一阶段门；未做生产回填；OPT-002 已关闭，OPT-003/004 按计划暂缓。

OPT-002 实现与评测证据（2026-08-28）：target=持续学习 source-first 流程与 WorkingContext 边界；inventory=`elfie/brain/reasoning/conversation_context.py`、`coordinator.py`、`settlement.py`、`elfie/brain/memory/consolidation.py`、`infrastructure/persistence/memory/{schema.py,sqlite_memory_store.py,sqlite_graph_store.py}`；references=OPT-002 开工文档 §3–§7 与 Memory 设计 §9.4–§9.5；verification=`devtools/evals/opt002_continuous_learning.py` 与 `test/devtools/evals/test_opt002_continuous_learning.py` 的八类场景全部通过：Episode 边界、实体/别名/歧义、主人纠正/重启、冲突、幂等重放、失败重试、投递失败边界、精灵隔离；组合受影响测试 36/36 通过，Ruff 和持久化扫描退出码 0，报告为 `build/evaluations/stage1-chat/opt002-136eebaa/report.json`；residuals=负责人体验复核和生产切换仍归 MEM-008/MEM-007，OPT-003/OPT-004 按计划暂缓。

## 剩余验收顺序

1. 修复当前候选的软质量失败样本并重新运行完整 E1 门。
2. 完成人工体验复核并记录晋级决定。
3. 另行批准并执行生产数据切换；开发迁移已经完成。

要求的只读持久化盘点命令是：

```text
uv run --no-sync python scripts/governance/persistence/scan.py --project-root . --check
```

修改 schema 后必须再次运行。每一行只有在 target、inventory、references、verification 和 residuals 五类信息都记录完整后才能关闭。MEM-008 在人工验收完成前保持阻塞。
