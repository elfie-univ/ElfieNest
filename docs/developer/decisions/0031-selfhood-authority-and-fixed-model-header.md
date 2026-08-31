# ADR-0031: Selfhood owns the two individual blocks of one fixed model header

**Status:** Accepted
**Date:** 2026-08-30
**Scope:** Selfhood authority, Genesis initialization and online Elfie
`ReasoningRun` context assembly

## Context

The accepted Brain architecture separated Selfhood from Memory and Profile, but
the implementation and contracts still described Profile as Selfhood's runtime
anchor. Ordinary reasoning projects current Profile and Canon values, Selfhood
stores one mixed flat record, Memory maintains another core self narrative, and
the generic continuity checkpoint can restore a second Selfhood copy.

Reasoning also constructs identity, behavioral, response and epistemic text as
an inline prompt. Raw Big Five numbers are supplied directly to the model, while
application-wide story and operating constraints have no one reviewed source.
This makes it impossible to answer which facts are authoritative, which content
is stable, and which exact prefix every online reasoning request must preserve.

## Decision

Adopt the
[Selfhood and fixed model-header design](../designs/elfie-selfhood-and-fixed-model-header.md)
and revise the Elfie contract to 2.2 and the Brain contract to 1.3.

1. Every model request inside an online Elfie `ReasoningRun` begins with exactly
   four ordered system-header blocks:
   `APPLICATION_FRAME`, `IDENTITY_CORE`, `ADAPTIVE_SELF` and
   `OPERATING_CONTRACT`.
2. One human-authored, required, bundled-only `ReasoningConstitution` owns the
   first and fourth blocks. Infrastructure validates it and Bootstrap injects
   it; Genesis, users, Providers and models cannot generate or override it.
3. One atomic Selfhood state owns the middle two blocks. `identity_core` contains
   the creation-frozen minimum individual identity; `adaptive_self` contains the
   slow personality, personal values, interaction, coping and expression
   tendencies. A deterministic Selfhood projection renders both blocks.
4. Genesis reads accepted adoption inputs and creation-time Canon and
   co-materializes Profile, Selfhood and Genesis Memory. Profile remains the
   outer objective dossier. Ordinary Brain runtime reads neither Profile nor
   Canon and never synchronizes Selfhood against them. Existing Elfies carry no
   Canon-version binding.
5. Phase 1 has no adaptive update route. A later design may allow only a typed
   Memory-consolidation proposal to request bounded `adaptive_self` changes;
   Selfhood remains validator and durable committer, and `identity_core` remains
   immutable.
6. The per-Elfie Selfhood document is the sole phase-1 durable authority.
   Generic Brain continuity checkpoints do not contain Selfhood, model-facing
   projections are not persisted, and missing/invalid state fails before any
   model invocation without Profile, Canon, Memory or generic-persona fallback.
7. Runtime protocol and current state follow the fixed header. Retrieved Memory,
   Activities, observations, conversation history and the current message are
   context data. Host capability, scope, commit and receipt checks remain the
   enforcement authority.

The fixed header applies to initial, tool-continuation and repair calls inside
the same online Run and remains byte-stable for that Run. It does not apply to
Genesis, Memory consolidation, Provider probes, evaluation judges or
identity-less background workers. Model/Provider adapters may transport the
request but cannot add system instructions or change the Brain-owned message
order/content. Skill/Tool instructions enter Brain-owned `TURN_PROTOCOL` after
the fixed prefix.

## Consequences

- The same Elfie no longer has Profile, live Canon, Selfhood and Memory competing
  as runtime identity authorities.
- Application-wide prompt semantics can be reviewed and shipped identically
  across every machine without creating a per-Elfie copy.
- Internal numeric traits remain available to typed Brain consumers, but the
  model receives a bounded natural-language projection rather than raw numbers
  or dictionaries.
- Dynamic Emotion, Energy, Orientation, capability and response-schema content
  remains outside the fixed four blocks and does not become Selfhood.
- Automatic growth, its algorithm and existing-workspace migration remain
  disabled until separate designs provide evidence and persistence rules.
- The phase-1 source slice implements the authority, fixed-header and
  fail-closed boundaries above. The
  [Selfhood conformance register](../conformance/elfie-selfhood.md) keeps the
  real-model behavior matrix and existing-workspace migration open; those gaps
  must not be papered over by structural tests.

## Rejected alternatives

Rejected alternatives are a separate `IdentityKernel`, letting Reasoning rebuild
identity from Profile/Canon/Memory, storing final prompt paragraphs as state,
using Memory's core narrative as Selfhood, sending raw Big Five values as the
behavior protocol, putting Turn-specific schemas into the fixed operating
contract, persisting Selfhood in both YAML and a generic checkpoint, enabling a
wide update API before the growth algorithm exists, and treating prompt text as
the security boundary.
