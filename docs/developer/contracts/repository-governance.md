# Repository architecture governance contract

**Contract version:** 1.4
**Adopted:** 2026-08-10
**Enforced scope:** App and system root boundaries

This contract defines how ElfieNest architecture rules are organized, changed
and enforced. Machine-checkable App and system rules use exact baselines; the
conformance registers explicitly identify target rules not yet covered by a
scanner. The System contract defines the target four-module architecture and
its register records current root and technical-boundary debt.

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

No one mechanism replaces another. Contracts state the target, `AGENTS.md`
guides execution, machine gates reject detectable violations, conformance and
baselines record only legacy debt, and human review covers semantic rules that
cannot be proven mechanically.

## End-to-end governance workflow

Every architecture-sensitive change follows one visible loop:

1. read the nearest `AGENTS.md`, the governing contract and the current
   conformance row before changing code;
2. classify the work as a governance change or a product/migration change;
3. for governance, revise the ADR/contract/local guidance and machine rule
   without production code; for migration, keep the target fixed and select one
   complete capability or business-domain slice;
4. run the candidate scanner against its exact baseline and run focused
   architecture tests;
5. in CI, run the immutable base-commit scanner against candidate production
   code for both pull requests and protected-branch pushes, then require
   maintainer review;
6. after a migration proves its real call chain, remove the old implementation,
   reduce only the matching baseline entries and close only the evidenced
   conformance row;
7. when a rule set reaches zero, delete its baseline and conformance register
   and keep the scanner permanently in deny-all mode.

The machine-readable registry at
`scripts/architecture/contract_registry.py` links each contract version to its
language mirrors, ADR, local guidance, scanners, architecture tests,
conformance register and legacy baseline. Architecture tests reject unowned
test files and missing registered artifacts. Human review remains responsible
for semantic claims that static analysis cannot prove.

## Local execution rules

The root `AGENTS.md` is the repository entry. A child `AGENTS.md` is required at
an ownership boundary where a local mistake could reverse dependencies, leak
authority, bypass persistence rules or weaken machine governance. Child rules
may refine but never reverse a parent contract. Ordinary leaf directories do
not receive ceremonial copies.

The System contract is summarized in the root `AGENTS.md` and refined at the
Elfie, Nest and current migration boundaries. The App contract is summarized at
`app/AGENTS.md` and refined at App areas plus high-risk lifecycle, embodiment,
device, API, Desktop, CLI, Setup, accounts, administration, configuration,
persistence, architecture-scanner and architecture-test boundaries.

## Change classes

Every reviewed commit or pull request is one of two classes:

1. **Product/migration change.** It may change production code and reduce an
   existing architecture baseline. It must not change normative contracts,
   governance rules, the scanner or CI policy.
2. **Governance change.** It may change contracts, `AGENTS.md`, architecture
   scanners, governance CI and ADRs. It must not change production code.

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
- a normal change may delete baseline entries but may not add or rewrite them;
- a governance change may not edit a legacy baseline;
- governance and production-source changes may not coexist.

Production classification is path-based: every tracked non-documentation file
under a production root is product source, including configuration, scripts,
Godot scenes/resources and static assets. It is not limited to a source-code
suffix allowlist.

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

When a legacy architecture baseline reaches zero, the migration change deletes
that baseline and its conformance page. The permanent scanner and architecture
tests remain and CI switches that rule set to deny-all: every detected entry is
a failure. A new baseline cannot be created to accommodate regression; only a
separate governance change with an accepted ADR may change the underlying
contract and scanner.

A conformance row may be marked `closed` only when every baseline rule mapped
to that row has zero entries. Machine tests reject a closed row that still has
an exact-baseline entry; human review remains responsible for non-machine
closure conditions.

## Ownership and external repository settings

The protected main branch must require the architecture-governance CI check and
at least one maintainer review for governance changes. A valid CODEOWNERS team
may be added when the repository owner confirms its GitHub handle; this
contract does not invent a nonexistent account. Branch protection and reviewer
identity are repository settings and cannot be proven by source files alone.
