# ADR-0033: Genesis compiles once and committed Elfies depend only on final owners

**Status:** Accepted
**Date:** 2026-09-01
**Scope:** creation-source ownership, adoption inputs, Genesis compilation,
Profile/Selfhood/Memory materialization and post-creation runtime dependencies

## Context

ADR-0031 removed Profile and live Canon from ordinary Brain reasoning, but the
creation boundary remained underspecified. Current code and design text still
allow several incompatible interpretations: Profile can retain generator seeds,
user choices, capability references and arrival facts; Selfhood can expose a
Profile/Canon projection; and an Infrastructure persistence Adapter can decide
personal knowledge, relationships and episodes while writing the workspace.
Some documents also treat a full creation manifest and the original adoption
answers as permanent inputs for replaying an already committed Elfie.

Those interpretations create several competing authorities. They make it
unclear whether Profile is an external dossier or a world-model container,
whether Infrastructure is an Adapter or a life generator, and whether an
existing Elfie is restored from its own final state or regenerated from newer
world material.

ADR-0032 separately establishes the Reasoning Context Workspace and durable
Memory boundary. This decision builds on that completed ordinary-Reasoning
isolation and defines the upstream creation transaction and post-commit
severance that ADR-0032 does not cover.

## Decision

Revise the Elfie contract to 2.3, the Brain contract to 1.5, the Application
contract to 1.11 and the Configuration contract to 1.4.

1. The creation-source chain is one-way:
   `CreatorWorldSkeleton -> ResidentKnowledgeBaseline -> published
   GenesisSourcePackage`. It is curated and validated before an individual
   creation begins. It is not an ordinary runtime dependency or a second
   personal-knowledge store.
2. Accepted adoption selections, the generated `LifeContext`, the
   `PersonalGenesisPlan`, random seeds and source-package bindings are
   creation-transaction data. `elfie/genesis/` owns the deterministic semantic
   compiler and validation rules. A model may render bounded non-authoritative
   language only; it does not choose identity, knowledge, people, relationships,
   events or Memory policy values.
3. One validated creation bundle co-materializes sibling final-owner outputs:
   the external Profile, Brain Selfhood, Brain Memory and any other explicitly
   owned startup seed. App `resident_admission` coordinates commit, recovery and
   compensation. Infrastructure only loads typed source documents and persists
   typed outputs through consumer-owned Ports; it does not compile a life.
4. A successful creation commit severs operational dependency on all creation
   inputs. Ordinary startup and runtime restore the committed final-owner state;
   they do not reload, refresh or regenerate it from Canon, a source package, a
   questionnaire, `LifeContext`, a plan or a generation seed. Original answers
   and generation-only records are deleted after commit or terminal abort. An
   in-flight transaction may retain only the bounded candidate/output material
   needed for crash recovery. A minimal technical commit receipt may survive
   outside Profile for idempotency and audit, but it contains no questionnaire,
   world knowledge, replay seed or complete life plan.
5. Profile is a frozen external objective dossier, not a creation ledger. Its
   semantic allowlist is stable identity (`elfie_id`, final name, formal species
   and fixed gender where applicable), a stable age/birth anchor, immutable
   personal-origin identifiers and labels, and final virtual appearance.
   Technical schema revision is allowed. Profile excludes world knowledge and
   Canon references, generator/model/policy versions, seeds, user choices,
   source-package hashes, arrival/training events, relationships, biography,
   personality, self-understanding, abilities, permissions, budgets, current
   body and runtime state.
6. Selfhood owns the Elfie's internal identity and personality; Memory owns what
   this Elfie actually knows, people and relationships, and all episodes,
   including departure, training, arrival and adoption experiences. Profile and
   Selfhood may contain the minimum shared identity values only as creation-time
   validated sibling snapshots. Neither derives from or synchronizes with the
   other at runtime.
7. Ordinary Brain runs from Selfhood, Memory and current Brain state. Profile is
   read only by authorized external dossier/projection paths and aggregate
   identity checks; creation sources are unavailable to reasoning. Publishing a
   new source package affects future creations only. Any change to an existing
   Elfie requires a separately approved migration or an in-world learning event,
   never silent regeneration.

ADR-0006 remains the historical decision that established the life-system
owners, ADR-0031 remains authoritative for Selfhood and the fixed model header,
and ADR-0032 remains authoritative for Reasoning Context Workspace ownership.
This decision supersedes their narrower wording wherever they described Profile
creation provenance or left creation-input persistence ambiguous.

## Consequences

- There is one direction of derivation and no runtime branch back to world
  source material.
- Profile can be shown externally without exposing private answers, generation
  internals, cognitive state or world encyclopedic content.
- Backup and restore preserve a committed Elfie's final state rather than
  requiring an old source package to recreate the same person.
- Genesis algorithms remain deterministic and testable in the domain; storage
  and configuration Adapters remain replaceable technical edges.
- Current source does not yet fully conform. The Elfie, Selfhood and
  Configuration conformance registers remain open for the exact Profile,
  compiler-placement, source-duplication and input-disposal gaps. This governance
  decision does not claim that those product migrations have landed.

## Rejected alternatives

Rejected alternatives are treating Profile as a bag for every immutable field,
keeping questionnaires or seeds for indefinite regeneration, making Canon a
runtime Brain input, refreshing an existing Elfie when bundled world content
changes, placing semantic generation in a persistence Adapter, letting a model
invent the structured life plan, storing arrival history as objective Profile,
or maintaining Profile and Selfhood as a runtime synchronization pair.
