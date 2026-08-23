# Repository architecture governance contract

**Contract version:** 1.18
**Adopted:** 2026-08-12
**Revised:** 2026-08-23
**Enforced scope:** Repository-wide change classification and architecture boundaries

This contract defines how ElfieNest architecture rules are organized, changed
and enforced. Exact baselines and conformance registers exist only while a
registered architecture gap remains. Rule sets that have reached zero debt are
enforced directly by permanent deny-all scanners and tests; active child
conformance may still record semantic or structural gaps not represented by a
retired general baseline.

## Four document classes

| Directory | Meaning | Lifecycle |
| --- | --- | --- |
| `architecture/` | Descriptive maps of the current system | Kept current; not normative |
| `contracts/` | Versioned ownership, dependency and boundary rules | Long-lived; changed deliberately |
| `conformance/` | Exact temporary gaps and migration gates | Deleted when gaps and baseline reach zero |
| `decisions/` | Accepted Architecture Decision Records | Retained as decision history |

English and Simplified-Chinese mirrors change together. Discussion notes,
unfinished proposals and implementation checklists do not become contracts.

## Quality governance stack

Architecture quality is maintained by one connected system:

| Mechanism | Purpose | Lifecycle |
| --- | --- | --- |
| Contracts | Define long-term ownership, dependency and authority | Permanent |
| ADRs | Explain deliberate contract changes and rejected alternatives | Permanent |
| Root/child `AGENTS.md` | Turn contracts into local execution guidance for coding agents | Permanent while the boundary exists |
| Scanners, type/lint checks and architecture tests | Enforce machine-checkable rules | Permanent |
| Exact legacy baselines | Ratchet known implementation debt without authorizing new debt | Temporary |
| Conformance registers | Name each temporary gap and its deletion gate | Temporary |
| CI base-branch comparison and maintainer review | Prevent a change from weakening the rule that judges itself | Permanent |
| Runtime health and Observer projections | Report operational health; separate from source architecture checks | Permanent |
| Exact-candidate affected CI and post-submit backstop | Merge quickly on relevant evidence while preserving broad asynchronous detection | Permanent |

No one mechanism replaces another. Contracts state the target, `AGENTS.md`
guides execution, machine gates reject detectable violations, conformance and
baselines record only legacy debt, and human review covers semantic rules that
cannot be proven mechanically.

## Repository script control plane

Repository scripts use one explicit stability and ownership model:

| Surface | Responsibility | Stability |
| --- | --- | --- |
| Stable files directly under `scripts/` | High-level Bootstrap, runtime, local-quality and release entry points | Exact command or import path is preserved deliberately |
| `scripts/governance/` | Contract registry, change policy, structural/dependency boundaries and persistence guards | First-class machine governance; never product implementation |
| `scripts/quality/` | Individual checks, validation planning/execution/evidence reuse and managed Git hooks | First-class machine governance; a gate cannot approve its own change |
| `scripts/internal/` | Replaceable Bootstrap, build, release and diagnostic helpers | No external path-compatibility promise; repository-owned callers may update atomically |

`internal` is a compatibility boundary, not access control. Repository-owned
CI, tests and stable entry points may call an internal helper directly, but
external instructions must prefer the supported high-level entry. Product
Bootstrap must not retain a runtime dependency on a convenience module under
`scripts/` when the concrete technical adapter has an Infrastructure owner.

The former flat `scripts/architecture/` tree and root-level leaf checks are not
valid target locations. During the one-time immutable-base cutover, the
candidate workflow may read legacy scanner files only from the exact base
commit that judges the candidate. The candidate tree itself contains only the
new layout; no root compatibility wrappers or duplicate implementations are
retained. Legacy base lookup is removed once a new-layout base is protected on
main.

## Exact-candidate submission and asynchronous full validation

Delivery separates merge-blocking evidence from broad regression detection:

