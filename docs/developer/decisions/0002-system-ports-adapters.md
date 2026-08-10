# ADR-0002: System-level nested Ports and Adapters

- **Status:** accepted
- **Date:** 2026-08-10
- **Scope:** repository-wide target architecture

## Context

App already adopted lightweight Ports and Adapters, but concrete persistence,
model, Godot, device and file capabilities remain distributed across root and
domain directories. Treating each current directory as a peer obscures the
product hierarchy and lets technical details enter Elfie and Nest tests.

## Decision

ElfieNest adopts a nested system architecture:

- `app/` is the upper product/application layer;
- `elfie/` and `nest/` are the central domain cores;
- one running ElfieNest system always has exactly one Nest;
- target root `infrastructure/` contains model, tool, persistence, Godot,
  device, communication and platform Adapters;
- root `godot_project/` remains an independent Godot source project and
  physical authority; only its Python host, Gateway and protocol integration
  target `infrastructure/godot/`;
- current `ai_runtime/` is decomposed rather than moved intact: provider/model
  calls target Infrastructure, Food administration and reports target App
  Features, and Elfie consumes Food/model/tool capabilities through its own
  Ports;
- stable Elfie and Nest facades serve as inbound Ports without duplicate
  Protocols unless a concrete need appears;
- Elfie and Nest own their outbound semantic Ports; Infrastructure implements
  them; Bootstrap performs all concrete wiring;
- Infrastructure capability packages do not construct or import one another's
  concrete Adapters; Bootstrap composes narrow Ports;
- Orchestration coordinates runtime workflows but is not the composition root;
- ordinary Food lookup, model calls and tool execution use injected Elfie Ports
  directly and do not pass through App Orchestration;
- actor-body commands and Nest world facts use separate semantic channels over
  one shared Godot Gateway.

This decision establishes macro architecture v1. Later changes to its module
ownership, authority, dependency direction, production composition/lifecycle
ownership or system-level Port semantics require a new standalone ADR and
versioned governance change before implementation.

## Consequences

Current paths are migrated incrementally under an exact conformance register.
Domain tests can use fakes, technology replacement is isolated to adapters, and
module-internal changes remain local while Ports are stable. The change adds
explicit mapping and Bootstrap wiring. It does not promise that a deliberate
system-contract change affects only one module.

Rejected alternatives are keeping `ai_runtime/` as a target module for one
configuration bundle, moving it intact under Infrastructure, moving the Godot
source project under Infrastructure, placing Godot transport/process code in
Nest, routing ordinary model calls through Orchestration, allowing domain cores
to construct technical dependencies, one global generic repository, duplicate
inbound Protocols for every facade, and a repository-wide one-shot move.
