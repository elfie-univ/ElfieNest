# Designs

Designs preserve accepted cross-version intent. They do not claim that the current source already
conforms; normative rules remain in [Architecture contracts](../contracts/), and current gaps remain
in [Conformance](../conformance/).

The whole-system design is a separate parent design. This reorganization does not relocate or
replace it. In particular, [Elfie top-level module design](./elfie/elfie-top-level-module-design)
describes the Elfie module only; it is not the whole-system design. Physical folders are created
only when an owner has multiple documents. This page is a catalog, not another parent design.

- App designs:
  - [Service lifecycle state-machine design](./app/service-lifecycle-state-machine): service state,
    entrypoints, process ownership and failure convergence.
  - [Native release validation and installed product journey](./app/native-release-validation):
    package, lifecycle and installed-product acceptance.
- Infrastructure singleton:
  - [Provider and endpoint-model availability](./provider-model-availability): curated model loading,
    serving-core scope, evidence and health projections.
- Elfie designs:
  - [Elfie top-level module design](./elfie/elfie-top-level-module-design): one complete Elfie's
    module ownership, life systems and boundaries.
  - Brain parent and systems:
    - [Brain ten-system architecture](./elfie/brain/elfie-brain-ten-system-architecture): the ten
      conceptual systems, boundaries, runtime loops and implementation order.
    - [Reasoning Core](./elfie/brain/elfie-reasoning-core): the bounded single-Turn cognitive loop.
    - [Selfhood and fixed model header](./elfie/brain/elfie-selfhood-and-fixed-model-header):
      Selfhood authority and the fixed online model prefix.
    - [Emotion system](./elfie/brain/elfie-emotion-system): affect state, dynamics and boundaries.
    - [Memory architecture](./elfie/brain/elfie-memory-architecture): durable experience, knowledge
      and retrieval.
    - [Brain evaluation and evolution system](./elfie/brain/elfie-brain-evaluation-system): evidence-
      first evaluation and constrained improvement.
  - Embodiment singleton:
    - [Virtual appearance generation](./elfie/virtual-appearance-generation): immutable generated
      appearance and visual acceptance boundaries.
- Nest singleton:
  - [Nest and Godot virtual living world](./nest-godot-virtual-world-functional-architecture):
    final Nest/Godot functional boundaries, semantic-physical loops and event routing.