| Phase | Trigger | Required result |
| --- | --- | --- |
| Local development | behavior change before staging | focused tests/type checks selected from actual risk |
| Local commit | real staged snapshot | staged diff, pinned Gitleaks and staged Python Ruff; warm target at or below 20 seconds |
| Feature push | candidate preparation | immediate branch push after the commit hook; no mandatory second local integration stage or pre-push test gate |
| Pull Request head | exact candidate SHA `H` | immutable-base manifest, security-fast and every selected parallel lane, aggregated internally as `elfienest/ci-gate` and exposed through required `elfienest/merge-gate` |
| Merge queue | synthetic merge of current main `M` and `H` | the same required `elfienest/merge-gate` name, now performing only lightweight identity, parent, conflict and gate-version checks |
| Main push | accepted merge result | non-blocking all-surface parallel backstop and aggregate |
| Manual/release | explicitly selected exact SHA | all-surface full graph plus release-specific acceptance |

The Pull Request preflight must execute the classifier from the immutable base
commit, not the candidate copy. Its versioned manifest selects
`security_fast`, Python bundles, Python quality, web frontend, Desktop,
Developer Tools web, architecture, persistence, Godot, docs, toolchain,
release, runtime smoke and governance
capabilities. Security-fast always runs. Unknown executable paths select all
lanes. A change to the classifier, CI workflow, governance contract or delivery
tooling cannot approve itself: it selects all lanes, remains subject to the
base-commit governance checker and requires maintainer review.

`elfienest/ci-gate` uses `always()` semantics and succeeds only when the trusted
preflight passed and every selected lane succeeded. A skipped, missing,
cancelled or timed-out selected lane is a failure. Unselected lanes may skip.
Evidence is bound to the exact PR head SHA; a newer commit creates a new
candidate. Movement of main alone does not invalidate `H` or restart its
affected tests. Only an actual conflict or a new candidate SHA requires new PR
evidence.

GitHub required status checks do not vary by event type. Therefore branch
protection requires only the stable `elfienest/merge-gate` job. On a Pull
Request event it succeeds only after `elfienest/ci-gate`; on a `merge_group`
event the same job name executes the lightweight synthetic-merge checks below.
This prevents either event from waiting forever for a check name emitted only
by the other event.

The merge queue must initially build one Pull Request per synthetic merge group.
The `merge_group` workflow is intentionally seconds-long: it does not install
dependencies or rerun Python, frontend, Godot or documentation suites. GitHub
serializes only the final main mutation; candidate validation remains parallel.
The required merge check must observe the exact synthetic merge SHA and reject
the wrong base, wrong queue ref, malformed parents, conflict residue or an
unknown gate schema.

The complete backstop is not a prerequisite for an ordinary merge. It runs
after each main push, on explicit full dispatches and before releases by
selecting every existing lane, not by serially repeating a local submission
script. Each main lane uses two non-cancelling parity concurrency slots; each
slot retains its running check and coalesces obsolete pending tips. A full
aggregate fails if any all-surface lane is missing, skipped, cancelled or red.
Superseded PR heads cancel. This prevents a steady stream of contributors from
holding main while retaining broad regression discovery.

Successful deterministic local checks remain reusable by exact check identity
as decided in ADR-0023. A cache key covers rule version, command, declared input
content and modes, toolchain and any immutable base used for selection. Narrow
nodes do not prove larger bundles; failures, timeouts, blocked environments and
live-provider observations never become passes. Local cache evidence never
replaces GitHub checks attached to the exact candidate SHA.

The delivery SLO is Pull Request push-to-main p95 at or below ten minutes under
available GitHub and runner capacity: local finalize plus push at or below one
minute, PR validation at or below seven minutes, and queue plus merge/ref
verification at or below two minutes. `elfienest/merge-gate` targets thirty
seconds inside that queue budget. CI records elapsed candidate and full-graph
timing in the job summary and warns when candidate validation exceeds 420
seconds. Platform outage, exhausted runner capacity and GitHub unavailability
are reported separately and cannot be turned into a false pass. Meeting the SLO
requires enough runner capacity for selected lanes to start in parallel; source
configuration alone cannot claim that external capacity exists.
Heavy lanes read the repository variable `ELFIENEST_HEAVY_RUNNER` as a runner
label and fall back to `ubuntu-latest` when it is unset. Setting that variable
is valid only after a multi-runner pool with the label is live; a label pointing
to one serialized worker does not satisfy the capacity requirement.

