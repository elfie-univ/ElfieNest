# Elfie Brain internal architecture contract

**Contract version:** 1.2
**Adopted:** 2026-08-12
**Scope:** `elfie/brain/` and the private cognitive coordination of one Elfie

> **Normative target.** This contract defines how one continuous Elfie admits
> events, maintains mental state, reasons, commits decisions and resumes work.
> The accepted Brain migration is complete; permanent architecture tests now
> enforce these boundaries directly.

The [Elfie internal architecture contract](./elfie) remains authoritative for
Profile, Brain, NervousSystem, Body, Communication and Genesis ownership. This
contract refines only the inside of Brain. It does not add a third external
line, another personality, or another system Runtime.

## Goals and non-goals

Brain must support a continuous autonomous embodied individual rather than a
request-scoped assistant. It owns current cognition, slowly changing mental
state, work that survives a Turn, and side-effect-free cognitive consolidation.
It shares one Selfhood and Memory across digital communication and embodied
life while keeping their Turns and output authority separate.

This contract fixes semantic owners, lifecycle boundaries and deterministic
guards. It does not fix prompts, model vendors, storage schemas, tunable numeric
coefficients or process topology. Emotion's six stored channels and signed
appraisal contract are intentional fixed semantics; their gains, half-lives and
presentation thresholds remain configurable. The ten systems are conceptual
owners, not a requirement for ten processes, databases or empty packages.

## Ten conceptual systems

| No. | System | Owns | Produces | Must not do |
| --- | --- | --- | --- | --- |
| 1 | Event Workspace | bounded Communication, Embodied and Internal lanes; admission, ordering, deduplication, backpressure, salience and single-domain framing | one immutable `TurnFrame` or an explicit defer/reject result | merge source domains into one Turn, reason about content, or execute actions |
| 2 | Orientation | sourced current body, place, time, nearby actors, conversation, activity, affordance and uncertainty | versioned `OrientationSnapshot` | copy world authority, store complete history, or define personality |
| 3 | Selfhood | mutable self-model, personality tendencies, norms and slow change evidence anchored by immutable Profile | versioned Selfhood/Personality/Norms snapshot and validated updates | rewrite Profile, accept one-message personality mutation, or enlarge capabilities |
| 4 | Emotion | process-local affect, appraisal, accumulation, decay and recovery | `EmotionSnapshot` and bounded influence on attention, recall and expression | create goals, messages or body actions, or persist its live stock |
| 5 | Energy | homeostasis, circadian state, cognitive/action budgets, emergency reserve and degradation mode | `EnergySnapshot`, reservations and cognitive-mode constraints | choose semantic goals or replace NervousSystem safety reflexes |
| 6 | Motivation | fixed drives, pressure, satisfaction, competition, saturation, cooldown and repetition suppression | `AttentionBias`, `GoalCandidate` or `InternalTriggerCandidate` | create an Activity or act externally |
| 7 | Memory | subjective episodes, working memory, knowledge, people, relationships, provenance, retrieval, consolidation and forgetting | bounded retrievals and validated memory commits | own current Orientation, Run state or Activity state |
| 8 | Reasoning Core | context assembly, bounded Model/Skill/Tool loop, observations, verification, inhibition, completion judgment and one `TurnDecision` | one settled decision plus internal state candidates | wait across Turns, claim execution success, or bypass deterministic policy |
| 9 | Persistent Activity | validated goals and work that survive the current Turn; steps, conditions, scheduling, pause/resume/cancel, retry, idempotency and receipts | preflight results, state events and bounded Internal triggers | become a second Brain or directly perform open-ended external actions |
| 10 | Cognitive Consolidation | interruptible sleep/idle review of memories, activities, emotion trajectories and outcomes under a no-external-side-effect scope | validated state candidates or a later Internal trigger | directly message, move, create Activity, expand permission or rewrite authoritative state |

