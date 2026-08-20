# Repository architecture governance contract

**Contract version:** 1.16
**Adopted:** 2026-08-12
**Revised:** 2026-08-20
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
| Tiered validation and check-scoped reuse | Match local effort to changed risk without repeating proven expensive checks | Permanent |

No one mechanism replaces another. Contracts state the target, `AGENTS.md`
guides execution, machine gates reject detectable violations, conformance and
baselines record only legacy debt, and human review covers semantic rules that
cannot be proven mechanically.

## Tiered validation and check-scoped reuse

Validation is selected from the changed-path impact, and a higher-risk result
may always escalate but never downgrade:

Every tier starts with the formatting and static-analysis fast lane. It must
finish before any test, build, documentation build or other expensive check.
Before a local submit candidate is frozen, preparation may run the Ruff
formatter in write mode only on the selected dirty or untracked `.py` and
`.pyi` files. It must refuse automatic formatting when one selected file has
both staged and unstaged changes. Commit hooks, tests and CI are check-only and
must never modify candidate files.

| Tier | Trigger | Required checks |
| --- | --- | --- |
| G1 commit | ordinary local change | fast-lane evidence, staged secret scan and affected tests |
| G2 push | feature-branch push or an affected integration path | G1 plus quality baseline and the affected API, persistence, architecture or documentation integration checks |
| G3 main | main-branch merge/release, governance/toolchain change or unknown impact | current-candidate checks and one required expensive backstop |

The candidate classifier owns the escalation decision. Unknown executable paths,
governance, toolchain, lockfile and delivery changes go to G3. A normal commit
does not wait for G3 unless its own impact requires that escalation; G3 remains
the protected-branch backstop.

Within one selected-tier invocation, the repository-wide quality baseline runs
at most once. G1 and the commit hook do not run it; G2/G3 invoke it directly
when required and must not invoke it again through an umbrella hook.

The main backstop reuses a ready pnpm installation when the corresponding
`node_modules/.modules.yaml` exists and its package manifest and lockfile are
unchanged from the base. It may install dependencies only when that proof is
absent or either input changed; a failed network install stops the gate rather
than retrying a broader validation tier.

Only a successful deterministic test check may be reused at check scope. A
delivery tier is a set of required checks, not part of a test check's identity:
the evidence key covers the check/rule version, exact command, declared input
contents and file modes, local tool fingerprint and immutable base when the
selection depends on that base. Therefore an unchanged focused test run by G1
is reused by G2 instead of being started again.

The local G3 pytest backstop is partitioned into registered bundles. The
repository packages remain separate, while the App package is split into
Bootstrap, Feature/Configuration, Interface, Orchestration and product-E2E
module slices. Each bundle starts with conservative source, test,
configuration and shared-fixture inputs, then adds the transitive local Python
import closure of its tests and declared source roots; dynamic or non-Python
entry points remain explicit inputs. An unknown executable input invalidates
every bundle. A bundle pass is reusable only when its pass record, immutable
base, coverage fragment, artifact digest, coverage/pytest versions, readable
coverage data and portable relative paths all agree. Running a complete
registered bundle earlier through the controlled runner creates that same
evidence, so G3 skips it. A narrower node, file or arbitrary selector cannot
prove the larger bundle. One invocation shares a repository content snapshot
across bundles and rechecks input signatures before accepting a cache hit. G3
combines all current bundle fragments and enforces the repository coverage
threshold once after combination; a failed combine invalidates the involved
fragments. Raw `pytest` commands remain useful for diagnosis but do not enter
this evidence store.

Exact-candidate evidence may still reuse a whole tier. G3 also records a
separate expensive-backstop fingerprint covering every changed source, test,
dependency, toolchain, documentation and validation-rule input. Any changed
path not explicitly treated as generated or ignored by the cache rules remains
part of that fingerprint and is fail-closed when it cannot be classified.

Failed, blocked, timed-out or live-provider results are never stored as passes;
a forced rerun that fails also removes an older pass for the same key. The
internal `--direct-main` path runs the complete backstop while retaining valid
bundle evidence. `--no-cache` only disables reading valid evidence for checks
already required by the selected tier; it never changes the tier or adds a
broader check. When one G3 bundle fails, earlier
successful bundle records remain valid; the next run skips those records and
resumes with the failed or still-missing bundle.
The fast lane stops on failure before any test or expensive check starts.
During a later repair loop, rerun the exact failed node first, then its owning
test file or module, then affected integration checks. A failure must not
automatically restart a broader gate or a previously proven check; run the
required G3 backstop once for the final executable candidate instead of
restarting it after every edit. Each expansion needs a new dependency or risk
reason. The worktree
fingerprint is checked again after every reused or executed gate; a change
discards the result. Cache records live only under ignored
`build/validation-cache/` and contain no source, credentials or user data.
GitHub status checks still have to pass on the latest commit SHA; local evidence
cannot replace CI for a new SHA.

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
4. run the candidate scanner against its exact baseline and run focused
   architecture tests;
5. in CI, run the immutable base-commit scanner against candidate production
   code for both pull requests and protected-branch pushes, then require
   maintainer review;
6. after a migration proves its real call chain, remove the old implementation,
   reduce only the matching baseline entries and close only the evidenced
   conformance row;
7. when the last gap in a rule set reaches zero, mark the evidenced register
   closure-ready and immediately complete the separate zero-debt governance
   workflow below; never leave an all-closed register or empty baseline as a
   steady state.

The machine-readable registry at
`scripts/architecture/contract_registry.py` links each contract version to its
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

For App and system architecture rules, CI compares the candidate tree against
immutable facts from the pull-request base commit or protected-branch
pre-push commit:

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

CI also performs this comparison after a direct protected-branch push so a
bypass is visible, but only repository branch protection can prevent that push
before it lands. Protected main therefore forbids direct pushes and requires
this check before merge.

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

The protected main branch must require the architecture-governance CI check and
at least one maintainer review for governance changes. A valid CODEOWNERS team
may be added when the repository owner confirms its GitHub handle; this
contract does not invent a nonexistent account. Branch protection and reviewer
identity are repository settings and cannot be proven by source files alone.
