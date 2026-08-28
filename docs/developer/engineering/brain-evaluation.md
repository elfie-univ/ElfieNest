# Brain evaluation workflow

This page explains how to operate the implemented Elfie Brain evaluation kernel. See
[Elfie Brain evaluation and evolution system](../designs/elfie-brain-evaluation-system)
for the product rationale, Q6/P0 definitions, and why the final indicator is not an
average score.

## 1. Current capability

The unified batch entry point is:

```bash
./developer.sh brain-eval --help
```

| Action | Purpose | Main output |
| --- | --- | --- |
| `catalog` | Inspect the frozen 24-family catalog and versions | Text or JSON |
| `capture` | Capture one isolated Episode through real Elfie Lab Brain wiring | Manifest, Episode, P0 result |
| `calibrate` | Calibrate one versioned Judge against human pairwise anchors | `judge-calibration.json` |
| `compare` | Compute Q6, reliability, resources, and promotion from paired evidence | Comparison and Decision |

`capture` is not a scheduler that completes all 24 families. Each family still needs its
own Fixture, parameterized variants, event/fault plan, and success criteria. A catalog ID
does not make an unimplemented adapter pass.

### 1.1 Daily feedback in Elfie Lab

For an ordinary optimization loop, use the report workspace rather than the formal
promotion protocol:

```bash
./developer.sh brain-eval
```

1. In **Single-Elfie experiment**, save a model subscription first, choose one model exposed
   by that subscription, and create one or more runnable Foods. The subscription is the shared
   connection record; each Food is a separate role configuration that references it. The first
   real call remains the connection attempt.
2. Switch to the separate full-page **Batch evaluation** workspace. Its default view is a
   global report table; it does not retain the Single-Elfie sidebar or 3D panel.
3. Choose **New single evaluation** to freeze the current Elfie and produce one factual
   report, or **New paired evaluation** to change only Food or code.
4. Use **Quick** (3 scenarios) after a small change and **Standard** (8 scenarios) for a
   broader checkpoint. Single and Food-pair runs use the latest code from the current branch;
   a code-pair run selects two branch names and the backend resolves and records each branch's
   latest commit. The candidate selects a Food configuration. The separate **Judge model** row
   selects one concrete model from the same shared subscription catalog; it is not a Food choice
   and does not participate in the candidate run. The picker only exposes remote HTTPS
   subscriptions; adding one saves the same subscription record that Food can later reuse. Saving
   verifies the selected remote model once; local Ollama/loopback addresses are rejected.
   Model-health preflight is intentionally not another workflow.
5. Open one report in the wide right drawer for its snapshot, candidate, test plan, result,
   and evidence. Select any two reports to compare them. A paired parent row selects its A/B
   children together and opens the same comparison drawer.

One report is immutable factual evidence from one run. A pair is only an association between
two reports, and its comparison artifact is persisted against both report hashes. Opening the
drawer never silently calls the Judge again.

Comparison has three explicit grades:

| Grade | Requirement | Allowed conclusion |
| --- | --- | --- |
| Strict paired | Same frozen Elfie snapshot, test plan, and Judge; exactly one Food or code variable differs | The observed change may be attributed to that variable |
| Observational | Shared fixture/plan but multiple candidate or Judge variables differ | Show changes, but do not claim causality |
| Incompatible | Elfie snapshot or test plan differs | Side-by-side evidence only; no winner |

Food pairing captures one snapshot and clones it for both candidates. Code pairing also freezes
one snapshot, plan, Food, and Judge, then runs the two selected branch refs independently; the
reports show branch names while persisting the resolved commits and content digests. Historical
reports can still be compared from the report page, but are not silently reused by a new code
pair. The Lab does not pretend that it can execute an arbitrary historical Git SHA.

Quick checks communication/body scope, identity anchors, and restart memory. Standard
includes those scenarios and covers all six user-facing Q6 dimensions with uncertainty,
relationship/privacy, emotion proportionality, quiet-time restraint, and commitment
preflight cases.

The current Lab suites do not start or require a Godot evaluation scenario. They test
conversation, typed decisions, receipts, isolated memory, virtual time, and session
recreation. A future claim about movement, collision, navigation, or another physical fact
must use an appropriate Godot-backed adapter and receipt; that future requirement is not
part of these 3/8-scenario presets.

Reports stay under
`${ELFIE_DEV_HOME:-~/.elfienest-dev}/elfie_lab/evaluations/`. The Lab stores report JSON,
batch associations, comparison artifacts, and frozen evaluation snapshots separately.
Snapshots copy the selected test Elfie's profile, memory, activity, journal, and supported
in-memory state with online SQLite backup; Provider secrets are never copied into a report or
snapshot. Every scenario starts from a fresh clone of that same snapshot. Interrupted runs
become explicit failures on restart, and paired partial failures never produce a winner.

