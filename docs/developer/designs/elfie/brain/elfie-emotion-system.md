# Elfie Emotion system design

> Status: accepted version-1 design<br>
> Normative boundary: [Elfie Brain internal architecture contract](../../../contracts/brain)<br>
> Current gaps: [Elfie Emotion conformance](../../../conformance/elfie-emotion)

> Design relations: **Owner:** Elfie / Brain / Emotion; **Parent:** [Brain
> ten-system architecture](./elfie-brain-ten-system-architecture.md); **Children:**
> none; **Normative contracts:** [Brain contract](../../../contracts/brain.md);
> **Current architecture:** [Cognitive information flow](../../../architecture/cognitive-flow.md);
> **Conformance:** [Emotion conformance](../../../conformance/elfie-emotion.md);
> **Domain sources:** none.

## Purpose and boundary

Emotion models **Elfie's own short-lived affect**, not the feeling expressed by
the owner or another actor. An observed person's affect is evidence. It changes
Elfie only after a direct self-relevance or relationship-weighted empathic
appraisal. Emotion may bias attention, recall and expression, but it cannot
create goals, messages or body actions.

Version 1 intentionally uses six stored channels and no second state space:

`happiness`, `sadness`, `anger`, `fear`, `surprise`, `disgust`.

Each channel is an absolute stock in `[0, 1]`. Several channels may coexist.
Mixed affect is therefore preserved without an Episode list, VAD point or a
fixed one-label winner. Primary, secondary, active emotions and trends are
derived projections, never additional stored state.

## Input contract

Every admitted cause produces zero or more sparse `AffectiveAppraisal` values.
Each appraisal selects a host-trusted scope and contains only affected channels:

- `direct`: the event changes Elfie's own situation;
- `indirect`: another actor's state affects Elfie through a host-resolved,
  revision-bound relationship weight;
- each effect contains `channel`, `increase|decrease`, semantic strength
  `1..100` and confidence;
- omitted channels are unchanged; an empty appraisal set is preferred to a
  guess;
- models return semantic strength, never a numeric stock delta or final value.

One event may raise several channels and directly consume several others. This
is the only version-1 coupling mechanism. There is no hidden stock-to-stock
matrix such as fear automatically creating anger. Such a matrix would invent a
cause that the event appraisal did not provide.

## State update

The program, not the model, converts semantic strength through configured knots
and applies source, confidence and relationship weights. Same-direction
evidence in one event uses a noisy-or combination so a weak parallel signal
cannot dilute a strong one:

```text
P = 1 - product(1 - positive_i)
N = 1 - product(1 - negative_i)
drive = positive_gain * P - negative_gain * N
```

Positive drive approaches saturation; negative drive consumes the current
stock directly:

```text
drive > 0: x' = 1 - (1 - x) * exp(-drive * dose)
drive < 0: x' = x * exp(drive * dose)
```

Equal calibrated drives cancel. Repeated admitted observations remain
meaningful: they refresh or strengthen the stock but approach `1` instead of
growing without bound. Emotion performs no second event deduplication; Event
Workspace owns admission, coalescing and deduplication.

With no new signed effect, every channel returns exponentially to its own
personality-derived baseline:

```text
x(t + dt) = baseline + (x(t) - baseline) * 2^(-dt / half_life)
```

The half-life creates immediate but progressively smaller recovery. Continued
stimuli can refresh the stock, and a decrease effect can consume it faster than
passive recovery. Surprise uses a short half-life; longer-lived channels use
larger values. Exact gains, half-lives, thresholds, source weights and strength
knots remain versioned runtime configuration rather than architecture constants.

## Personality

Big Five traits deterministically and modestly adjust each channel's baseline,
positive gain, negative gain and half-life within hard bounds. The baseline is
an absolute visible stock and the passive-return target; it is not subtracted
away when deriving the current state. Personality is a temperament prior, not a
second emotion source.

## One Turn: stable, fast and reviewed

For every admitted frame, Coordinator runs one frame-scoped in-memory emotion
transaction:

1. advance passive recovery and capture the pre-fast stable anchor;
2. run the deterministic fast appraiser and commit its provisional candidate;
3. send the model the **pre-fast stable emotion description**, the current
   event and host-trusted candidate scopes, never the provisional fast stock;
4. accept only structured sparse model appraisals bound to supplied scope IDs;
5. recompute the reviewed candidate from the same pre-fast anchor and replace
   the provisional candidate atomically.

A valid explicit empty appraisal removes the provisional fast effect for that
frame. Missing, invalid or failed model feedback leaves the fast result in
place. A correction retained for a continuing causal identity may be reapplied
to later admitted observations of that same cause, so the fast reaction is not
recreated unopposed every Turn. Frame replay reuses the same transaction rather
than applying the fast effect twice.

The slow model must be offered host-trusted candidate scopes independently of
whether the fast lexical appraiser recognized an effect; otherwise a fast miss
cannot be reviewed. The remaining implementation gap is recorded as `EMO-002`.

## Projection to reasoning and expression

`EmotionSnapshot` always carries all six absolute values. Its natural-language
projection is sparse:

- only channels above their activation threshold are candidates;
- primary is the strongest active channel;
- secondary and further active channels appear only when they are sufficiently
  strong relative to the primary, up to the configured cap;
- trends appear only above a configured change threshold.

This avoids fixed-count noise while preserving both absolute strength and mixed
affect. Expression mapping may consume the complete snapshot for future
embodied presentation; it does not own emotion state.

## Lifetime, provenance and modalities

Live stocks, transient continuing-cause guidance and frame transactions are
process-local. Sleep and process restart reset all channels to
personality-derived baselines and clear guidance. Emotion owns no database,
checkpoint or historical change-event ledger. A snapshot may retain only a
small bounded list of recent source event identities for in-process provenance;
Memory may separately retain completed experiences and their historical tone.

Version 1 appraises social text, physical touch, execution outcomes and explicit
internal/model appraisals. Typed audio and image/vision transport remains
available at the perception boundary, but audio/image affect appraisal is not
implemented in this version. No unused detector placeholder is kept. A future
detector must emit typed observation evidence into the same appraisal boundary;
it must not mutate live stocks directly, equate an observed actor's feeling
with Elfie's feeling, or manufacture a `calm` result when detection is absent.

## Verification

Deterministic tests cover six-channel completeness, signed updates, saturation,
passive recovery, personality bounds, repeated admitted events, stable/fast/
reviewed replacement, structured scope validation, process reset and prompt
projection. Semantic appraisal quality is a separate statistical gate using
fresh independent blind sets. Known quality and scope-coverage gaps remain open
in the conformance register and cannot be closed by deterministic tests alone.