A terminal red full backstop on the newest main tip quarantines ordinary merges
until a newer main full backstop is green. A narrowly identified fix or revert
may use the audited `main-recovery` path. One exact failing check may be rerun;
the system must not repeatedly restart the entire graph or guess a revert when
the culprit is ambiguous. A newer green main result supersedes older red
ancestors.

Cutover is two-phase. Repository code and shadow checks land first while the
legacy full gate remains available. The faster submission instructions become
authoritative only after the live GitHub ruleset requires Pull Requests, merge
queue and the event-stable `elfienest/merge-gate`, blocks direct/force pushes
and has demonstrated zero missed affected lanes. Rollback returns the ruleset
to evaluation while retaining the full backstop; it never weakens tests or
fabricates evidence.

An architecture dependency is defined by the effective target, not only by an
`import` statement. A repository module reached through `python -m`, a script
path, a subprocess or Node child-process command, a shell command, `importlib`,
`runpy` or another dynamic loader is subject to the same ownership and allowed-
direction matrix as a static import. The effective-dependency scanner applies
this rule to repository-owned Python, Node, Godot and shell execution surfaces,
including newly introduced source roots. It classifies both caller and target
by module ownership rather than blacklisting a current offender. Targets that
cannot be statically resolved require a typed Port or Bootstrap-owned launch
plan and human review.

## Implementation evidence and delivery claims

An approved design or contract is the fixed target for implementation. Evidence
belongs in the relevant Conformance register, change description, test result or
runtime artifact; none of these becomes a second architectural authority.

Tests, builds, a clean worktree and a successful commit prove only their own
checks. They do not substitute for real startup, shutdown, crash, concurrency,
installation, cross-platform, stress or Provider checks required by the target.
If the current environment cannot perform a required check, the handoff keeps
that check explicitly blocked, names the missing environment and records the
next evidence step. The final handoff reports completed, retained and blocked
items separately and includes commands or scenarios that reproduce the claims.
External-environment gaps remain open until CI or a matching host supplies the
required evidence; there is no local flag that turns them into completion.

## End-to-end governance workflow

Every architecture-sensitive change follows one visible loop:

1. read the nearest `AGENTS.md`, the governing contract and the current
   conformance row before changing code;
2. classify the work as a governance change or a product/migration change;
3. for governance, revise the ADR/contract/local guidance and machine rule
   without implementation-side files; for migration, keep the target fixed and select one
   complete capability or business-domain slice;
4. run the candidate scanner against its exact baseline and the affected local
   checks; do not start the full repository merely because submission began;
5. in CI, route from the immutable base manifest, require the event-stable
   `elfienest/merge-gate` backed by `elfienest/ci-gate` on the candidate,
   require maintainer review for governance, then run the complete backstop
   asynchronously on the accepted main tip;
6. after a migration proves its real call chain, remove the old implementation,
   reduce only the matching baseline entries and close only the evidenced
   conformance row;
7. when the last gap in a rule set reaches zero, mark the evidenced register
   closure-ready and immediately complete the separate zero-debt governance
   workflow below; never leave an all-closed register or empty baseline as a
   steady state.

The machine-readable registry at
`scripts/governance/contract_registry.py` links each contract version to its
language mirrors, ADR, local guidance, scanners, architecture tests,
conformance register and legacy baseline. Architecture tests reject unowned
test files and missing registered artifacts. Human review remains responsible
for semantic claims that static analysis cannot prove.

## Cleanup proof and completion claims

Passing tests, a successful build, a clean worktree or a successful push proves
only that result. None proves that an approved cleanup or migration is complete.
Before claiming cleanup completion or contract conformance, the responsible
review must:

1. name the exact contract clauses, conformance rows and filesystem/runtime
   scope being cleaned;
2. recursively inventory tracked, untracked, ignored and empty paths in that
   scope and compare them with the approved target disposition;
3. classify every path as target source, retained content, developer input,
   generated material, current registered debt or a proved deletion candidate;
4. trace static imports plus dynamic launch, CLI, scene/resource, export,
   documentation and external-consumer references as applicable;