Context assembly, Turn settlement, decision governance, routing, Journal,
Checkpoint and receipt reconciliation are mandatory mechanisms serving these
owners. They are not additional peer mental systems.

## Emotion state and appraisal

The detailed [Elfie Emotion system design](../designs/elfie-emotion-system) is
the accepted interpretation of this section. Its current quality gaps remain in
the [Emotion conformance register](../conformance/elfie-emotion).

1. Emotion owns Elfie's process-local affect, not an observed actor's affect.
   Another person's feeling is evidence only; changing Elfie requires a direct
   self-relevance appraisal or a host-resolved, relationship-weighted indirect
   appraisal.
2. The only stored version-1 stocks are `happiness`, `sadness`, `anger`, `fear`,
   `surprise` and `disgust`, each bounded to `[0, 1]`. Several may coexist.
   Primary, secondary, active labels and trends are derived projections; VAD,
   Episode lists and fixed interaction matrices are not parallel state owners.
3. Fast and model appraisal output is sparse signed semantic evidence bound to
   a host-trusted Scope. Omitted channels remain unchanged. A model returns
   direction, semantic strength and confidence, never a stock delta or final
   value; the deterministic Emotion owner calculates all numeric changes.
4. Same-direction evidence must combine without diluting a strong signal.
   Positive drive approaches saturation, negative drive consumes existing
   stock, and absent drive returns each stock exponentially toward its
   personality-derived baseline. Big Five may adjust bounded baselines, gains
   and half-lives, but cannot become a second state source.
5. Emotion applies every event admitted by Event Workspace. It does not
   deduplicate again. Repeated admitted observations can refresh a continuing
   state while saturation bounds growth.
6. One frame captures a pre-fast stable anchor. Fast appraisal may commit a
   provisional candidate, but the model receives only the pre-fast stable
   emotion projection plus host-trusted candidate Scopes. Valid structured slow
   feedback recomputes from the same anchor and atomically replaces the fast
   candidate; explicit empty feedback cancels that frame's fast effect, while
   missing, invalid or failed feedback leaves it in place.
7. Host framing must make eligible self-relevance candidate Scopes available to
   slow review independently of a fast lexical hit. A model cannot invent or
   widen a Scope. A bounded correction for one continuing causal identity may
   affect later observations of that exact cause, not unrelated events.
8. Live stocks, frame transactions and continuing-cause guidance are not
   durable. Sleep or process restart restores personality-derived baselines and
   clears transient guidance. Emotion owns no database, checkpoint or
   historical change-event ledger; a bounded recent source-ID projection is
   diagnostic provenance, not a second history.
9. Version 1 appraises social text, physical touch, execution outcomes and
   explicit internal/model evidence. Typed audio and image/vision transport may
   exist at perception boundaries, but their affect appraisal is deferred. A
   future detector must produce observation evidence through the same Scope
   boundary and must never mutate Emotion directly or manufacture a calm result.

## Conservation rules

1. Brain accepts exactly three event-source domains: `Communication`,
   `Embodied` and `Internal`.
   Delivery/command receipts and Activity state events re-enter as `Internal`
   events bound to their original causal identity; later facts observed in the
   world remain new `Embodied` events. Receipts never create a fourth domain.
2. One `TurnFrame` has exactly one `SourceDomain`, one `InteractionScope` and
   one bounded `ResponseScope`. Model output cannot widen either scope.
3. Communication and Embodied events that arrive together remain separate
   Turns. They may observe shared committed mental state but cannot share a
   frame, transient reasoning state or output authority.
4. A cross-domain consequence becomes a validated Persistent Activity request
   or a later Internal event and a new Turn. A Communication Turn cannot emit a
   NervousSystem directive in the current Turn.
5. Every Turn settles to exactly one `TurnDecision`. It may request at most one
   external execution domain: Communication or NervousSystem. A validated
   Persistent Activity request may accompany that decision; all may be absent
   for `No-op`.
