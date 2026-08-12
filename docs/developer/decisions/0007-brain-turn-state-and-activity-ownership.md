# ADR-0007: Brain Turn, mental-state and persistent-activity ownership

**Status:** Accepted
**Date:** 2026-08-12

## Context

ADR-0006 and Elfie contract 2.0 fixed Brain as the owner of ten conceptual
systems, three input sources and three decision outputs. That aggregate-level
decision did not yet fix the internal semantics of a Turn, authoritative mental
state, bounded multi-step reasoning, long reasoning interruption, persistent
activities or recovery. Without a subordinate contract, an implementation plan
could accidentally treat typed payload tags as Turn isolation, expose
communication or body control as cognitive Tools, let a model write durable
state, or create Motivation before durable work can be bounded and recovered.

## Decision

Adopt Brain internal architecture contract 1.0 as the normative target inside
`elfie/brain/`.

- Brain has ten conceptual owners: Event Workspace, Orientation, Selfhood,
  Emotion, Energy, Motivation, Memory, Reasoning Core, Persistent Activity and
  Cognitive Consolidation. Mandatory governance and persistence mechanisms do
  not become peer mental systems.
- Event Workspace admits exactly one source domain into one immutable Turn.
  Communication, Embodied and Internal events may share committed mental state
  but never a Frame, transient reasoning state or output authority. Each Turn
  also binds one interaction scope, so independent conversations, body
  generations and internal causes cannot be mixed merely because their source
  domain is the same.
- Reasoning Core owns context assembly and a bounded Model/Skill/Tool loop. Tool
  use is cognitive work inside a deterministic sandbox; Communication, Body and
  device access remain external peripherals rather than Tools.
- Every Turn yields one decision. A deterministic serialized boundary allows at
  most one external domain, plus a validated Persistent Activity request, and
  commits mental-state candidates only through their authoritative owners.
- Persistent Activity uses side-effect-free preflight followed by post-Turn
  commit. Due work re-enters cognition as an Internal event. Motivation and
  Cognitive Consolidation cannot create activities or execute externally.
- Long and short Runs may overlap only with isolated transient state. Stale,
  expired or obsolete-body results cannot pass the single commit boundary.
- Durable Journal, state, checkpoint, budget, idempotency, causal trace and
  receipt reconciliation are cognitive infrastructure, not another mind.

The ten concepts may use flat files while small. A package is created only when
real state, contracts or behavior require it. This decision does not mandate a
storage schema, prompt, scoring formula, model provider, threshold or process
topology.

## Consequences

Brain contract 1.0 is subordinate to Elfie contract 2.0: Elfie remains the
authority for the aggregate and its two external lines, while Brain contract is
authoritative for internal cognitive lifecycle. No root system module,
Infrastructure dependency direction, Nest authority, body authority or public
Facade changes.

Current product code remains intentionally nonconformant until separately
approved vertical slices close the Brain register. The first implementation
plan must be generated from those gaps and must not build ten empty directories
or enable autonomous Motivation before Persistent Activity is bounded and
recoverable.

Rejected alternatives are embedding the entire design in the Elfie aggregate
contract, treating every mechanism as a peer module, using one mixed perception
frame with source labels, exposing external peripherals as Tools, letting model
text prove execution, and postponing all state/recovery boundaries until after
autonomous behavior is enabled.
