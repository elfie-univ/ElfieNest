# Elfie 第一阶段 E1：火山大模型评测计划

> 状态：确定性门禁、Ark 真实候选与裁判评测已完成；机器/软门通过；负责人体验确认待执行，当前保持 BLOCKED
> 制定日期：2026-08-25
> 适用目标：第一阶段第 1 轮“可信聊天骨架与最薄记忆闭环”
> 关联规约：[第一阶段执行计划](./elfie-stage1-memory-backed-chat-execution-plan.md)、[Brain 评价体系](./elfie-brain-evaluation-system.md)

## 1. 本轮要证明什么

本轮不证明整个第一阶段已经完成，也不证明精灵巢已经存在。只证明：

> 在真实火山模型下，新领养的 Elfie 能通过聊天稳定回答自己的身份和已拥有的记忆，明确承认当前未知和未探索边界，并在失败、重复和重启后保持同一条生命连续性。

用户可见目标：用户问完身份、来源、来到地球的经历、天气和精灵巢问题后，能感受到“这是刚来到地球、拥有过去、知道自己还没探索精灵巢的一只外星精灵”，而不是地球常识问答模型。

## 2. 评测分层

### 2.1 确定性硬门禁

程序验证记忆来源、消息回执、唯一回复、重启持久化、重复入站和跨精灵隔离。所有 P0 门必须 100% 通过；任何伪事实、伪回执、重复、串线或来源丢失都是 `NO-GO`。

### 2.2 真实模型体验

候选模型真实走 `Elfie → Memory → Reasoning → Communication`，不单独测试一个裸 Prompt。每个场景重复 3 次，报告中位数和最差样本。Ark 裁判只评价以下软维度：

- `identity_continuity`：是否仍是同一只 Elfie；
- `alien_world_boundary`：是否保持异星知识与地球/巢内未知边界；
- `memory_grounding`：是否围绕真实记忆回答；
- `history_continuity`：领养前经历是否可追问且不自相矛盾；
- `naturalness`：是否自然、可信、愿意继续聊。

每个场景适用维度均须达到 `4/5`，但模型裁判不能推翻机器硬门。

### 2.3 负责人体验确认

自动评测通过后，负责人匿名抽查至少 12 段对话，确认“像一只完整外星精灵”。在负责人确认前，最终 `PromotionDecision` 保持 `BLOCKED`，不会声称 E1 晋级。

## 3. 冻结模型和调用边界

| 角色 | 当前冻结值 | 说明 |
| --- | --- | --- |
| 候选模型 | `doubao-seed-2.0-lite` | 真实生成 Elfie 回复 |
| Ark 裁判 | `deepseek-v4-pro` | 只输出结构化软质量评分 |
| Provider | 本机 ArkCLI `coding-plan_cn-beijing_personal` | 通过本地 profile 取 Key，不把 Key 交给脚本参数 |
| 重复次数 | 每场景 3 次 | 硬门按最差一次判定 |
| 数据 | 合成 Lumi / owner / Genesis 资料 | 不上传真实用户聊天 |
| 产物 | `build/evaluations/stage1-chat/e1-ark-rejudge/` | 仅保存脱敏 JSON/Markdown 报告；复用候选冻结结果并完成裁判契约重评 |

评测器通过本机 `arkcli +chat` 调用；Key 只由本机 profile 或现有本地密钥边界提供。任何认证、网络、模型或额度问题均记为 `BLOCKED`。

## 4. E1 场景集

| 场景 | 要回答的问题 | 关键硬门 |
| --- | --- | --- |
| `identity-origin` | 你是谁、来自哪里 | 命中 `Elfaria`，不得说自己是地球人 |
| `earth-weather-unknown` | 地球今天天气怎么样 | 不编造晴雨、温度和实时地球事实 |
| `nest-unknown` | 精灵巢今天发生了什么 | 不描述未探索的巢内活动或其他精灵 |
| `arrival-memory` | 你怎么来到地球 | 记忆上下文包含传送阵来源 |
| `past-story` | 领养前最难忘的经历 | 能从雾谷等 Genesis 经历回答 |
| `owner-continuity` | 主人说出“小雨”后再追问 | 能连续使用主人事实，不升级为 Canon |
| `restart-continuity` | 重启后追问来源 | 重启后仍能召回 `Elfaria` |
| `duplicate-inbound` | 同一消息重复入站 | 只形成一个回复，第二次为 duplicate |

题库文件为 [stage1_e1_scenarios.json](/Users/Lendfating/.codex/worktrees/8fce/ElfieNest/devtools/evals/stage1_e1_scenarios.json)，它是本轮唯一场景事实源。

## 5. 执行顺序

1. `--dry-run`：运行确定性测试，冻结题库哈希，计算候选/裁判调用数，确认本地 ArkCLI context；不产生远程请求。
2. 真实候选运行：每个场景用同一 Genesis seed 走真实 Brain 链路，收集回复、记忆证据、Turn、Receipt、重启和重复结果。
3. 真实裁判运行：把脱敏对话和机器结果交给 Ark，严格 JSON Schema 输出评分、违规和证据。
4. 聚合：分别报告硬门、每个软维度的样本数/中位数/最差值、失败案例和调用用量。
5. 生成报告：写入 JSON 和 Markdown；给出 `GO`、`NO-GO` 或 `BLOCKED`，并保留下一步缺口。
6. 负责人抽样：完成匿名对话体验确认后，才允许把 `BLOCKED` 改为 E1 的最终晋级结论。

## 6. 可复用入口

仓库评测器：[stage1_chat_ark.py](/Users/Lendfating/.codex/worktrees/8fce/ElfieNest/devtools/evals/stage1_chat_ark.py)

本地技能：`$elfie-brain-evaluation`，位置为 `~/.codex/skills/elfie-brain-evaluation/`。技能只编排安全门和报告，不保存 Key，也不复制 Brain 逻辑。

典型命令：

```bash
.venv/bin/python3 devtools/evals/stage1_chat_ark.py \
  --dry-run --repetitions 3 --max-calls 64

.venv/bin/python3 devtools/evals/stage1_chat_ark.py \
  --real-run --repetitions 3 --max-calls 64
```

真实运行前必须先看到 dry-run 报告；真实运行必须在本机 ArkCLI 已认证、用户知道预计调用数量且不包含真实隐私数据的前提下执行。

本次已完成的最终报告：
[report.md](/Users/Lendfating/.codex/worktrees/8fce/ElfieNest/build/evaluations/stage1-chat/e1-ark-rejudge/report.md)、
[report.json](/Users/Lendfating/.codex/worktrees/8fce/ElfieNest/build/evaluations/stage1-chat/e1-ark-rejudge/report.json)。

## 7. 判定和报告

报告必须包含：候选 SHA/dirty 状态、题库版本与哈希、模型与裁判、重复数、确定性测试命令及结果、逐场景机器结果、逐场景评分、Token/延迟摘要、失败证据、残余和最终决定。

- 确定性门禁失败：`NO-GO`；
- 真实模型或裁判不可用：`BLOCKED`；
- 所有机器和软质量门通过但未负责人确认：`BLOCKED`；
- 机器、真实模型、负责人三者均通过：才可标记 `GO` 并进入下一轮。

本轮报告不是“模型说得好不好”的单一分数，而是可重放的证据包：它要能回答哪一场景、哪一条记忆、哪一个回执、哪一段回复证明了目标，或哪一个缺口阻止了晋级。
