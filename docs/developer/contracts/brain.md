# Elfie Brain internal architecture contract

**Contract version:** 1.4
**Adopted:** 2026-08-12
**Revised:** 2026-08-31
**Scope:** `elfie/brain/` and the private cognitive coordination of one Elfie

> **Normative target.** This contract defines how one continuous Elfie admits
> events, maintains mental state, reasons, commits decisions and resumes work.
> Earlier Brain migrations remain protected by permanent architecture tests.
> The accepted Selfhood/fixed-header gaps remain tracked in the scoped
> [Selfhood conformance register](../conformance/elfie-selfhood). The completed
> Reasoning Context Workspace P0 boundary is protected by permanent focused tests.

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
guards. It additionally fixes the four-block prefix and source ownership of
online Elfie model prompts, but not their release-owned copy, model vendors,
storage encodings, tunable numeric coefficients or process topology. Emotion's six stored channels and signed
appraisal contract are intentional fixed semantics; their gains, half-lives and
presentation thresholds remain configurable. The ten systems are conceptual
owners, not a requirement for ten processes, databases or empty packages.

## Ten conceptual systems

| No. | System | Owns | Produces | Must not do |
| --- | --- | --- | --- | --- |
| 1 | Event Workspace | bounded Communication, Embodied and Internal lanes; admission, ordering, deduplication, backpressure, salience and single-domain framing | one immutable `TurnFrame` or an explicit defer/reject result | merge source domains into one Turn, reason about content, or execute actions |
| 2 | Orientation | sourced current body, place, time, nearby actors, conversation, activity, affordance and uncertainty | versioned `OrientationSnapshot` | copy world authority, store complete history, or define personality |
| 3 | Selfhood | one atomic state containing creation-frozen `identity_core` and slow `adaptive_self`; deterministic typed/model projections | versioned Selfhood snapshot, two model-header blocks and, only after a later design, validated Memory-evidenced updates | read Profile/Canon at runtime, accept direct Turn/model/state updates, persist final prompt text, or enlarge capabilities |
| 4 | Emotion | process-local affect, appraisal, accumulation, decay and recovery | `EmotionSnapshot` and bounded influence on attention, recall and expression | create goals, messages or body actions, or persist its live stock |
| 5 | Energy | homeostasis, circadian state, cognitive/action budgets, emergency reserve and degradation mode | `EnergySnapshot`, reservations and cognitive-mode constraints | choose semantic goals or replace NervousSystem safety reflexes |
| 6 | Motivation | fixed drives, pressure, satisfaction, competition, saturation, cooldown and repetition suppression | `AttentionBias`, `GoalCandidate` or `InternalTriggerCandidate` | create an Activity or act externally |
| 7 | Memory | durable subjective episodes, knowledge, people, relationships, provenance, retrieval, consolidation and forgetting | bounded retrievals and validated durable memory commits | own transient conversation/context state, current Orientation, Run state or Activity state |
| 8 | Reasoning Core | `Reasoning Context Workspace`, context assembly, bounded Model/Skill/Tool loop, observations, verification, inhibition, completion judgment and one `TurnDecision` | one settled decision plus internal state candidates | wait across Turns, let another system own its transient context, claim execution success, or bypass deterministic policy |
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

## Selfhood and the fixed online model header

The detailed
[Selfhood and fixed model-header design](../designs/elfie-selfhood-and-fixed-model-header)
is the accepted interpretation of this section. Current implementation gaps
remain in the
[Selfhood conformance register](../conformance/elfie-selfhood).

### Selfhood authority and state

1. Selfhood owns one atomic, strongly typed state with one schema version, one
   Selfhood revision and exactly two semantic layers. `identity_core` contains
   the minimum per-Elfie identity facts frozen at creation. `adaptive_self`
   contains bounded personality traits, personal value/norm identifiers and
   interaction, coping and expression tendencies.
2. The state must not contain a Profile revision, Canon version/path/reference,
   final prompt paragraph, free-form model-authored autobiography, detailed
   world knowledge, biography, relationship state, current Emotion/Energy/
   Orientation/Activity, capabilities, permissions or application-wide rules.
3. `identity_core` is immutable after Genesis. Phase 1 exposes no assembled
   `adaptive_self` mutation route. A later approved growth design may accept
   only a typed Memory-consolidation proposal carrying a base Selfhood revision,
   stable proposal/idempotency identity and durable Memory evidence. Memory owns
   the proposal and evidence. Consolidation may schedule its derivation and a
   model may be an untrusted helper inside that bounded Memory process, but
   neither addresses Selfhood directly. Only Selfhood validates and commits,
   and no proposal may modify `identity_core`.
