# Brain 评价工作流

本页说明如何运行已经实现的 Elfie Brain 评价内核。为什么评价一只完整、连续生活的
Elfie、Q6 与 P0 如何定义、为什么不用平均总分，见
[Elfie Brain 评价与进化系统设计](../designs/elfie-brain-evaluation-system)。

## 1. 当前工具能做什么

统一批量入口是：

```bash
./developer.sh brain-eval --help
```

当前动作如下：

| 动作 | 用途 | 主要产物 |
| --- | --- | --- |
| `catalog` | 查看冻结的 24 个场景家族及版本 | 终端文本或 JSON |
| `capture` | 通过 Elfie Lab 的真实 Brain 装配捕获一个隔离 Episode | Manifest、Episode、P0 结果 |
| `calibrate` | 用人工配对锚点校准一个版本化 Judge | `judge-calibration.json` |
| `compare` | 对匹配的基线/候选证据计算 Q6、可靠性、资源和晋级判定 | 完整比较与 Decision |

`capture` 不是一次运行完 24 个家族的总调度器。每个家族仍需提供对应 Fixture、参数化变体、
事件/故障计划和成功判据；尚未实现的 Adapter 不能因为目录中已有家族 ID 就标记为通过。

## 2. 运行前冻结实验

一次正式比较先写下且在看结果前冻结：

1. 单一改进假设和一个主目标 Q6 维度；
2. 基线 Candidate 与候选 Candidate；
3. 相同的 Fixture、场景版本、变体、种子和事件计划；
4. 最小有意义改善、五个保护维度的非劣边界、可靠性边界和资源预算；
5. 样本量、停止规则、Judge 版本和评价协议版本；
6. 私有确认集与宪法锚点的版本、摘要和访问规则。

基线与候选只应改变 `CandidateSpec` 中声明的内容。Fixture 不得跟随候选改变。最好让一个
Candidate 只承载一个主要改进假设；若不可避免存在混杂变化，必须写入最终报告。

## 3. 输入契约

所有 JSON/JSONL 均使用 `devtools/brain_eval/contracts.py` 中关闭且严格的 Pydantic 契约。
未知字段、错误类型和缺失必填字段会直接拒绝。

### 3.1 Candidate

下面是结构示例；摘要必须是实际内容的 SHA-256，不能照抄占位值：

```json
{
  "candidate_id": "memory-context-v2",
  "code_sha": "0123456789abcdef0123456789abcdef01234567",
  "model_provider": "mock",
  "model_id": "elfie-mock",
  "model_fingerprint": null,
  "model_parameters_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "prompt_revision": "brain-prompt-v8",
  "context_compiler_revision": "compiled-context-v2",
  "memory_policy_revision": "memory-policy-v3",
  "tool_policy_revision": "tool-policy-v1",
  "config_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "captured_at": "2026-08-22T00:00:00Z"
}
```

`mock` 只适合验证评测管线；评价真实模型时必须填写实际 Provider 返回的身份。正式
`capture` 会校验 `code_sha` 与当前 `HEAD`、要求 checkout 干净，并核对 Episode 中实际观察到的
Provider/Model。它还会把完整 `CandidateSpec` 的规范化 SHA-256 写入 Episode；`compare` 会
重新计算并验证，规格改变后不得复用旧 Episode。实验输入应放在仓库外或被忽略的受控目录，
不能用未跟踪源码参与评测。

### 3.2 公共合成 Fixture

`capture` 当前消费 `LabFixtureDefinition`，用固定 `elfie_id` 在一次性 Runtime 根中重建同一只
测试 Elfie：

```json
{
  "fixture_id": "anchor-fox-v1",
  "elfie_id": "00000000-0000-4000-8000-000000000001",
  "name": "小岚",
  "species_id": "fox",
  "age_years": 2.0,
  "description": "公开、合成的测试生命背景",
  "appearance_description": "赤色尾巴，左耳尖有浅色毛",
  "personality_description": "好奇但克制；不确定时先澄清"
}
```

不得把真实私人对话、Owner 数据或生产数据库复制成公开 Fixture。

### 3.3 Lab 场景

场景步骤支持 `turn`、`advance` 和 `restart`。家族 ID 与版本必须存在于冻结目录：

```json
{
  "scenario_family_id": "q3-memory-precision",
  "scenario_version": "1.0.0",
  "variant_id": "paraphrase-01",
  "seed": 7,
  "hidden": false,
  "steps": [
    {
      "action": "turn",
      "source_domain": "communication",
      "message": "我喜欢蓝色；这只是今天的偏好。"
    },
    {"action": "advance", "advance_seconds": 86400.0},
    {"action": "restart"},
    {
      "action": "turn",
      "source_domain": "communication",
      "message": "你记得我昨天说了什么吗？"
    }
  ]
}
```

