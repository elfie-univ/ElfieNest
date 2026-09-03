# ADR-0033: Embodied feedback and dynamic capability routing

**Status:** Accepted
**Date:** 2026-09-02
**Scope:** Brain event domains, embodied action/feedback, and Body/World routing

## Context

Earlier contracts grouped command receipts with Activity events under an
`Internal` source domain. The embodied design review found that this obscured
the physical return path, encouraged a separate Brain Turn for every receipt,
and made Nest appear to be either part of, or a bypass around, the Body chain.
The same review also found that a fixed `DecisionIntent` union could not express
capabilities registered by different virtual and physical bodies.

## Decision

1. Brain has exactly three input domains: `Communication`, `Embodied`, and
   `Activity`. Activity means Brain-owned work that survives a Turn; it is not a
   bucket for external receipts.
2. A body action outcome is an external `Embodied` fact. A communication
   delivery outcome is a `Communication` fact. Neither creates a fourth domain.
3. Body traffic always follows the same chain in both directions:
   `Brain -> NervousSystem -> Body/BodyPort -> Adapter -> Transport -> Gateway ->
   runtime/device`, and the reverse path back through Body and NervousSystem.
   Nest is not a hop in this direct Body channel.
4. Nest remains the household/world-semantic authority. A targeted semantic
   result produced by Nest enters the target Elfie's Body input boundary and
   then NervousSystem. If world resolution results in actor movement, the
   movement command must re-enter NervousSystem and Body before execution.
5. `accepted` and `started` are action-ledger states only. Brain receives one
   terminal outcome: `completed`, `rejected`, `failed`, `interrupted`, or
   `timed_out`. Cancellation is represented as `interrupted` with a reason.
   Timeout requests stop/cancel, and late terminal receipts are reconciled
   idempotently rather than reopening the action.
6. Event Workspace seals the immutable `TurnFrame`. It may coalesce one
   action's terminal outcome with compatible proprioception, touch, posture,
   position, or arrival facts in the same embodied causal window. A receipt
   does not have its own Brain-trigger rule, and one incoming event does not
   imply one model Turn.
7. Brain selects one or more registered capabilities through a finite generic
   typed invocation plan: broad category, dynamic `capability_id`, typed
   arguments, call/cause identity, deadline, and current subject. Concrete verbs
   such as `go_to`, `turn`, and `speak` are catalog entries, not a fixed
   `DecisionIntent` union. Lower layers choose the registered route and current
   body binding; compatible actions may be ordered or run concurrently.
8. Version 1 may wait for terminal completion inside an isolated execution
   worker, provided the Gateway receiver and sensor ingress remain live. Fully
   non-blocking Body submission and an asynchronous receipt stream are deferred
   to version 2.
9. Godot owns virtual physical truth, including coordinates, navigation,
   collision, visibility, audibility, animation, and actual execution. Brain
   receives normalized proprioception through Orientation, not raw physics
   frames. A physical device owns equivalent local sensing, safety, and
   actuator behavior through separately deployed device software.

## Consequences

- The Brain, Elfie, System, and Nest-Godot contracts are revised together.
- Chat output and embodied control remain separate circuits: chat uses natural
  language delivery; control uses catalog-checked structured calls.
- `BodyPort` remains thin but necessary as the stable body semantic boundary.
  `NativeBody` and `ExternalBody` are Infrastructure implementations, while
  Transport and Gateway remain target-specific Infrastructure components.
- The current source still contains `Internal` source naming, fixed decision
  variants, and synchronous execution details. Those are implementation gaps;
  this ADR does not claim that they have been migrated.

## Rejected alternatives

Rejected alternatives are treating body receipts as Activity events; creating
one Brain Turn for each lifecycle state; routing direct Body traffic through
Nest; allowing world results to bypass Body or NervousSystem; hard-coding every
body verb in Brain; putting pathfinding in Brain or NervousSystem; and requiring
the full asynchronous executor redesign in the first Godot vertical slice.
