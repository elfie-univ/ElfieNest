# ADR-0035: Hierarchical design placement and private source boundaries

- **Status:** accepted
- **Date:** 2026-09-03
- **Scope:** internal source material and public Developer design placement

## Context

The public design pages were flat even though the system has a whole-system design, four
first-level modules and a Brain with multiple accepted sub-designs. The private directory also
mixed world material, product material, technical target designs and execution plans. Directory
names did not tell an agent which parent design to read first or which document was authoritative.

## Decision

`docs/.internal/` has exactly three flat first-level directories:

- `elfaria/` for Elfaria world and resident-knowledge material;
- `product/` for product intent, story and experience material;
- `drafts/` for unfinished domain drafts.

No new private code-design, execution-log or execution-report category is introduced. Existing
legacy plans and technical drafts remain non-authoritative migration material until a separate
governance decision promotes, retires or removes them.

The public `designs/` category uses this logical hierarchy:

```text
whole-system design (separate parent; not relocated by this decision)
├── app/                         (created once App has multiple designs)
├── infrastructure/              (created once Infrastructure has multiple designs)
├── elfie/
│   ├── elfie-top-level-module-design.md  (Elfie module design only)
│   └── brain/                    (created because Brain has multiple designs)
└── nest-godot-virtual-world-functional-architecture.md  (Nest singleton)
```

The whole-system design remains a separate parent and is not relocated or assigned a
new path by this decision. `designs/elfie/elfie-top-level-module-design.md` is
only the top-level design of the Elfie module; its children are Brain, Embodiment,
Communication and Genesis, not App, Infrastructure or Nest. The Nest/Godot design is
a singleton at the public `designs/` root, so no `nest/` directory is
created yet. Physical directories are lazy: a directory is created only when that
owner has multiple documents, and no per-directory `index.md` is required.
`designs/index.md` remains a catalog, while actual design documents carry parent,
child, contract, current-architecture, conformance and domain-source references.

Selfhood remains under Brain because it is Brain system 3. Skill and Tool remain Reasoning Core
capabilities, not an additional Brain system.

Product and Elfaria are domain sources, not implementation designs. A Genesis design owns the
compilation rules that turn those sources into Elfie owner state. Cross-references are allowed,
but authority is not circular: public pages use stable source identifiers rather than direct
links into the site-excluded `.internal` tree.

## Consequences

An agent changing a local design reads the parent chain before the local document. Moving a
document does not rewrite its technical meaning; it only changes its path and adds explicit
relations. The structure is enforceable through scoped `AGENTS.md` files, bilingual governance
documents, navigation and the documentation architecture test.

## Rejected alternatives

- treating the Elfie top-level module design as the whole-system parent;
- an `index.md` in every module or submodule;
- pre-creating empty `app`, `infrastructure`, `nest`, `embodiment` or `communication` folders;
- keeping private code designs or execution histories as a second authority tree.