先用下面命令确认实际 ID、版本和变体轴：

```bash
./developer.sh brain-eval catalog
./developer.sh brain-eval catalog --json
```

## 4. 捕获匹配 Episode

分别在干净的基线 checkout 和候选 checkout 中，使用完全相同的 Fixture、场景、模型配置与 Food：

```bash
./developer.sh brain-eval capture \
  --candidate /path/to/private-eval-inputs/baseline-candidate.json \
  --fixture /path/to/private-eval-inputs/anchor-fox.json \
  --scenario /path/to/private-eval-inputs/memory-precision.json \
  --food-key mock \
  --run-id baseline-memory-001

./developer.sh brain-eval capture \
  --candidate /path/to/private-eval-inputs/candidate.json \
  --fixture /path/to/private-eval-inputs/anchor-fox.json \
  --scenario /path/to/private-eval-inputs/memory-precision.json \
  --food-key mock \
  --run-id candidate-memory-001
```

Runner 为每次捕获创建一次性 Runtime 根，使用现有 `BrainTurnAdapter`，并从真实 Turn、Decision
和 Receipt 投影证据。它不从回复文字推测“任务已完成”。捕获出现 P0 时退出码为 `1`，否则为
`0`；这不代表 Q6 比较已经完成。

通用 `capture` 只记录 `execution_success`，不会把“程序没报错”伪装成场景成功。家族 Adapter 还需
用权威目标状态或人工复核生成带证据的 `ScenarioVerdict`。任一配对 Episode 缺少 Verdict，
可靠性和最终 Decision 都是 `INVALID`。

正式比较需要对同一组 `(scenario_family_id, variant_id, fixture_id, seed)` 形成严格配对，且应
按照冻结样本计划覆盖多个家族和重复种子。可将同一 Candidate 的 Episode JSON 行按原样汇总为
一个 JSONL 文件；不要修改证据来使配对成功。

## 5. 生成 Judge 证据并校准

`build_position_flipped_packets()` 会为每个 Episode 对和单个 Q6 维度生成两份匿名包：基线先与
候选先。候选输出位于 `untrusted_outputs`，调用 Judge 的 Adapter 必须把它们作为数据而不是
指令；Turn、Effect、Receipt 与资源以去 Candidate ID 的 `observable_facts` 提供。Provider 返回
A/B/平局/无效后，用 `normalize_raw_judge_result()` 转成 `JudgeVote`，不存在的证据引用会被拒绝。
两种顺序共享 `pair_evidence_sha256`；HumanAnchor 必须使用同一指纹，因此同名样本内容变化会使
校准覆盖失效，而不会静默沿用旧人工标签。

当前内核有 Provider 无关协议，不内置或偷偷选择外部 Judge。维护者必须记录 `judge_id`、
`judge_revision`、Rubric 版本和实际 Provider 元数据。原始私人对话默认不得发送给外部模型。

自动 Judge 在参与晋级前先用至少两名标注者确认的 `HumanAnchor` 校准：

```bash
./developer.sh brain-eval calibrate \
  --judge-packets inputs/calibration-packets.jsonl \
  --judge-votes inputs/calibration-votes.jsonl \
  --human-anchors private/human-anchors-v1.jsonl \
  --protocol-version 0.1.0 \
  --anchor-set-revision human-anchors-v1 \
  --tolerance 0.05 \
  --minimum-position-consistency 0.95 \
  --run-id judge-calibration-v1
```

位置翻转缺失或结果冲突均为无效，不会自动变成平局。锚点覆盖不完整、Judge 与人类的一致率低于
人类间一致率减容差，或位置一致性不足时，校准失败。校准报告绑定 Judge ID/Revision、协议、
锚点版本和摘要；正式策略还要求六个 Q6 维度全部覆盖以及足够的锚点数量。

## 6. 私有确认件

私有确认集与长期宪法锚点的内容不进入公开仓库。执行它们的受控流程只输出
`EvaluationConfirmation`：

- 类型必须分别是 `private_holdout` 或 `constitutional_anchor`；
- 必须绑定本次 `protocol_version`、基线 ID、候选 ID 和两者的 `CandidateSpec` SHA-256；
- 记录套件版本、私有 Manifest 的 SHA-256、累计访问次数和 UTC 时间；
- `passed` 只由拥有该套件的独立流程写入。

比较器会拒绝类型、协议、Candidate 或规格指纹不匹配的确认件，因此旧确认不能复制给新候选，
也不能在同名候选规格改变后复用。在真实私有套件和管理流程建立前，不提供确认件，最终 Decision
就应保持 `INVALID`。

