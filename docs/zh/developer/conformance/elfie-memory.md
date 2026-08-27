# Elfie Memory 一致性

> 状态：当前分支实现已完成；真实 Ark 评测的机器硬门和软质量门均已通过，人工复核和生产切换仍阻止第一阶段晋级<br>
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
| MEM-008 | P0 | 阻塞 | 确定性结构门禁和已授权的真实 Ark 候选/裁判运行现在均通过；负责人体验复核尚未完成，因此第一阶段尚未晋级。 | 可重放脱敏报告必须在 Stage 1 晋级前证明结构门禁、来源锚定、关系/冲突、重启和延迟。 | target=设计第 9.7 节及 `docs/.internal/elfie-stage1-memory-backed-chat-execution-plan.md`；inventory=`devtools/evals/stage1_chat_ark.py`、场景集和聚焦测试；references=`build/evaluations/stage1-chat/e1-ark-fixed-v2/report.json`；verification=确定性 E1 81 项测试通过、真实 Ark 候选 36 次和裁判 24 次调用、机器硬门通过、五项 Ark 质量维度全部通过（异星边界最差 5、历史 4、身份 5、记忆 grounding 5、自然度 4）、持久化扫描退出码 0；residuals=负责人体验复核和单独批准的生产数据切换仍待完成。 | Ark 鉴权和结构化裁判返回均通过，报告未写入密钥。 |

## 剩余验收顺序

1. 完成人工体验复核并记录晋级决定。
2. 另行批准并执行生产数据切换；开发迁移已经完成。

要求的只读持久化盘点命令是：

```text
uv run --no-sync python scripts/governance/persistence/scan.py --project-root . --check
```

修改 schema 后必须再次运行。每一行只有在 target、inventory、references、verification 和 residuals 五类信息都记录完整后才能关闭。MEM-008 在人工验收完成前保持阻塞。