5. report completed, retained and remaining items separately, then run the
   relevant scanner and positive/negative behavior checks.

An unclassified path or an open affected conformance row makes a completion
claim false even when every selected test passes. Contract-guarded cleanup roots
use permanent structural classification. Unknown direct entries fail, and a
temporary path owned by an open row may shrink or change but may not gain new
files.

A row newly marked `closed` must carry one compact evidence cell containing all
five machine-stable fields: `target=`, `inventory=`, `references=`,
`verification=` and `residuals=`. Tests alone cannot supply all fields. Human
review checks their truth; the base-aware governance checker checks their
presence, bilingual status parity and transition.

## Local execution rules

The root `AGENTS.md` is the repository entry. A child `AGENTS.md` is required at
an ownership boundary where a local mistake could reverse dependencies, leak
authority, bypass persistence rules or weaken machine governance. Child rules
may refine but never reverse a parent contract. Ordinary leaf directories do
not receive ceremonial copies.

The System contract is summarized in the root `AGENTS.md` and refined at the
Elfie, Nest and high-risk ownership boundaries. The App contract is summarized at
`app/AGENTS.md` and refined at App areas plus high-risk lifecycle, embodiment,
device, API, Desktop, CLI, Setup, accounts, configuration,
persistence, architecture-scanner and architecture-test boundaries.

## Change classes

Every reviewed commit or pull request is one of two classes:

1. **Product/migration change.** It may change implementation-side files and
   reduce an existing architecture baseline. Implementation-side files include
   product code, Developer Tools, build/release scripts, ordinary tests,
   executable manifests, delivery workflows and documentation-site code. It
   must not change normative contracts, governance rules, the scanner or CI
   policy.
2. **Governance change.** It may change contracts, `AGENTS.md`, architecture
   scanners, governance CI and ADRs. It must not change implementation-side
   files.

Mixing these classes is forbidden. Documentation needed to describe a public
product behavior may travel with product code, but changing an architecture
contract or its enforcement still requires a separate governance change. This
prevents one change from weakening the rule that judges its own implementation.

## Contract change procedure

A deliberate ownership, dependency or authority change requires all of:

1. an accepted ADR describing context, options, decision and consequences;
2. synchronized English and Chinese contract version changes;
3. matching root/child `AGENTS.md` updates where execution guidance changes;
4. scanner and focused architecture-test updates where the rule is mechanical;
5. a governance-only pull request and maintainer review;
6. a separate later product migration, if implementation must change.

An ADR cannot approve an unbounded exception. Temporary implementation gaps
use a conformance ID, exact machine entry and deletion condition.

The repository-wide macro architecture is frozen as v1. Any later change to
top-level module ownership, authority, dependency direction, production
composition/lifecycle ownership or system-level Port semantics requires a new
standalone ADR, synchronized contract-version revisions and a governance-only
commit before any product migration. Editing an earlier ADR is not approval for
a new macro-architecture decision.

Architecture scanners, architecture tests and governance CI may change only in
a governance-only commit accompanied by a bilingual ADR update that explains
the rule change. A change that alters the contract itself additionally follows
the versioned contract procedure above.

## Incremental migration and continuous operability

Contracts describe the final target; they do not require the current tree to
reach it in one move. Existing violations may remain only when already named in
the conformance register and exact baseline. They may not be copied into new
code or used as precedent.

Every migration slice must keep the application buildable, testable and usable
on the main branch. The safe order is: define the target facade/Port and strict
models, implement the Adapter, wire it in Bootstrap, migrate the complete set
of production callers, prove at least one real path, then delete the old
implementation and reduce the baseline. A partially migrated call chain never
lands on main.

Old and new implementations may coexist temporarily inside one unmerged slice
while callers are switched, but one fact still has one active authority. Dual
writes, fallback reads and compatibility aliases require explicit approval and
a deletion gate; they are not the default migration technique. If a capability
cannot be changed safely in one slice, split it at a stable Port or facade
boundary rather than breaking runtime behavior between commits.

## Base-branch ratchet

For App and system architecture rules, CI compares the exact candidate tree
against immutable facts from the Pull Request base commit:

