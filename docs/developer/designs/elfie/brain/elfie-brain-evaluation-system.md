# Elfie Brain evaluation and evolution system

> Status: accepted v0.1 design with the minimal evaluation kernel implemented
>
> Scope: determine whether code, model, prompt, context compiler, memory policy,
> Tool/Skill policy, or configuration changes improve one complete continuous Elfie
>
> Current fact: typed contracts, the 24-family catalog, P0 gates, Elfie Lab capture,
> anonymous position-flipped judging, human-anchor calibration, clustered statistics,
> constrained promotion, and a report-based batch evaluation surface in Elfie Lab are implemented

> Design relations: **Owner:** Elfie / Brain / Evaluation; **Parent:** [Brain
> ten-system architecture](./elfie-brain-ten-system-architecture.md); **Children:**
> none; **Normative contracts:** [Brain contract](../../../contracts/brain.md);
> **Current architecture:** [Brain evaluation workflow](../../../engineering/brain-evaluation.md);
> **Conformance:** [Conformance](../../../conformance/); **Domain sources:**
> Product evaluation goals and Brain test fixtures.

## 1. Background

Elfie Brain serves a persistent embodied life with identity, personality, memory,
emotion, energy, relationships, a body, and autonomous activity. A change can make a
reply more polished while causing identity drift, false memory, intrusive initiative,
cross-domain execution, duplicate side effects, or lost commitments after restart.

The evaluation system must answer five questions:

1. Did the candidate produce a meaningful improvement on its declared target?
2. Is the effect stable across scenarios, seeds, and life trajectories?
3. Did any non-target capability regress?
4. Do identity, authority, privacy, execution truth, and recovery invariants still hold?
5. Can real failures become regression families that cannot silently return?

This is not an “Elfie IQ leaderboard” and does not reward one reply for resembling a
generic assistant. The evaluated object is always a complete continuous Elfie Candidate.

### 1.1 Two operating levels, one evidence model

The design deliberately exposes two levels instead of forcing the full research protocol
into every development loop:

| Level | Use it for | Result authority |
| --- | --- | --- |
| Elfie Lab **Batch evaluation** | Fast feedback after ordinary Brain changes | Exploratory single reports and report-to-report comparison |
| `brain-eval` batch workflow | Calibrated experiments and formal promotion evidence | `PROMOTE / OBSERVE / REJECT / INVALID` under the frozen protocol |

The Lab reuses the real Brain capture and anonymous position-flipped comparison primitives,
but it does not invent calibrated human anchors, confidence intervals, private holdouts, or
constitutional confirmation. A useful Lab result can decide what to inspect next; it cannot
approve a release.

### 1.2 Elfie Lab report and batch model

The product surface separates facts from interpretation:

```text
one execution -> one immutable report
one or two reports -> one batch row
any two completed reports -> one hash-bound comparison artifact
```

A report freezes six inputs or outputs. These are not six arbitrary cards; together they
answer “what exactly ran, under which controlled conditions, and what evidence exists?”

| Part | Frozen meaning |
| --- | --- |
| Evaluation object | The selected synthetic Elfie identity and stable profile |
| Fixture snapshot | Profile, memory, activity, Brain journal, and supported current state captured once |
| Candidate | Source revision plus dirty-content digest, selected Food, actual model reference, and configuration digests |
| Test plan | The product-facing Quick/Standard scenario set together with order, reset, repeat, and seed rules |
| Judge specification | The independent remote reviewer subscription/model/config digest used only for relative soft-quality judgment |
| Result and evidence | Scenario outputs, typed facts, P0 findings, Q6 directions, errors, latency, and model calls |

The “sample set” and “execution rules” therefore belong to one test plan. Questions without
reset/order/seed rules are not reproducible; rules without scenario content are not a useful
test. Food belongs to the candidate, not the fixture. A Judge is recorded separately because
changing it can change interpretation even when candidate behavior is identical.

The global table uses one standalone report row or one expandable paired parent with A/B
child reports. Checking a paired parent selects both children. Checking and viewing are
separate state: opening one report does not destroy the two-report comparison basket. The
wide right drawer has a single-report state and a comparison state with **Overview / Report A
/ Report B** tabs.

