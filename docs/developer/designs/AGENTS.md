# Public design placement and reading rules

This file governs `docs/developer/designs/` and all of its descendants. The Chinese mirror
under `docs/zh/developer/designs/` follows the same rules.

## Ownership and physical layout

- `designs/index.md` is a catalog only. It is not a parent design and does not create another
  authority layer.
- The whole-system design is a separate parent design. Its relocation is outside this change, and
  this file does not assign it a public path. `designs/elfie/elfie-top-level-module-design.md`
  is only the top-level design of the Elfie module; never use it as a substitute for the whole-system
  design.
- The logical first-level owners are `app`, `infrastructure`, `elfie` and `nest`.
- Within `elfie`, the logical submodules are `brain`, `embodiment`, `communication` and
  `genesis`.
- A physical directory is created only when an owner has multiple design documents. A
  subdirectory is created only when a submodule has multiple documents. Do not create empty
  directories or `index.md` files merely to represent a future module.
- A singleton document can stay in its current parent directory and declares its owner and
  parent design in its relation block. Current grouped documents live under `elfie/brain/`;
  current App documents live under `app/`.

## Parent links and reading order

Existing design text is preserved during reorganization. Only paths and the small relation
block should be added or corrected. Each design document declares:

```text
Owner module:
Parent design:
Child designs:
Normative contracts:
Current architecture:
Conformance:
Domain sources:
```

For a local change, read the nearest chain from the whole-system design to the module design,
then the submodule design, the target document, its contracts and its conformance entry. A
child refines its parent; it cannot silently redefine the parent's ownership or authority.
The normative system rule is `../contracts/system.md`; the verified present-state map is
`../architecture/index.md`. They are different layers from the target design and must not be
replaced by it.

## Elfie Brain

`Selfhood` is Brain system 3 and belongs under `elfie/brain/`. The other Brain systems follow
the accepted ten-system design. Skill and Tool are stage-gated capabilities used by Reasoning
Core, not an additional Brain system or a peer of `brain`, `embodiment`, `communication` and
`genesis`; do not create a `skills/` branch unless a separate accepted design later requires it.

Local implementation specifications, authoring guides and frontend/Godot design files remain
beside the code or asset owner. Do not duplicate them in this central design tree.