4. Selfhood may expose an immutable typed snapshot or narrower trait projection
   to contracted Brain owners. Reasoning receives only a deterministic,
   bounded, side-effect-free `SelfhoodPromptProjection` with
   `identity_core_text`, `adaptive_self_text` and non-prompt revision metadata.
   The projection is not persisted, reads no Profile, Canon or Memory, invokes
   no model, emits no raw Big Five values or internal IDs, and cannot invent
   biography, relationships, knowledge, current state, permissions or actions.
5. User-controlled names and every bounded text slot are encoded as data.
   Control characters, reserved fixed-header labels and delimiter-breaking
   sequences are rejected or escaped before projection. Arbitrary adoption
   story, Memory content and model text cannot enter a fixed block.

### Genesis and runtime inputs

6. Genesis is the only Selfhood initializer. It may consume accepted adoption
   input, creation-time Canon/species facts and reviewed deterministic mappings,
   then co-materializes Profile, complete Selfhood and Genesis Memory as sibling
   outputs of one validated creation bundle. Selfhood does not derive from a
   persisted Profile at ordinary startup, and partial/inconsistent creation
   fails admission.
7. Profile remains the external immutable dossier. Canon remains a creation-time
   world/species input and a source for Genesis Memory. Ordinary Brain runtime,
   Reasoning context assembly and Selfhood projection must not read, accept,
   refresh or synchronize Profile or Canon. Existing Elfies are not bound to a
   Canon version; later Canon changes do not alter their Selfhood.
8. Missing, invalid, unsupported or unrenderable Selfhood fails Brain/resident
   cognition before `ModelPort` invocation and produces a safe diagnostic. It
   must not fall back to `Elfie`, a generic persona, all-0.5 traits, Profile,
   Canon, Memory self narrative or a model-generated repair.

### Four-block fixed prefix

9. Every model request inside an online Elfie `ReasoningRun` starts with exactly
   one fixed prefix in this order:

   ```text
   [APPLICATION_FRAME]
   {application_frame_text}

   [IDENTITY_CORE]
   {identity_core_text}

   [ADAPTIVE_SELF]
   {adaptive_self_text}

   [OPERATING_CONTRACT]
   {operating_contract_text}
   ```

   Reasoning owns the labels, order and request assembly. Selfhood owns and
   renders blocks 2 and 3. One required, human-authored, same-release,
   bundled-only `ReasoningConstitution` owns blocks 1 and 4; Infrastructure only
   validates/loads it and Bootstrap injects it. Users, Genesis, Canon, models,
   Providers and per-Elfie data cannot generate, override, hot-reload or branch
   that constitution.
10. `APPLICATION_FRAME` contains only the minimum shared ElfieNest application
    and story premise. `OPERATING_CONTRACT` contains stable identity,
    epistemic, context-trust, execution-truth and scope rules. Detailed Canon,
    individual facts and Turn-varying schema/capability instructions do not
    belong in either block.
11. Trusted `TURN_PROTOCOL` and current Brain state follow the fixed prefix.
    Retrieved Memory, Activities, observations, conversation history and the
    current message remain context data after it. They cannot become a fifth
    fixed block or replace any fixed source.
12. The canonical envelope uses LF line endings, no text before its first
    label, exactly one blank line between sections, and exactly one blank line
    before the following `[TURN_PROTOCOL]`. Validated block content has no
    leading/trailing blank lines and cannot contain a reserved header label.
13. Initial generation, Tool-observation continuation and structured-output
    repair inside one online Run preserve the exact fixed-prefix bytes and bound
    source revisions. Genesis, Memory consolidation, Provider probes,
    evaluation judges and identity-less background Workers must not receive this
    Elfie header. All online system instructions, including Skill/Tool
    instructions, are assembled by Reasoning after the fixed prefix as
    `TURN_PROTOCOL`. Provider/model Adapters and generic prompt injectors must
    not add system instructions or change request message order/content.
14. The fixed prefix is reserved before dynamic context trimming. Its byte cap
    and the complete provider context-window budget are validated before
    invocation. A fixed block cannot be dropped, truncated or reordered to fit;
    an invalid request fails explicitly.
15. `OPERATING_CONTRACT` is model guidance, not a security authority.
    Deterministic host capability, response/execution scope, privacy, budget,
    serialized commit and receipt guards remain mandatory and take precedence
    over a conflicting personal norm or model response.

### Persistence and conflict rules

16. In phase 1 the per-Elfie Selfhood document is the sole durable Selfhood
    authority. Generic Brain continuity checkpoints must not contain or restore
    Selfhood. Future adaptive mutation cannot be enabled before one dedicated
    atomic, revision-checked and idempotent durable commit boundary exists.