- the base-branch scanner is run against candidate production code;
- every candidate violation must already exist in the base baseline;
- the candidate scanner must exactly match the candidate baseline;
- the baseline-free effective-dependency scanner must report zero forbidden
  repository targets;
- a normal change may delete baseline entries but may not add or rewrite them;
- a governance change may not edit a legacy baseline;
- governance and implementation-side changes may not coexist;
- deleted paths participate in classification and closure validation;
- a temporary cleanup path cannot gain a file absent from the base tree;
- conformance status and registration changes are compared with the base
  bilingual register rather than only with candidate files.

Implementation classification is repository-wide and fail-closed. After
governance artifacts and ordinary prose documentation are identified, every
other tracked file belongs to the implementation side, including product,
Developer Tools, scripts, tests, root runtime/toolchain configuration,
manifests, assets, documentation-site code and non-governance workflows.
Governance identity takes precedence for architecture scanners and tests.
Ordinary prose documentation is neutral and may accompany the change class it
describes. A new directory, extension or executable surface cannot remain
unclassified.

Therefore editing the current scanner, contract or baseline cannot make a new
production violation pass. The bootstrap change that first introduces this
gate may create its initial exact baseline because no earlier governance
contract exists. After it reaches the protected main branch, absence of the
base scanner is an error and a new or rewritten baseline is rejected.

The post-submit full run repeats the broad comparison for detection, but it is
not a substitute for pre-write protection. The live ruleset must forbid direct
and force pushes, require Pull Requests and merge queue, and bind the one
event-stable required check before main can move.

## Zero-debt state

The final product/migration change removes the last production violation and
the last exact baseline entry. It closes the final row with all five evidence
fields and marks both all-closed mirrors `Closure state: ready`; it does not edit
governance rules. This short-lived registered ready state is the handoff to an
immediate governance-only closure change, which performs one atomic cleanup:

1. inspect the active checkout, remove retired physical paths including empty,
   untracked and ignored directories, then run the permanent scanner in
   deny-all mode and focused architecture tests against the zero-debt tree;
2. run every architecture test registered to each contract being closed; if
   multiple contracts close together, run the complete `test/architecture/`
   suite instead of a selected subset;
3. delete the empty baseline and the all-closed conformance mirrors;
4. remove their registry fields, hard-coded test bindings, indexes and links;
5. replace temporary migration guidance in root/child `AGENTS.md` with only the
   durable target boundary and anti-regression rule;
6. search for retired gap IDs, dead links and migration-only terminology,
   retaining them only in ADR history where their historical meaning is
   explicit; permanent anti-recreation tests may retain a retired baseline path;
7. after deleting the temporary artifacts, rerun the same scanners and required
   architecture tests, then verify bilingual mirrors, registry ownership and CI
   deny-all behavior before merge.

The closure is incomplete if any empty baseline, closure-ready registered
conformance page, retired physical path, stale local instruction or test that
requires a retired debt artifact remains, or if any contract-owned architecture
test has not passed. Registry tests allow an all-closed register only when it is
explicitly ready and every row has complete evidence; registered empty baselines
remain forbidden. The base checker includes deletions and rejects removal of an
open, unproved, one-language-only or product-mixed register. Permanent scanners
and architecture tests remain; CI's full test job includes the complete
architecture suite and treats every detected entry as a failure without
duplicating the same suite in another job.

A new baseline cannot be created to accommodate regression; only a separate
governance change with an accepted ADR may change the underlying contract and
scanner.

A conformance row may be marked `closed` only when every baseline rule mapped
to that row has zero entries, every temporary structural path mapped to it is
gone, and its five evidence fields are complete. Machine tests reject a closed
row that still has an exact-baseline entry or temporary path; human review
remains responsible for whether the referenced inventory, route and behavior
evidence is semantically sufficient.

## Ownership and external repository settings

The protected main branch must require the event-stable
`elfienest/merge-gate` from the expected GitHub Actions App, plus at least one
maintainer review for governance and CI changes. It must require the merge queue
and reject direct pushes, force pushes and deletion. Repository owners may add
CODEOWNERS only for verified accounts. Ruleset state and reviewer identity are
live repository settings and cannot be proved from source files alone.