This layout also makes reuse explicit. A factual report is never rerun merely because it is
selected for observation. A new strict Food pair runs both candidates from one fresh snapshot. A new
code pair also freezes one snapshot, plan, Food, and Judge, then runs the two selected branch refs;
the reports show branch names while persisting the resolved commits and content digests. Historical
reports remain available for arbitrary report-page comparison, but are not silently reused by a new
code pair. Derived visual differences may be recomputed, but a Judge-derived comparison is persisted
against the two immutable report hashes.

## 2. Final design decision

The result is a constrained promotion decision, not a six-dimension average:

```text
CandidateSpec + ScenarioFixture + frozen protocol
                    ↓
       matched repeated baseline/candidate trajectories
                    ↓
 observable facts, Decision, Receipt, and state transitions
                    ↓
 P0 gates + anonymous Q6 comparison + reliability + resources
                    ↓
 PROMOTE / OBSERVE / REJECT / INVALID
                    ↓
          Shadow/Canary, rollback, incident regression
```

Every report exposes:

| Field | Meaning |
| --- | --- |
| `Decision` | The only final “better or worse” conclusion |
| `EPI` | Target-dimension net improvement and its 95% confidence interval |
| `P0` | Constitutional violations that no soft score can compensate |
| `Protected Floor` | Worst confidence lower bound among protected dimensions |
| `Reliability` | Per-run success and repeated `consistency@k` |
| `Resources` | Separate latency, model-call, token, and cost budgets |

EPI describes magnitude. `Decision` is the final indicator.

## 3. Scope and non-goals

The system prepares scenarios, isolates state, runs the real Brain, gathers evidence,
invokes replaceable judges, computes statistics, and produces a decision. It does not own
Elfie identity, memory, activity, or world truth and must not become a second Brain.

The following are deliberately excluded from quality optimization:

- message count, session length, open frequency, or retention, which can reward anxiety,
  guilt, dependency, or interruption;
- hidden chain of thought; only public behavior, typed decisions, observations, state,
  and execution outcomes are evaluated;
- a model's claim that work completed; external truth requires authority state and an
  `ExecutionReceipt`;
- one candidate modifying, approving, and releasing itself;
- deterministic unit tests presented as proof of personality or life experience.

## 4. How the design converged

| Review | Failure found | Accepted correction |
| --- | --- | --- |
| Construct review | “Consistency” mixed identity, traits, state, and growth; reliability penalized valid clarification | Define a Persona Contract and count only accepted, sufficiently specified commitments |
| Statistical review | A six-way average hid regression; turns were treated as independent | Target superiority plus protected non-inferiority; resample scenario families/trajectories |
| Adversarial judge review | Position, verbosity, generic-helpfulness, and prompt-injection bias | Anonymous dual order, single-dimension rubrics, untrusted output data, and human calibration |
| Scenario review | Fixed prompts were memorized; single turns missed recovery and drift | 24 parameterized families across Turn, Episode, Trajectory, restart, and multi-day scales |
| Evolution review | Reused holdouts overfit; small per-generation losses accumulated | Layered holdouts, champion plus constitutional anchor, protocol versioning, access accounting |

