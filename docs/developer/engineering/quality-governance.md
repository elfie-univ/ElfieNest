# Repository quality governance

ElfieNest does not rely on a single test suite or on every contributor remembering
the architecture. Repository quality is maintained by several mechanisms that
serve different purposes and reinforce one another.

## The quality loop

```text
Design intent
    ↓
Versioned contracts and ADRs
    ↓
Root and directory AGENTS.md guidance
    ↓
Typed boundaries and focused implementation
    ↓
Tests, scanners, lint and type checks
    ↓
Exact baselines and base-branch CI ratchets
    ↓
Conformance closure and maintainer review
```

No layer replaces another. Human-readable architecture explains the current
system; contracts define rules; local Agent guidance applies those rules at the
editing boundary; machine checks reject detectable violations; review covers
semantic decisions that static analysis cannot prove.

## What each layer contributes

| Layer | What it protects |
| --- | --- |
| [Current architecture](../architecture/) | An understandable map of the system that exists now |
| [Architecture contracts](../contracts/) | Versioned ownership, dependency, authority and boundary rules |
| [Architecture decisions](../decisions/) | The context and consequences of significant accepted choices |
| Root and child `AGENTS.md` | The rules a coding Agent must apply in the directory it is changing |
| Types, Ports and facades | Explicit boundaries that make invalid coupling harder to express |
| Unit, integration and architecture tests | Observable behavior and machine-checkable structural rules |
| Scanners and exact baselines | A ratchet that admits only recorded legacy debt and allows it only to shrink |
| [Conformance registers](../conformance/) | Current, temporary gaps against accepted contracts and their deletion gates |
| CI and maintainer review | Independent verification and review of semantics that automation cannot judge |

## Why a change cannot weaken its own guard

Architecture-sensitive CI compares candidate production code using the scanner
and exact baseline from the immutable base commit. A normal product or migration
change may remove recorded violations, but it cannot add or rewrite them.
Governance and production responsibilities use distinct local commits. They may
share one final Pull Request because the immutable base contract, scanner and
architecture tests still judge the whole candidate; candidate rule changes
cannot silently make accompanying product code acceptable.

When a legacy baseline reaches zero, the temporary baseline and detailed
conformance register are removed. The scanner and architecture tests remain and
run in deny-all mode. For that baseline-backed rule set, the baseline's removal
therefore means the boundary is fully enforced, not that it is no longer checked.

## How a contributor uses the system

1. Read the nearest `AGENTS.md` files and the current architecture page for the
   area being changed.
2. Read the governing contract and active conformance row when the change touches
   ownership, dependencies, authority, persistence or another protected boundary.
3. Make the smallest complete change and run the tests closest to it.
4. Run the directly affected architecture checks when a protected boundary changes.
5. Report the actual evidence and keep governance and product responsibilities
   in clear commits; prefer one final PR when the immutable base accepts both.

The concrete commands and test layers are listed in [Testing & quality](./testing).
The normative rules for this system live in the
[repository architecture governance contract](../contracts/repository-governance),
and its accepted rationale is recorded in
[ADR-0003](../decisions/0003-architecture-governance-ratchet).
