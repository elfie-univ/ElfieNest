# ADR-0006: Elfie life-system ownership and one-body authority

- **Status:** accepted
- **Date:** 2026-08-12
- **Scope:** one Elfie's stable Profile, Brain systems, Genesis and embodiment authority

> **Later refinement:** ADR-0033 supersedes this record's creation-provenance
> wording. The current contract limits Profile to an external objective dossier,
> makes Genesis the sole semantic compiler and removes creation-input bindings
> after commit. This file remains historical evidence, not the active rule.

## Context

ADR-0005 established the internal Ports/Adapters direction for one Elfie. Its
ownership table intentionally followed the implementation available at that
time: Profile still contained personality, capabilities and runtime limits;
aggregate cognition remained partly rooted outside `elfie/brain/`; and the Body
contract left future concurrent bodies open.

The subsequently reviewed Elfie story and ten-system Brain design now provide a
more precise life model. An Elfie has one continuous identity and Brain, two
independent external lines, three cognitive event sources and exactly one active
embodiment authority. Stable objective identity is different from a changing
self-model. Creation-time generation is different from ordinary runtime
cognition. Keeping these distinctions implicit would make the upcoming Brain
implementation preserve the wrong owners and require a second migration later.

## Decision

Revise the Elfie internal architecture contract to version 2.0:

- As refined by ADR-0033, Profile owns only immutable externally visible
  objective identity, stable age/birth and personal-origin anchors, and final
  virtual appearance. Creation provenance is transaction-only; Profile does not
  own it, personality, memory, capabilities, permissions, runtime limits,
  current body or current state.
- Brain owns ten conceptual systems: Event Workspace, Orientation, Selfhood,
  Emotion, Energy, Motivation, Memory, Reasoning Core, Persistent Activity and
  Cognitive Consolidation. Skills belong to the Reasoning Core side of Brain.
- The ten systems are conceptual owners, not a requirement for ten processes,
  databases or pre-created directories. A package is introduced only when it
  contains real state, contracts or behavior.
- Communication events, embodied events and internal triggers enter Brain as
  separate sources. Every admitted Turn has one source domain and one permitted
  response scope; cross-domain consequences require a later Turn.
- Brain's external decisions are limited to communication directives, nervous-
  system directives and persistent-activity requests, or no-op. Model, Skill and
  Tool calls remain internal cognitive operations rather than external life
  channels.
- Several authorized body candidates may be known to an Elfie, but virtual and
  physical embodiment are mutually exclusive at runtime. Exactly one selected
  body is the sensor/action authority outside explicit switching transactions.
  Headless remains a deterministic development/test substitute, not a third
  product body.
- `genesis/` owns creation-time rules and an ephemeral initialization bundle. It
  commits generated values to Profile and Brain owners, then retains no second
  copy and does not become a sixth runtime organ.
- `Elfie` and `ElfieFactory` remain thin aggregate boundaries. Private cognitive
  coordination belongs inside Brain; application Bootstrap still constructs
  technical Adapters and lifecycle Orchestration still owns system Runtime
  start/stop/restart.

This decision changes ownership inside `elfie/` but does not change root system
modules, Infrastructure dependency direction, Nest authority, production
composition or system-level Port semantics. The system contract therefore
remains at version 1.3. ADR-0005 remains the historical source for the accepted
Ports/Adapters direction; where its Profile, Brain or body-activation wording
conflicts with this decision, contract version 2.0 and this ADR supersede it.

## Consequences

The current source remains intentionally nonconformant until separate vertical
implementation slices close the registered gaps. In particular, root cognitive
coordination must move under Brain as behavior is implemented, Profile data must
be transferred only after its new owners exist, and initialization must become
Genesis without dual authority or compatibility storage.

The governance change does not move product code, change persisted data or
create empty Brain packages. A separate execution plan will compare the accepted
target with current callers and turn each gap into an independently visible and
reversible implementation stage.

Rejected alternatives are keeping Profile as a permanent bag of every stable
configuration, creating ten empty packages to mirror a diagram, allowing a
model/tool loop to act as a hidden communication or body channel, supporting
simultaneously active virtual and physical bodies, treating Genesis as a daily
runtime, and postponing all ownership cleanup until after the complete Brain is
built.