6. Model, Skill, Tool, Worker and consolidation outputs are proposals or
   observations. They never prove that an external action happened and never
   write authoritative state directly.
7. All authoritative mental-state changes use candidate, validation and commit.
   Every commit identifies source, causal identity, version and idempotency.
8. Only typed external receipts prove message or body execution. Only Activity
   state events prove durable-work transitions.
9. Open decisions pass one deterministic, serialized commit boundary that
   enforces source/response/execution scope, capabilities, budget, privacy,
   deadlines, body generation and idempotency.
10. Fast deterministic safety reflexes stay in NervousSystem and do not wait for
    an open model Turn.

## Online Turn lifecycle

### Admission and framing

Producers publish semantic events, not raw device frames or platform payloads.
Event Workspace retains three logical lanes with bounded capacity and explicit
backpressure. It may deduplicate, coalesce state updates, habituate repeated
stimuli, prioritize safety and enforce fairness, but it must preserve source and
causal identity.

Admission creates an immutable single-domain `TurnFrame` with a stable Turn ID,
source domain, interaction scope, triggering events, cutoff, deadline and
response scope. A Communication scope binds channel, conversation and relevant
participants; different conversations remain different Turns. An Embodied scope
binds current Body ID/generation and one coherent situation window, while an
Internal scope binds one trigger or Activity causal chain. One frame may
therefore aggregate several compatible events without mixing independent
conversations, body generations or internal causes. Events outside the cutoff
remain available to later Turns. Failure to admit is an observable defer,
reject or backpressure result rather than silent loss.

### Context and reasoning

Reasoning Core assembles only the context needed by the admitted Turn. A context
snapshot records the versions and capture time of Profile anchors, Orientation,
Selfhood, Emotion, Energy, Motivation, Memory, Activity and effective
capabilities. Facts, inferences and unknown values remain distinguishable.

A `ReasoningRun` may contain multiple cognitive steps and multiple Model,
Skill, Tool and Observation cycles. It has an explicit budget, deadline,
cancellation state and completion condition. Tool observations return to the
same Run. A bounded Worker receives only a minimal context capsule and has no
independent identity, durable-state write authority or external action route.

The Run terminates with one structured `TurnDecision`, an explicit failure, or
a safe `No-op`. A timeout, unavailable model, rejected Tool call or exhausted
budget cannot be represented as successful completion.

### Decision, execution and settlement

The deterministic boundary validates the decision against the admitted Turn
and current state before committing any directive. The only action families are:

- `CommunicationDirective` for digital-message delivery;
- `NervousSystemDirective` for embodied speech, expression or motion;
- `PersistentActivityRequest` for validated work beyond the current Turn;
- `No-op` when no action is committed.

Internal memory, emotion, selfhood, orientation, energy or motivation candidates
are Turn-settlement material, not a fourth action family. Settlement submits
each candidate or receipt to its true owner, which validates current version and
causal identity before committing. A stale or duplicate result is rejected or
reconciled; it is never repaired by merely prompting a later model to assume the
desired state.

## Response scopes

- A Communication Turn may produce a Communication directive, a validated
  Persistent Activity request, or `No-op`; it cannot produce a NervousSystem
  directive. A direct reply remains inside the admitted channel/conversation;
  contacting another person or conversation requires a validated later scope.
- An Embodied Turn may produce a NervousSystem directive, a validated Persistent
  Activity request, or `No-op`; it cannot produce a digital-message directive.
- An Internal Turn may select at most one external domain allowed by its
  `ExecutionScope`, may create/update a validated Activity, or may choose
  `No-op`.
- A clarification uses the current source domain. Missing identity, contact,
  capability, time meaning or success criteria must be clarified during the
  originating Turn when possible, not postponed until an Activity is due.

## Persistent Activity lifecycle

