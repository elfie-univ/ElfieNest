# ADR-0013: Nest–Godot semantic-world ownership and event routing

- **Status:** accepted
- **Date:** 2026-08-13
- **Scope:** Nest internal ownership, Godot semantic channels and embodied-world event routing

## Context

The system contract already separates one Elfie's body channel from the shared
Godot world channel, but it does not define enough semantics for the upcoming
Nest migration. The current implementation mixes speech, user messages,
collision and tactile input in `InteractionHub`; routes several Runtime events
through every Body transport before applying special handling; and lacks the
structured visual, semantic-action and environment-object contracts needed by
the reviewed virtual-world design.

Keeping only the earlier three Nest areas would scatter three versions of the
same cross-authority workflow. Structured vision, virtual hearing and semantic
action all correlate one Elfie request or physical occurrence with Nest-owned
meaning, Godot-owned physical facts and one typed result. Conversely, treating
all occurrences as one broadcast stream would erase fact ownership, duplicate
body perception and make causal deduplication impossible.

## Decision

Adopt a dedicated Nest–Godot semantic-world contract and revise the System
contract to version 1.6.

Nest has four internal functional owners:

1. **Space and Facilities** owns the Nest ID and a coordinate-free household
   catalogue keyed by stable physical IDs published from the Godot scene, plus
   facility semantics and the minimum discrete projection needed by household
   rules.
2. **Household Living Rules** owns resident IDs, homes, ownership, sharing,
   reservation, occupancy, access and event-audience policy.
3. **Time and Environment** owns Nest time, life phases, scheduled environment
   rules and desired environment state.
4. **Elfie–Nest Interaction** owns the short-lived correlation and semantic
   assembly for structured vision, virtual hearing and semantic action.

These are ownership boundaries, not a requirement for four packages,
processes, databases or empty directories. The stable `Nest` facade remains the
inbound aggregate boundary.

A common Nest event mechanism crosses the four owners without becoming a fifth
business module. The owner of a fact creates its event. Household rules resolve
an audience only when policy is required, and a router delivers the already
targeted event once. Broadcast is an audience shape, never the default handling
for Godot Runtime events. Different facts caused by one physical occurrence use
distinct event types and IDs and may share one cause ID.

One authenticated Godot Gateway may carry several semantic lanes, but the lanes
remain non-interchangeable:

- known-target body commands, receipts, tactile and proprioceptive input flow
  directly between the owning Elfie Body and Godot;
- semantic action, structured vision, virtual speech/hearing and environment
  commands/facts cross the Nest semantic boundary through narrow typed
  capabilities;
- Runtime readiness, generation, connection and recovery flow to App Lifecycle.

Elfie remains the only originator of its body intent. Nest may resolve and
forward a target inside the original intent authorization, but cannot create,
schedule or rewrite Actor behavior. Nest may independently command world
objects when applying time or household environment rules. Godot remains the
authority for geometry, position, navigation, collision, visibility,
audibility and actual execution. App composes real objects and resolves target
IDs during cross-authority delivery, but does not become the semantic owner or
a mandatory hop for direct body traffic.

## Consequences

The repository gains Nest–Godot contract 1.0, a bilingual temporary
conformance register, a reviewed migration specification and matching local
execution guidance. The System contract advances to 1.6 because the semantic
meaning of the shared Godot boundary and event routes is now explicit. The
macro architecture remains v1: no root module, authority owner, production
composition root or lifecycle owner changes.

Current product code remains intentionally nonconformant until later vertical
migration slices close the register. This governance change does not move code,
change the Gateway protocol, create compatibility paths or claim the designed
visual/action/environment capabilities are implemented.

Rejected alternatives are keeping interaction scattered across three owners;
making events, residents, Gateway or recovery new business modules; routing all
Godot events through Nest; routing all semantic interactions directly to
Godot; storing coordinates or per-Elfie visible surroundings in Python; and
using per-Elfie rendered cameras or TTS-to-STT loops as the MVP perception path.
