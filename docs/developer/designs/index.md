# Designs

Designs preserve accepted cross-version intent and the reasoning behind future
architecture. They may describe both completed and upcoming versions, but do not
claim that the current source already conforms. Normative rules remain in
[Architecture contracts](../contracts/), and current implementation gaps remain
in [Conformance](../conformance/).

- [Elfie top-level module design](./elfie-top-level-module-design): target
  top-level ownership for one complete Elfie.
- [Elfie Brain ten-system architecture](./elfie-brain-ten-system-architecture):
  the conceptual systems, boundaries, runtime loops and implementation order of Brain.
- [Elfie Memory architecture](./elfie-memory-architecture): episodic memory, the personal
  knowledge graph and hybrid graph/text retrieval.
- [ElfieNest service lifecycle state-machine design](./service-lifecycle-state-machine):
  authoritative service states, entrypoint behavior, ownership and failure convergence.
- [Provider and endpoint-model availability](./provider-model-availability):
  curated model loading, serving-core scope, low-cost evidence and shared health projections.
- [Virtual appearance generation](./virtual-appearance-generation): geometry inputs, four ordered
  skin layers, semantic regions, palettes and visual acceptance gates for one immutable Elfie look.