17. Memory must not persist or inject a second authoritative identity,
    relationship, world and tendency self narrative. Identity conflicts resolve
    to `identity_core`; recalled Memory remains fallible evidence. Current
    Emotion/Orientation may temporarily modulate expression but cannot rewrite
    `adaptive_self`. A Profile/Selfhood conflict during creation fails creation;
    ordinary runtime cannot reread Profile to repair it.
18. An application upgrade may replace the same-release Constitution for all
    Elfies. It does not alter `identity_core`, bind Selfhood to new Canon or
    silently rewrite existing `adaptive_self` data.

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

The detailed
[Reasoning Core single-Turn Agent design](../designs/elfie-reasoning-core) is
the accepted interpretation of this section. Its completed P0 owner-chat
boundary is protected by focused architecture, context, memory, runtime,
receipt and restart tests.

Event Workspace and Reasoning Context Workspace are distinct. Event Workspace
owns event lanes, admission and immutable single-domain framing. The
Reasoning-internal Context Workspace owns bounded recent alternating dialogue,
active-topic state, source-linked context summaries, current-Run observations,
pending Memory handoffs and its own bounded recovery checkpoint. It is not a
peer mental system, and Memory owns no transient conversation tail, context
summary, Run scratch state or generic context buffer.

Reasoning Core assembles only the context needed by the admitted Turn. A context
snapshot records the Constitution and Selfhood revisions and the versions and
capture time of Orientation, Emotion, Energy, Motivation, Memory, Activity and
effective capabilities. These owner projections are read-only and remain
frozen during the Run. The snapshot contains no Profile or Canon runtime
projection. Facts, inferences and unknown values remain distinguishable.

Every Turn may perform baseline Memory Recall. A cognitive step may request an
additional bounded Recall through a Reasoning-owned Memory Bridge when required
to resolve a person, reference, conflict or missing fact. All Recall results
used by one Run bind to one explicit Memory revision unless the complete Run
context is rebased; mixed revisions are invalid. Reasoning owns query intent,
timing and context placement. Memory owns retrieval semantics, provenance,
conflict handling, validation and durable commit. A model never reads or writes
Memory directly.

Before every model call, Reasoning rebuilds one provider-neutral model context
from the frozen snapshots and current Context Workspace. It reserves response
headroom and retains the current Frame, trusted Scope, unresolved items and
complete Action/Observation pairs before trimming less relevant material.
Prompt-pressure compaction creates a source-linked `ContextSummary` owned by
Reasoning. Durable capture is a separate handoff of complete sourced
`ClosedEpisode` records and typed candidates to Memory; a lossy summary is not
a durable fact. A pending handoff is removed only after a Memory receipt.

`DIRECT` and `DELIBERATE` are Reasoning depth choices derived from upstream
hints, task complexity/risk, Energy, deadline and available model capability.
They do not change Memory availability or hard permissions. Food selects the
requested model role and fallback route; it does not define cognitive modes or
carry a separate allow-list of modes. Skill, Tool and Worker remain independent
stage-gated capabilities.

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

Internal Memory, Emotion, Orientation, Energy or Motivation candidates are
Turn-settlement material, not a fourth action family. Selfhood is deliberately
absent: phase 1 has no update route, and a future update can enter only as the
Memory-owned consolidation proposal defined above, never as ordinary Turn
output. Settlement submits each admitted candidate or receipt to its true
owner, which validates current version and causal identity before committing. A
stale or duplicate result is rejected or reconciled; it is never repaired by
merely prompting a later model to assume the desired state.

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

`MemoryState`, `SelfhoodState`, `ReasoningContextWorkspaceState`,
`ReasoningRunState` and `ActivityState` are distinct. A bounded Reasoning
Context Workspace checkpoint supports crash recovery but is not durable
Memory. Durable cognitive infrastructure provides owner-appropriate state, an
event journal, Run/Activity checkpoints, budget ledger, causal trace,
idempotency records and receipt reconciliation. It does not imply one universal
checkpoint for every mental owner and does not become an eleventh mind.

After restart, Brain loads durable owners from their single authorities,
reconciles in-flight directives
and Activities, rejects stale body generations and resumes only work whose
scope and deadline remain valid. Emotion is the explicit exception: its live
stocks and transient guidance return to personality-derived baselines on sleep
or process restart. Missing model service delays or degrades open cognition; it
does not erase identity, memory, commitments or basic reflex capability.

## Dependency and package rules

Brain depends only on its own strongly typed consumer-owned Ports and Elfie
semantic contracts. Ordinary Brain runtime also does not depend on Profile or
Canon. It does not import App, Nest, concrete Infrastructure,
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