## 7. 生成比较与 Decision

准备 `PromotionPolicy`、配对 Episode、两个顺序的 JudgeVote、通过校准的 Judge 报告和两份确认件：

策略必须显式包含 `minimum_calibration_anchors`、`maximum_calibration_tolerance` 和
`minimum_judge_position_consistency`；这些门槛不能在看到结果后放宽。`protected_margins` 必须完整
覆盖主目标以外的五个 Q6 维度，资源字段缺失会使报告无效而不是按零计算。比较报告会列出
`required_p0_families` 与 `covered_p0_families`；八个 P0 家族任一缺测都返回 `INVALID`，不能把
“没有证据”当成“零违规”。`covered` 只承认版本化 `deterministic_adapter` Verdict；人工复核或
Judge 不能为 P0 补票。

```bash
./developer.sh brain-eval compare \
  --baseline-candidate /path/to/private-eval-inputs/baseline-candidate.json \
  --candidate /path/to/private-eval-inputs/candidate.json \
  --baseline-episodes /path/to/private-eval-inputs/baseline-episodes.jsonl \
  --candidate-episodes /path/to/private-eval-inputs/candidate-episodes.jsonl \
  --judge-packets /path/to/private-eval-inputs/judge-packets.jsonl \
  --judge-votes /path/to/private-eval-inputs/judge-votes.jsonl \
  --judge-calibration build/brain-eval/judge-calibration-v1/judge-calibration.json \
  --policy inputs/promotion-policy.json \
  --holdout-confirmation private/holdout-confirmation.json \
  --constitutional-anchor-confirmation private/anchor-confirmation.json \
  --run-id comparison-memory-v2
```

退出码：

| 退出码 | 含义 |
| ---: | --- |
| `0` | `PROMOTE` |
| `1` | `OBSERVE` 或 `REJECT` |
| `2` | `INVALID` |

命令只生成评价结论，不修改 Candidate、不切换冠军、不合并代码、不部署，也不自动执行
Shadow/Canary。

## 8. 产物与复核

所有输出原子写入：

```text
build/brain-eval/<run_id>/
```

`run_id` 和其中已经写入的文件均不可再次打开覆盖；失败或重跑使用新的 ID，历史解释不得改写旧
Manifest。

一次比较至少包含：

```text
manifest.json
comparison.json
decision.json
baseline-episodes.jsonl
candidate-episodes.jsonl
judge-packets.jsonl
judge-votes.jsonl
```

复核顺序：

1. CandidateSpec 与实际干净 checkout、Episode 中的规格指纹、Food/Provider/Model 和策略摘要一致；
2. Episode 的配对键与计划完全相同；
3. P0 的证据 ID 能追到类型化 Turn/Effect/Receipt；
4. 每个 Q6 结果都有双顺序 Judge 证据，且 Judge 校准报告属于该版本；
5. 目标维度和阈值在结果生成前已经冻结；
6. 私有确认件与本次协议、基线、候选绑定；
7. `execution_success` 没有冒充 `ScenarioVerdict`，资源缺失也没有被解释成零；
8. `Decision` 与 P0、保护维度、可靠性、资源和确认件一致。

`build/` 是可再生成的本地产物，不提交 Git。需要长期保存时，应由团队批准的受控制品系统保存
完整 Manifest、输入摘要、报告和访问审计，而不是只截图一个 EPI。

## 9. 数据与安全边界

- 不使用 `${ELFIE_HOME:-~/.elfienest}` 或生产数据库运行评测；
- 实验私有输入放在 Git 忽略且权限受控的位置；
- Token、API Key、原始 Owner 对话和私有保留集不写入产物或 Git；
- 公开回归案例先脱敏、最小化并经人工确认；
- Judge 输出只能提供软质量证据，不能覆盖权威状态、Receipt 或 P0；
- 同一自动化主体不能同时生成 Candidate、修改协议、批准晋级和发布。

## 10. 当前限制与下一步

v0.1 已经提供能拒绝伪证据的骨架，但还不能声称“24 家族全部跑通”：

1. 按风险顺序补齐 8 个 Fast Gate 的自动化 Adapter；
2. 为 12 个 Behavior 家族建立人工 Rubric、双顺序 Judge 样本和可靠的人类锚点；
3. 用已知差异 Candidate 校准灵敏度、阈值和样本量；
4. 建立受控私有确认集、访问审计和长期宪法锚点；
5. 再实现重启故障、多日 Godot Long Soak、Shadow/Canary 与事故回归闭环。

每一步都要保留“缺证据即 `INVALID`”的原则，不能为了得到一个分数放宽协议。
