# ADR-0005: Elfie internal Ports and Adapters

- **Status:** accepted
- **Date:** 2026-08-11
- **Scope:** one Elfie's internal architecture and aligned model/tool boundaries

## Context

The system contract already places `elfie/` in the domain core and requires
Infrastructure to implement its outbound Ports. It does not, however, define
the ownership boundaries inside one Elfie. The current package has good typed
Body and communication contracts, but it also keeps technical persistence,
Godot/device bodies, platform channels, root-level Skills and a broad Runtime
boundary beside domain behavior. Without a smaller contract, incremental moves
could preserve the wrong ownership or create duplicate abstractions.

Body and communication also have real multi-implementation requirements. One
Elfie may inhabit a Godot actor, one or more physical toys and a headless test
body; it may communicate concurrently through Web chat, the ElfieNest App and
third-party platforms. These variations need stable semantic Ports without
making transports part of Elfie cognition.

## Decision

Adopt the [Elfie internal architecture contract](../contracts/elfie) as the
normative target for `elfie/`:

- one Elfie is one aggregate and internal lifecycle boundary—not a system
  Runtime authority—and is entered through the stable `Elfie` and
  `ElfieFactory` Facades;
- Profile, Brain, NervousSystem, Body and Communication own distinct semantics;
  private aggregate coordination joins them without becoming a product Runtime;
- Skills move under Brain and authorize semantic tool requests; they do not
  wrap a Runtime or execute tools;
- outbound Ports live beside their consumers: Brain owns Food/model/tool and
  memory Ports, Profile owns its store Port, Body owns `BodyPort` for
  NervousSystem/aggregate routing, and Communication owns its channel Port;
- a curated root re-export may help Bootstrap, but it neither duplicates Port
  models nor acts as a Service Locator;
- every body implements the same `BodyPort`; stable identity, capabilities,
  registry and explicit binding support multiple and later concurrent bodies;
- every platform channel implements the same communication channel Port;
  canonical envelopes and typed receipts support concurrent channels;
- external communication enters an Elfie only after App resolves account,
  membership, target and authorization; Infrastructure cannot choose or
  authorize the target Elfie;
- the Elfie Facade is the inbound boundary for body and communication events;
  symmetrical inbound Protocols are not added without a real isolation need;
- technical storage, Provider, tool, Godot, device and platform-channel
  Adapters move to root Infrastructure and are constructed by App Bootstrap;
- Bootstrap owns construction and container lifetime, lifecycle Orchestration
  alone decides system Runtime start/stop/restart, and Elfie lifecycle remains
  limited to its internal aggregate;
- Brain Skill authorization cannot bypass the Tool Adapter's global and
  invocation safety intersection; workspace scope is injected into a scoped
  Adapter view instead of crossing `ToolPort` as a filesystem path;
- immutable bundled Skills and in-memory policy need no persistence Port;
  mutable Skill installation or durable state stays disabled until a separate
  contract decision is approved;
- migration proceeds one complete boundary at a time, removes the old path in
  the same slice and closes an explicit conformance item.

This decision refines the already accepted system architecture. It changes no
root module, authority owner, dependency direction, production composition or
system-level Port semantic, so system contract version 1.3 remains unchanged.
Any future proposal that changes one of those macro properties still requires
its own system ADR and contract version.

The model/Food/tool behavior contract advances to version 1.5 to align these
boundaries. The accepted Food behavior remains named roles, one optional
fallback and Emergency—not an arbitrary ordered fallback list. Tool availability
and workspace confinement are also behavior-preserving: only the ownership and
boundary representation are clarified.

## Consequences

Elfie domain tests can use typed fakes, while technical integrations receive
focused Adapter and Bootstrap tests. Body and channel growth becomes additive
without changing cognition. The public aggregate surface becomes smaller and
the Factory must eventually accept only typed dependencies.

The current package remains temporarily nonconformant. In particular, Skills,
memory/profile persistence, technical bodies, platform channels and the broad
Runtime bridge need separate migration slices. This ADR authorizes the target
and its governance checks, not a repository-wide source move or a compatibility
layer.

Rejected alternatives are a flat mutually importing Elfie package, a universal
`ElfiePort`, one Protocol per helper, keeping technical Adapters inside domain
submodules, one body/channel class per product caller, a generic Runtime proxy,
App Orchestration proxying normal cognition, and a one-shot migration.
