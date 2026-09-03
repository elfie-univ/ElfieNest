# ADR-0032：Reasoning 拥有 Context Workspace，Memory 只拥有持久记忆

**状态：** 已接受
**日期：** 2026-08-31
**范围：** Reasoning 上下文、Memory 边界与单 Turn Agent 循环

## 背景

既有 Brain 文档一度把“工作记忆”写在 Memory 系统中，但 Memory 详细设计又明确不拥有
Reasoning 的完整上下文，当前源码也已经把有界对话历史放在 `elfie/brain/reasoning/`。
与此同时，`workspace` 既指一级 Event Workspace，也被非正式地用于模型上下文，因而留下
三种冲突解释：Memory 可能拥有当前对话，Event Workspace 可能是通用认知草稿区，或者每次
模型调用都接收一份调用方拥有的完整 Conversation。

这些解释会建立重复事实源，也无法一致定义上下文压缩、多次 Recall、基于回执的回复历史和
重启恢复。

## 决策

接受 [Reasoning Core 单 Turn Agent 详细设计](../designs/elfie-reasoning-core.md)，并把
Brain 契约升级到 1.4。

1. `Event Workspace` 继续作为第 1 系统并保留 `workspace/`；它只拥有事件 Lane、准入和
   不可变单域 `TurnFrame` 的形成。
2. `Reasoning Context Workspace` 是第 8 系统内部组件，拥有有界最近交替对话、活跃话题、
   带来源的上下文摘要、本 Run Observation、待确认 Memory handoff 和自己的有界恢复 checkpoint。
3. Memory 只拥有持久 Episode、知识、人物、关系、来源、检索和生命周期维护；不拥有短期
   conversation tail、context summary、Run 草稿状态或通用工作缓冲。
4. Reasoning 接收 `TurnFrame` 与其他 owner 的只读快照，而不是调用方拼好的完整
   Conversation；它从自己的 Context Workspace 读取相关会话分区。
5. 每个 Turn 都执行基础 Recall。Agent Loop 可以通过 Memory Bridge 再次请求 Recall，同一
   Run 内的查询绑定一个 Memory revision。Reasoning 选择查询意图和时机，Memory 拥有检索、
   冲突、校验与提交。
6. Prompt 压缩生成 Reasoning 自有、带来源的 `ContextSummary`；持久捕获是另一条完整
   `ClosedEpisode` 来源与类型化候选交接，不能把有损模型摘要直接当作 Memory 事实。
7. Reasoning 是只完成一个 Turn 的有界 Agent。`DIRECT` 与 `DELIBERATE` 只选择推理深度；
   Food 提供模型角色与回退，认知能力是独立阶段门。P0 主人聊天启用 Memory，关闭 Skill、
   Tool 和 Worker。
8. 回复只有在投递 Receipt 完成后才进入 Context Workspace。Run 在一个 `TurnDecision` 处
   结束，外部执行和 Settlement 不会重新打开它；所有跨 Turn 等待都属于 Persistent Activity。

## 后果

- Brain 只有一个事件工作区和一个 Reasoning 内部上下文工作区；两者不互相改名，也不产生
  第十一个心智系统。
- 对话连续性、Prompt 预算与压缩有了唯一 owner，不再把持久 Memory 当 Token 缓冲区。
- 所有 Reasoning 深度都能使用 Memory，Memory 不再被藏进“辅助模式”。
- 当前有界历史、上下文编译器、Recall Reader 和 `ReasoningRun` 已在原有生产链上完成
  P0 主人聊天迁移。上下文摘要、逐步骤重建、固定 revision 的按需 Recall、聊天复杂度路由
  和语义完成判断由永久聚焦测试及已退役台账防复活门禁守护。后续 Skill、Tool 或 Worker
  能力不属于 P0；如需采用，必须另立限定范围的设计与一致性工作。
- 本次治理变更不重命名源码目录，也不实现 Tool、Activity 或 Runtime 行为。

## 被否决的方案

明确否决：新增 Memory 所有的工作缓冲模块；把最近对话和 Prompt 摘要放进持久 Memory；
把 Event Workspace 变成通用 Agent 草稿区；每次 Reasoning 调用都传入可变完整 Conversation；
让模型直接读写 Memory；把压缩文本直接当作持久事实；以及用 Food allow-list 绑定
`DIRECT/DELIBERATE`。
