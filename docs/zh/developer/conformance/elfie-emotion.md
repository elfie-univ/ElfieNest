# Elfie 情绪一致性

> 状态：效果质量和慢层纠正覆盖仍有开放债务<br>
> 基线：2026-08-30，分支候选 `1cc4962d`<br>
> 目标：[Elfie 情绪系统设计](../designs/elfie/brain/elfie-emotion-system)

这是相对于已接受 Emotion 设计的临时差距台账。它不能削弱六通道契约，也不能用低误报
掩盖召回不足。

## 开放台账

| ID | 严重度 | 状态 | 当前差距 | 目标与关闭门槛 | 证据 / 参考 | 残余 |
| --- | --- | --- | --- | --- | --- | --- |
| EMO-001 | P1 | open | 全新独立的 120 条盲测显示系统很保守，但自我影响覆盖很差：85 条正例只输出 16 条，10/85 命中任一预期通道，预期 Effect 召回率为 9.9%；direct 为 1/36、contrast 为 0/9、mixed 为 1/10、trusted empathy 为 8/18。35/35 空例正确保持空；禁止通道和反方向错误率分别为 1.67% 与 0.83%。 | 下一轮 Emotion 质量优化继续处理；每轮调参后必须重新生成独立隐藏集。只有预期 Effect 召回率不低于 70%、direct 正例任一命中率不低于 70%、空例 Abstention 不低于 90%、严重禁止/反向错误低于 20% 才可关闭；参与调参的旧样本不能作为关闭证据。 | target=设计“输入契约”和“验证”；inventory=`elfie/brain/emotion/appraiser.py`、`detector/text_detector.py`；references=候选 `1cc4962d` 的独立盲测；verification=120 条，其中 85 条正例、35 条显式空例；residuals=当前规则较安全，但可用性不足。 | 本次清理不做算法优化；保留为下一轮质量 Backlog。 |
| EMO-002 | P1 | open | 当前只有快速词法评价已产生 direct Effect 时，才会加入 direct Appraisal Scope。快速漏检可能让慢模型没有合法 direct Scope，因此无法纠正这次漏检。 | 宿主成帧必须独立于快速命中，为每个合资格的自我相关事件提供有界 direct 候选 Scope；indirect Scope 仍必须绑定关系。关闭证据必须证明未见过的表扬/威胁可被慢层复核、不会复制他人的自述情绪、未知或伪造 Scope ID 会被拒绝。 | target=设计“一个 Turn”；inventory=`elfie/brain/emotion/appraiser.py`、`elfie/brain/reasoning/coordinator.py`、`context_source.py`；references=结构化 `EmotionFeedback` Scope 校验；verification=聚焦未见 Cue、主人自述情绪场景和全新慢层独立集；residuals=修复前结构化反馈虽安全，但不能覆盖所有快速漏检。 | 与 EMO-001 一起延后到下一轮 Emotion 质量优化。 |

这两条开放期间，当前确定性状态机仍然有效，但台账尚未准备收口。
