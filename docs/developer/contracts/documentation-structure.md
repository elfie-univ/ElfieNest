# Documentation structure contract

**Contract version:** 1.1<br>
**Adopted:** 2026-08-12<br>
**Enforced scope:** Public documentation information architecture

This contract defines the stable public documentation sections, the meaning of
each Developer document class and the governance required to change them. It
protects navigation and document ownership without turning ordinary content
editing into an architecture process.

## Public site structure

English is the default site root. Simplified Chinese is its semantic mirror
under `docs/zh/`.

```text
docs/
├── index.md
├── story/
├── user-guide/
├── developer/
│   ├── index.md
│   ├── architecture/
│   ├── designs/          # created when the first reviewed public design exists
│   ├── contracts/
│   ├── conformance/
│   ├── decisions/
│   └── engineering/
└── zh/
    ├── index.md
    ├── story/
    ├── user-guide/
    └── developer/
        ├── index.md
        ├── architecture/
        ├── designs/      # mirrors English when public designs exist
        ├── contracts/
        ├── conformance/
        ├── decisions/
        └── engineering/
```

`docs/.vitepress/`, `docs/public/` and `docs/scripts/` are site/repository
implementation directories, not reader-facing content sections.
`docs/.internal/` is private, excluded from the site and must not be linked from
public pages. An optional section directory is created only when it contains an
approved page; empty placeholder directories are not retained.

The former `getting-started/` section is forbidden. End-user installation,
configuration, operation and troubleshooting belong to `user-guide/`.

## Developer document classes

The Developer categories live directly under `developer/`. Wrapper directories
such as `current/`, `evolution/`, `governance/` or `archive/` must not be added.
Only `developer/index.md` may be a Markdown page directly in the Developer root.

| Directory | Responsibility | Lifecycle |
| --- | --- | --- |
| `architecture/` | Describes the current, verified implementation and runtime structure | Updated in place; history stays in Git |
| `designs/` | Significant, reviewed designs across released, active and superseded versions | Retained while valuable; status is explicit |
| `contracts/` | Versioned normative rules for code, boundaries and governance | Stable authoritative paths; changed deliberately |
| `conformance/` | Current temporary gaps against active contracts and their deletion gates | Detailed register removed after full conformance |
| `decisions/` | Accepted Architecture Decision Records | Retained permanently; later ADRs supersede earlier ones |
| `engineering/` | Explanations and working guidance for development, quality, debugging, tools, security and release | Kept aligned with the current toolchain |

User-visible capabilities and operation instructions belong to `user-guide/`,
not to a duplicate Developer capability catalog. Drafts, meeting notes, Agent
plans, execution logs and unreviewed future designs remain private.

## Design, contract and conformance history

Reviewed Designs may describe released, active or upcoming versions. A released
Design is not deleted merely because implementation finished; a later design
marks it superseded when appropriate. Seriously obsolete material may be hidden
from the main navigation, but the public tree is not subdivided into version or
archive directories.

One contract scope has one current authoritative document at its stable path.
Contract history is reconstructed from Git and ADRs rather than copied into a
parallel directory tree.

Conformance contains only current gaps. Closed rows are removed. When every gap
for a contract is closed and its exact baseline is empty, the detailed register
and baseline are deleted, the conformance index reports the contract as
conformant, and permanent scanners or architecture tests continue in deny-all
mode. Historical execution progress remains in Git and Pull Requests, not in a
public archive.

## Language and navigation parity

Every public English Markdown page has a Simplified-Chinese counterpart at the
same relative path under `docs/zh/`, and the reverse is also true. Both pages
change together and preserve the same meaning.

VitePress navigation uses the same reader model in both languages:

1. Home;
2. World & Story;
3. User Guide;
4. Developer Docs, organized as Current Architecture, Design & Governance, and
   Engineering.

Navigation labels may be translated naturally, but they must point to mirrored
document classes and cannot invent a second ownership model.

## Structural change procedure

Ordinary page edits and new pages inside an existing category do not change this
contract. A change to the top-level sections, Developer categories, category
meaning, language-mirror rule or document lifecycle requires all of:

1. a new accepted bilingual ADR;
2. synchronized version updates to this English and Chinese contract;
3. matching `docs/AGENTS.md` guidance;
4. VitePress navigation updates;
5. focused documentation-structure test updates;
6. Contract Registry updates and maintainer review.

This is a governance change and must not be mixed with production-source changes.

## Enforcement

The documentation-structure architecture test checks the public sections,
Developer root and category layout, English/Chinese Markdown mirrors, forbidden
legacy paths and required navigation paths. VitePress build verification checks
that the resulting public site can be rendered. Human review remains responsible
for semantic translation quality and whether content belongs in the selected
class.
