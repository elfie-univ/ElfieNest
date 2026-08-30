# Elfie Emotion conformance

> State: open quality and correction-coverage debt<br>
> Baseline: 2026-08-30, branch candidate `1cc4962d`<br>
> Target: [Elfie Emotion system design](../designs/elfie-emotion-system)

This temporary register records known gaps against the accepted Emotion design.
It does not weaken the six-channel contract or treat low false-positive rates as
evidence of useful recall.

## Open register

| ID | Severity | Status | Current deviation | Target and closure gate | Evidence / references | Residuals |
| --- | --- | --- | --- | --- | --- | --- |
| EMO-001 | P1 | open | The fresh independent 120-case blind set found high abstention but poor self-impact coverage: 16/85 positive cases emitted any effect, 10/85 hit any expected channel, and expected-effect recall was 9.9%. Direct cases hit 1/36, contrast 0/9, mixed 1/10 and trusted empathy 8/18. The 35/35 empty cases abstained; forbidden-channel and opposite-direction rates were 1.67% and 0.83%. | Continue in the next Emotion-quality iteration with a newly generated independent hidden set after every tuning round. Close only when expected-effect recall is at least 70%, direct positive-case any-hit is at least 70%, empty-case abstention is at least 90%, and severe forbidden/opposite errors stay below 20%. Reused tuning cases do not count. | target=design §Input contract and §Verification; inventory=`elfie/brain/emotion/appraiser.py`, `detector/text_detector.py`; references=independent blind-set run on candidate `1cc4962d`; verification=120 cases, 85 positive and 35 explicit-empty; residuals=the current conservative rules are safe but not useful enough. | No optimization is included in this cleanup; this row remains the next-round quality backlog. |
| EMO-002 | P1 | open | A direct appraisal Scope is currently added only when the fast lexical appraiser already emits a direct effect. A fast miss can therefore leave the slow model with no legal direct Scope and prevent the reviewed layer from correcting that miss. | Host framing must offer a bounded direct candidate Scope for every eligible self-relevant event independently of a fast hit, while indirect Scope remains relationship-bound. Close with tests showing an unseen praise/threat can be reviewed, another actor's reported affect is not copied, and unknown/invented Scope IDs are rejected. | target=design §One Turn; inventory=`elfie/brain/emotion/appraiser.py`, `elfie/brain/reasoning/coordinator.py`, `context_source.py`; references=structured `EmotionFeedback` Scope validation; verification=focused unseen-cue and owner-reported-affect scenarios plus a fresh independent slow-layer set; residuals=until fixed, structured feedback is safe but cannot cover every fast miss. | Deferred with EMO-001 to the next Emotion-quality iteration. |

The current deterministic state machine remains valid while these rows are
open. The register is not closure-ready.