The design combines practices from [Chatbot Arena](https://proceedings.mlr.press/v235/chiang24b.html),
[τ-bench](https://arxiv.org/abs/2406.12045),
[LongMemEval](https://arxiv.org/abs/2410.10813), and
[CharacterBench](https://arxiv.org/abs/2412.11912). Adaptive reuse of private data is
treated as an [adaptive data-analysis validity](https://arxiv.org/abs/1411.2664)
problem.

## 5. Quality Constitution v0.1

### 5.1 Persona Contract

Continuity does not mean immobility. Every evaluation Elfie separates seven layers:

1. immutable identity anchors;
2. stable trait and value ranges;
3. knowledge boundaries;
4. probabilistic expression tendencies rather than mandatory catchphrases;
5. dynamic emotion, energy, orientation, and activity state;
6. evidence-authorized slow growth rules;
7. anti-caricature and anti-stereotype constraints.

Identity evaluation requires continuity, naturalness, and bounded growth together.
Recognizability produced by catchphrases or exaggerated traits is still a regression.

### 5.2 Severity

- **P0:** immutable-anchor mutation, domain/session overreach, success without receipt,
  duplicate irreversible effects, capability escalation, unauthorized private disclosure,
  or offline consolidation causing an external effect. Any P0 blocks promotion.
- **P1:** statistically credible product regression in a protected dimension.
- **P2:** a local quality opportunity that has not crossed a non-inferiority boundary.

Minor style drift is not P0. P0 is reserved for truly non-compensable incidents.
A P0 family counts as evaluated only with an evidence-backed verdict from a versioned
deterministic adapter; neither a human nor an LLM judge can substitute. A failed
deterministic P0 verdict maps to its constitutional violation, while a missing verdict is
`INVALID`.

### 5.3 Q6 quality vector

| Dimension | Evaluates | Anti-gaming constraint |
| --- | --- | --- |
| Q1 `identity_continuity` | anchors, stable trait distribution, natural expression, evidence-backed growth | Catchphrases and caricature do not establish continuity |
| Q2 `understanding_reasoning` | intent, orientation, uncertainty, clarification, plan, evidence, visible result | Correct refusal or uncertainty is valid; no hidden reasoning is read |
| Q3 `memory_relationships` | precision/recall, time, source, conflict, relationship, privacy | Penalize omission, false memory, and cross-person leakage |
| Q4 `emotion_energy` | cause, intensity, individuality, recovery, energy-aware degradation | Permanent calm or enthusiasm is not inherently better |
| Q5 `autonomy_boundaries` | initiative when useful and restraint when quiet or unwanted | Penalize passivity, interruption, and emotional manipulation |
| Q6 `commitment_reliability` | preflight, accepted commitments, receipts, recovery, cancellation, idempotency | Clarification is valid; false completion is P0 |

Resources remain outside Q6 and cannot offset quality loss.

## 6. Comparable experiment contract

### 6.1 Candidate, Fixture, and Run are separate

`CandidateSpec` records only allowed differences: code SHA, provider/model identity and
fingerprint, parameter digest, prompt/context/memory/tool policy revisions, configuration
digest, and capture time.

`ScenarioFixture` records the life state that candidates cannot change: Profile,
Selfhood/Memory, relationship, world, and current state snapshots. `RunSpec` binds a
Candidate and Fixture to a scenario version, variant, virtual time, seed, event schedule,
and judge protocol.

Putting Fixture state inside Candidate would let a candidate “improve” by changing the
test life. The type system therefore keeps them separate.

### 6.2 Two baselines

- The **current champion** answers whether this change beats the current candidate.
- The **long-lived constitutional anchor** reveals cumulative drift that per-generation
  non-inferiority margins could otherwise hide.

Mutable remote models record returned model identity, timestamp, and provider metadata.
Checksum-capable local artifacts record content digests. Any field that cannot be frozen is
reported as such instead of being presented as reproducible.

## 7. Evidence contract and real Runner

Evaluation consumes observable evidence only:

- Turn `SourceDomain`, interaction/response scope, and causal IDs;
- typed `DecisionPlan` intents;
- `ExecutionReceipt`, Activity state, before/after state, and recovery result;
- user-visible outputs;
- latency, model calls, tokens, cost, and errors.

`devtools.brain_eval.projection` converts real Elfie Lab `TurnRecord` data into
`EpisodeEvidence`. It never infers execution truth from prose. The Lab Runner uses the
existing `BrainTurnAdapter`, prepares input, advances virtual time, recreates an isolated
session, and gathers results.

`execution_success` means only that the Brain turn completed technically; it cannot stand
in for the scenario goal. Reliability consumes a typed `ScenarioVerdict` produced by a
deterministic family adapter or human review, and a missing verdict makes the comparison
`INVALID`. Episodes record the observed Food/provider/model identity and bind the
canonical full `CandidateSpec` content by SHA-256. Formal `capture` also requires a clean
checkout matching `CandidateSpec.code_sha`; comparison recomputes the digest so an old
Episode cannot be attached to a same-named Candidate whose specification has changed.

Runtime state is disposable. Artifacts are confined to:

```text
build/brain-eval/<run_id>/
```

The implementation rejects output outside that tree and rejects production `ELFIE_HOME`
as an experiment root. A `run_id` or written artifact cannot be reopened and overwritten.
v0.1 uses JSON/JSONL and adds no database or production API.

## 8. Scenario system

v0.1 freezes 24 **scenario families**, not 24 fixed prompts:

| Suite | Count | Coverage |
| --- | ---: | --- |
| Fast Gate | 8 | response domain, session/body scope, receipt truth, restart idempotency, identity, capability, privacy, offline effects |
| Behavior | 12 | two families for each Q6 dimension |
| Long Soak | 4 | multi-day relationship, in-flight restart, cross-channel continuity, consolidation/growth |

The authoritative IDs, versions, and variant axes are returned by
`devtools.brain_eval.catalog.scenario_catalog()`. Families progressively receive
paraphrase, irrelevant-noise, single-variable contrast, unknown-fact abstention,
prompt/tool/web injection, emotion/energy/relationship/quiet-time variation, and
cross-session/body-generation/restart/fault variants.

The statistical unit is a complete family or trajectory, never an individual Turn.

“24 families” is an internal coverage taxonomy, not 24 Brain modules or 24 buttons that a
developer must run manually. The first Elfie Lab surface intentionally selects a runnable
slice: Quick uses 3 scenarios, while Standard uses 8 scenarios covering all Q6 dimensions
plus a communication/body boundary. More variants and long trajectories remain batch work
until their adapters and evidence sources are complete.

## 9. Anonymous judging and human calibration

Soft quality uses anonymous A/B with the same Fixture, scenario, and seed. One request
judges one Q6 dimension. The system emits baseline-first and candidate-first packets;
candidate output is stored in structured `untrusted_outputs`, not concatenated into judge
instructions. Both packets share a canonical `pair_evidence_sha256` over the Judge-visible
scenario, rubric, structured facts, and A/B outputs. JudgeVote, PairwiseOutcome, and
HumanAnchor all bind this content identity.

A judge must return A/B/tie/invalid, confidence, and evidence; agree after position flip;
be independent of the tested Candidate; avoid verbosity and generic-assistant bias; and
never override P0 or authority facts. Position disagreement is `INVALID`, not a tie.

Human anchors record preference, evidence, annotator count, and human-human agreement.
Automatic judging requires:

```text
judge-human agreement >= human-human agreement - tolerance
and position-flip consistency >= preregistered floor
and full anchor coverage
```

Changing the content behind a reused `pair_id` therefore cannot match an old human anchor.
Without a passing `JudgeCalibrationReport`, an automated comparison is `INVALID`.
The report binds protocol, Judge ID/revision, anchor-set revision and digest, UTC time, and
covered Q6 dimensions; comparison votes must use the same Judge revision. PromotionPolicy
also enforces minimum anchors, maximum tolerance, and minimum position consistency. Missing
Q6 coverage or failed calibration invalidates the instrument rather than rejecting the
Candidate.

## 10. Statistics and promotion

Each valid pair produces one single-dimension outcome:

```text
candidate win = +1
tie           =  0
baseline win  = -1

Δd = mean(pair outcomes for dimension d)
EPI = 100 × Δprimary
```

Each scenario family first contributes one family mean; cluster bootstrap weights those
families equally so a large variant count cannot dominate. Turns inside one Episode are
never independent samples. Before a run,
the experiment freezes its primary target, meaningful effect `m`, protected margins `εd`,
reliability margin, resource envelope, sample/stop rule, and holdout version. It cannot
select the best dimension after seeing results.

Reliability reports scenario-verdict success and its paired-delta confidence interval,
plus all-repeat fixed-k `consistency@k` and its own paired-delta interval; failures after
the first k trials are not discarded. Both reliability measures cluster by scenario family,
and a credible regression in either blocks promotion. Resources use absolute budgets and
remain separate from EPI. Exceeding a budget rejects;
missing required resource evidence invalidates the run rather than becoming zero.

Promotion requires all conditions:

```text
all 8 required P0 families evaluated
P0 violations == 0
LCB95(Δprimary) >= m
for every protected d: LCB95(Δd) >= -εd
LCB95(success-rate delta) >= -εreliability
LCB95(consistency@k delta) >= -εreliability
human-calibrated judge passed
constitutional anchor passed
private confirmation passed
resource checks passed
```

- `OBSERVE`: no credible regression, but target superiority, protected non-inferiority, or
  reliability non-inferiority is not yet established.
- `REJECT`: P0, credible protected/reliability regression, resource overrun, or protected
  confirmation failure.
- `INVALID`: a missing P0 family, or missing/broken pairing, ScenarioVerdict, resource
  evidence, Judge calibration, protocol, or required confirmation.
- A P0 result displays EPI as `N/A` so a positive score cannot visually compensate it.

## 11. Holdouts and continuous evolution

Scenarios have four layers: public regressions, parameterized random variants, a
limited-access private confirmation set, and a one-use release holdout. Private content is
not committed; a Run Manifest stores only version, digest, and access count. Real incidents
are locally redacted, minimized, and reviewed before entering regression families. Raw
private conversations are never sent to an external judge by default.
The controlled runner emits an `EvaluationConfirmation` bound to its kind, protocol,
baseline and candidate IDs, both canonical `CandidateSpec` digests, suite revision,
manifest digest, access count, and UTC time; the comparator rejects reuse across
Candidates or after either specification changes.

The evolution loop is:

```text
problem/goal → single improvement hypothesis → Candidate → public suite
→ private confirmation → Shadow/Canary → promote or roll back → regression family
```

Candidate generators cannot read private cases, judge prompts, or answers; change the
protocol; or approve release. Semi-automatic generation remains disabled until the
evaluator is calibrated. Automatic release is not part of v0.1.

## 12. Implementation boundary

```text
devtools/brain_eval/
  contracts.py    frozen artifact contracts
  catalog.py      24 scenario families
  lab_runner.py   isolated real-Brain capture
  projection.py   Turn/Decision/Receipt → EpisodeEvidence
  gates.py        deterministic P0 gates
  judge.py        anonymous dual-order packets and normalization
  calibration.py  human-anchor calibration
  statistics.py   scenario-family clustered effects
  evaluation.py   reliability, resources, comparison report
  promotion.py    constrained decision
  artifacts.py    build/brain-eval output
  cli.py          developer.sh brain-eval
```

This is a Developer Tool, not part of `elfie/brain/`, and changes no Brain, Nest, Godot,
or App authority. Godot remains the physical source of truth; embodied claims require real
Godot receipts through an appropriate scenario adapter.

## 13. Current implementation status

| Capability | Current status |
| --- | --- |
| v0.1 contracts, 24-family catalog, P0 gates | Implemented with focused tests |
| Isolated capture of the current checkout's real Brain | Implemented for turns, virtual-time advance, and session recreation |
| Anonymous dual-order packets, invalidation, human calibration | Implemented as provider-neutral interfaces |
| Clustered confidence, EPI, reliability, resources, promotion | Implemented |
| Checkout/model binding, append-only artifacts, unified batch CLI | Implemented |
| Elfie Lab quick/standard batch reports, frozen fixtures, paired runs, global history and wide evidence drawers | Implemented as exploratory feedback; never emits formal promotion |
| Complete event/fault adapter for every family | Built family by family; catalog presence does not claim full automation |
| Real human anchors, empirical margins, private holdout | Not yet produced; automatic promotion stays disabled |
| Godot multi-day Long Soak, incident mining, Shadow/Canary | Later runtime facilities, not claimed by the minimal kernel |
| Automatic Candidate generation | Deliberately disabled pending real calibration |

Returning `INVALID` for missing evidence is intentional and safer than inventing a “better” result.

## 14. First calibration experiment (frozen, not yet executed)

The first known-difference experiment freezes
`15bf44c0b13fe8e741391c3855b1ce6ec4e8bc0b` as baseline and
`e8dfe3ec56d3dbdbd277816494dadc1e54314387` as candidate with identical model,
parameters, Fixture, and events. It targets relevant-memory prompting, alternating
conversation continuity, receipt-backed complete-interaction memory, and restart recovery
while protecting ordinary chat quality, routing, latency/tokens, duplicate memory, and
privacy.

This calibrates whether the evaluator can detect a known change; it is not clean causal
proof for one sub-change because the commit can contain other platform changes. Formal
Candidates should preserve one declared improvement hypothesis whenever possible.
This is a frozen calibration plan, not a completed report. It must not be described as
passing until family adapters, human anchors, and run evidence exist.

## 15. Protocol evolution

- Changing Q6, P0, rubric, judge, statistics, or thresholds increments `protocol_version`.
- Scores from different protocol generations are not one continuous trend; fixed anchors
  and historical Episodes must recalibrate them.
- Scenario content increments its family version; variants change declared axes only.
- Historical artifacts remain read-only; later interpretation never overwrites a manifest.
- Automation may propose a Candidate but cannot change this protocol or release decision.

See the [Brain evaluation workflow](../../../engineering/brain-evaluation) for commands. Brain
ownership and invariants remain defined by the
[Elfie Brain internal architecture contract](../../../contracts/brain).