Persistent Activity owns `Goal -> Activity -> ActivityStep -> ActivityRun`
semantics without owning a separate personality or reasoning engine. Before a
Turn can request a durable Activity, Reasoning Core may submit an inert
`ActivityDraft` for synchronous preflight. Preflight checks target identity,
contact path, capability, budget, time semantics, dependencies, success
criteria and execution scope, and returns `VALIDATED`, `NEEDS_CLARIFICATION` or
`REJECTED`. Preflight has no durable or external side effect.

Only a validated draft may be committed after the Turn settles. A due time,
condition, retry or receipt creates a typed Internal event; it never executes an
open action directly. Communication and embodied consequences are separate
Activity steps and separate Turns. Stable causal IDs, idempotency keys,
checkpoints and receipts prevent lost commitments and duplicate side effects
across interruption or restart.

Motivation and Cognitive Consolidation cannot create Activity directly. They
may only produce candidates that re-enter Event Workspace as an Internal Turn.
Motivation must not be enabled as an action source before Persistent Activity
has bounded creation, cancellation, cooldown and recovery behavior.

## Energy, long reasoning and interruption

Energy determines available cognitive modes and reserves resources; it does not
decide semantic content. At minimum the policy distinguishes normal work,
bounded long reasoning, degraded response and emergency reserve. Emergency
reserve preserves basic orientation, refusal, acknowledgement and help-seeking
but forbids long reasoning and optional background work.

A long `ReasoningRun` may yield or be interrupted. An urgent new event is a new
Turn, not additional content injected into the existing Run. A short
acknowledgement such as "I am busy" is likewise a separate Turn with its own
scope and budget. Multiple Runs may compute concurrently only if transient
state is isolated; their decisions still pass one serialized commit boundary.
Outputs based on stale state, expired deadlines or an obsolete body generation
must not commit.

## Cognitive tools and external peripherals

Brain Skills authorize semantic cognitive capabilities. `ToolPort` executes
only tools made available by the injected, Elfie-scoped runtime, such as bounded
search, retrieval, command execution, simple code and file work inside the
Elfie's authorized cognitive workspace. The runtime sandbox, command allowlist,
network policy, workspace root and quota are deterministic and require no
per-operation human approval inside that envelope.

Digital-message channels, Body control and device state are not Tools. They are
external peripherals reached only after a settled decision through
Communication or NervousSystem. A Tool cannot expose a hidden message, device or
body route, and its textual claim is never an execution receipt.

## State, persistence and recovery

`MemoryState`, `ReasoningRunState` and `ActivityState` are distinct. Durable
cognitive infrastructure provides an event journal, authoritative state store,
Run/Activity checkpoints, budget ledger, causal trace, idempotency records and
receipt reconciliation. These facilities hold state for the ten systems but do
not become an eleventh mind or decide behavior.

After restart, Brain restores durable owners, reconciles in-flight directives
and Activities, rejects stale body generations and resumes only work whose
scope and deadline remain valid. Emotion is the explicit exception: its live
stocks and transient guidance return to personality-derived baselines on sleep
or process restart. Missing model service delays or degrades open cognition; it
does not erase identity, memory, commitments or basic reflex capability.

## Dependency and package rules

Brain depends only on its own strongly typed consumer-owned Ports and Elfie
semantic contracts. It does not import App, Nest, concrete Infrastructure,
Provider SDKs, platform payloads, device transports, filesystem roots or
database records. AI Runtime implementations remain outside Brain; Brain owns
when and why they are called inside a Run.

The canonical package names are `workspace/`, `orientation/`,
`selfhood/`, `emotion/`, `energy/`, `motivation/`, `memory/`, `reasoning/`,
`activity/` and `consolidation/`. Every package owns real state, contracts or
behavior. Synonymous flat modules at the Brain root must not return, and empty
architecture-shaped directories are forbidden.

Private cognitive coordination and context assembly belong under Brain. The
root Elfie Facade may start, stop and observe the aggregate but must not become
the owner of Turn state, model loops or mental state. Product execution proceeds
only through separately approved vertical slices recorded in the conformance
register; this contract itself does not authorize source migration.