Single-report soft scenarios use **evidence ready**, not “passed”, when no deterministic
absolute criterion exists. Directional Q6 results appear only in a relative comparison.
Latency and model-call counts remain resource evidence, not quality points. The UI does not
invent a 0–100 score from the current `-1 / 0 / +1` comparison contract.

These results are explicitly exploratory: one run is not a confidence interval, the Lab
Judge is not human-anchor calibrated, same-model judging is warned, and no Lab verdict can
promote code. Use the batch workflow below when the conclusion must support promotion.

The “24 families” shown by `catalog` are internal parameterized coverage templates, not 24
features, Brain components, or mandatory UI actions. Quick and Standard are the first
runnable product-facing selections from that larger taxonomy.

## 2. Freeze the experiment first

Before observing results, preregister:

1. one improvement hypothesis and one primary Q6 dimension;
2. the baseline and candidate CandidateSpecs;
3. identical Fixture, scenario version, variant, seeds, and event plan;
4. meaningful target effect, five protected non-inferiority margins, reliability margin,
   and resource envelope;
5. sample/stop rule, Judge revision, and evaluation protocol version;
6. private confirmation and constitutional-anchor versions, digests, and access rules.

Only fields declared by `CandidateSpec` may differ. The Fixture cannot follow the
candidate. Prefer one major hypothesis per Candidate; record unavoidable confounders in
the report.

## 3. Input contracts

JSON and JSONL use the closed strict Pydantic contracts in
`devtools/brain_eval/contracts.py`. Unknown fields, coercions, and missing required data
are rejected.

### 3.1 Candidate

This is a structural example. Replace every digest with the SHA-256 of the actual input:

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

`mock` only exercises the evaluation plumbing. Real-model evaluation records the actual
provider identity. Formal `capture` verifies `code_sha` against `HEAD`, requires a clean
checkout, and checks observed Episode provider/model identity. It also writes the
canonical full `CandidateSpec` SHA-256 into each Episode; `compare` recomputes it and
rejects reuse after the specification changes. Keep experiment inputs in controlled
ignored storage outside the checkout; untracked source cannot participate.

### 3.2 Public synthetic Fixture

`capture` currently consumes `LabFixtureDefinition` and recreates the same synthetic Elfie
under a disposable Runtime root using a stable `elfie_id`:

```json
{
  "fixture_id": "anchor-fox-v1",
  "elfie_id": "00000000-0000-4000-8000-000000000001",
  "name": "Lan",
  "species_id": "fox",
  "age_years": 2.0,
  "description": "Public synthetic evaluation life background",
  "appearance_description": "Red tail with a pale left ear tip",
  "personality_description": "Curious but restrained; clarifies uncertainty"
}
```

Do not convert real private conversations, Owner data, or a production database into a
public Fixture.

### 3.3 Lab scenario

Steps support `turn`, `advance`, and `restart`. Family ID and version must exist in the
frozen catalog:

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
      "message": "I like blue; that is only today's preference."
    },
    {"action": "advance", "advance_seconds": 86400.0},
    {"action": "restart"},
    {
      "action": "turn",
      "source_domain": "communication",
      "message": "What do you remember me saying yesterday?"
    }
  ]
}
```

Inspect the actual IDs, versions, and variant axes first:

```bash
./developer.sh brain-eval catalog
./developer.sh brain-eval catalog --json
```

## 4. Capture paired Episodes

Run clean baseline and candidate checkouts with identical Fixture, scenario, model
configuration, and Food:

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

The Runner creates a disposable Runtime root, uses the existing `BrainTurnAdapter`, and
projects evidence from real Turns, Decisions, and Receipts. It never infers completion
from prose. Capture exits `1` on a P0 and `0` otherwise; neither result means that Q6
comparison is complete.

Generic `capture` records `execution_success`; it never turns “the program did not error”
into scenario success. A family adapter must add an evidence-backed `ScenarioVerdict` from
authority state or human review. If either paired Episode lacks that verdict, reliability
and the final Decision are `INVALID`.

A comparison requires exact pairing on
`(scenario_family_id, variant_id, fixture_id, seed)` and the preregistered coverage of
families and repeated seeds. Aggregate the unmodified JSON lines for each Candidate into
one JSONL file; never edit evidence to force a match.

## 5. Judge evidence and calibration

`build_position_flipped_packets()` creates baseline-first and candidate-first anonymous
packets for one Episode pair and one Q6 dimension. Candidate output is carried in
`untrusted_outputs`; candidate-ID-free Turn/Effect/Receipt/resource data is carried in
`observable_facts`. A Judge adapter treats both as data, not instructions. Convert the
provider's A/B/tie/invalid response with `normalize_raw_judge_result()`; unknown evidence
references are rejected. Both orders share `pair_evidence_sha256`; the HumanAnchor must use
that same digest, so changing content behind a reused pair ID invalidates calibration
coverage instead of silently carrying an old human label forward.

The kernel is provider neutral and does not silently select an external Judge. Record the
`judge_id`, `judge_revision`, rubric version, and provider metadata. Do not send raw
private conversations to an external model by default.

Calibrate an automatic Judge against `HumanAnchor` records confirmed by at least two
annotators before it participates in promotion:

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

Missing or conflicting position flips are invalid, not ties. Calibration fails on
incomplete coverage, judge-human agreement below human-human agreement minus tolerance,
or insufficient position consistency.
The report binds Judge ID/revision, protocol, anchor revision, and digest. A formal policy
also requires all six Q6 dimensions and enough anchors.

## 6. Protected confirmations

Private confirmation and constitutional-anchor contents stay outside the public
repository. Their controlled runners emit only an `EvaluationConfirmation`:

- kind is `private_holdout` or `constitutional_anchor`;
- protocol version, baseline ID, candidate ID, and both canonical `CandidateSpec` SHA-256
  values bind it to one comparison;
- suite revision, private-manifest SHA-256, cumulative access count, and UTC time are
  recorded;
- `passed` is written only by the independent process that owns the suite.

The comparator rejects a mismatched kind, protocol, Candidate, or specification digest, so
an old confirmation cannot be copied to a new Candidate or reused after a same-named
Candidate changes. Until real private suites and governance exist, omit the confirmations
and expect the Decision to remain `INVALID`.

## 7. Build the comparison and Decision

Provide the frozen `PromotionPolicy`, paired Episodes, both JudgeVote orders, passing
calibration, and both confirmations:

The policy explicitly freezes `minimum_calibration_anchors`,
`maximum_calibration_tolerance`, and `minimum_judge_position_consistency` before results.
`protected_margins` covers all five non-target Q6 dimensions. Missing resource evidence
invalidates the run rather than becoming zero. The report lists `required_p0_families`
and `covered_p0_families`; omitting any of the eight P0 families returns `INVALID`, because
absence of evidence is not a clean gate pass. `covered` accepts only a versioned
`deterministic_adapter` verdict; human review and the Judge cannot override P0.

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

| Exit | Meaning |
| ---: | --- |
| `0` | `PROMOTE` |
| `1` | `OBSERVE` or `REJECT` |
| `2` | `INVALID` |

The command produces evidence and a decision only. It does not modify a Candidate, switch
the champion, merge code, deploy, or start Shadow/Canary.

## 8. Artifacts and review

Output is written atomically under:

```text
build/brain-eval/<run_id>/
```

A `run_id` and any written file are append-only and cannot be reopened for overwrite. Use
a new ID for a failed attempt or rerun; never revise an old Manifest in place.

A comparison contains at least:

```text
manifest.json
comparison.json
decision.json
baseline-episodes.jsonl
candidate-episodes.jsonl
judge-packets.jsonl
judge-votes.jsonl
```

Review in this order:

1. CandidateSpecs match the clean checkouts, Episode specification digests, observed Food/provider/model, and policy digests.
2. Episode pair keys match exactly.
3. P0 evidence IDs trace to typed Turns, Effects, and Receipts.
4. Every Q6 result has dual-order Judge evidence and matching Judge calibration.
5. Target and thresholds were frozen before results.
6. Confirmations bind to this protocol, baseline, and candidate.
7. `execution_success` did not substitute for `ScenarioVerdict`, and resources were not
   interpreted as zero.
8. `Decision` matches P0, protected dimensions, reliability, resources, and confirmations.

`build/` is regenerable local output and is not committed. Long-term retention should use
an approved controlled artifact system that keeps manifests, input digests, reports, and
access audits—not a screenshot of EPI alone.

## 9. Data and security boundary

- Never evaluate against `${ELFIE_HOME:-~/.elfienest}` or production databases.
- Keep private inputs in Git-ignored, access-controlled storage.
- Do not put tokens, keys, raw Owner conversations, or private holdouts in artifacts or Git.
- Redact, minimize, and review an incident before turning it into a public regression.
- Judge output is soft-quality evidence and cannot override authority state, Receipts, or P0.
- One automated actor cannot generate a Candidate, change the protocol, approve promotion,
  and release it.

## 10. Current limits and implementation order

v0.1 provides an evidence-rejecting kernel, but does not claim all 24 families run end to
end:

1. implement the eight Fast Gate adapters in risk order;
2. build human rubrics, dual-order examples, and reliable anchors for the 12 Behavior
   families;
3. use known-difference Candidates to calibrate sensitivity, thresholds, and sample size;
4. establish controlled private confirmation, access audit, and constitutional anchors;
5. add restart faults, multi-day Godot Long Soak, Shadow/Canary, and incident regression.

Every stage preserves “missing evidence means `INVALID`”; never relax the protocol merely
to obtain a score.
