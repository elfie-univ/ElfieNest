# ADR-0037: One typed brain observation surface with a single sink Port

- **Status:** accepted
- **Date:** 2026-09-08
- **Scope:** Elfie Brain, Elfie assembly and developer tools

## Context

Brain boundaries previously reported progress to developer tools through two
ad-hoc dict callbacks (`memory_observer`, `context_observer`) wired through
`Elfie.configure_cognition`. The events had no shared envelope, no common
lifecycle fields and no stable boundary taxonomy; every consumer re-parsed its
own dict shape, production paths built event dicts even when nobody was
listening, and each developer tool invented its own capture path. This is a
change to what the composition root injects into the Brain aggregate, so it
needs a decision.

## Decision

- Brain owns one typed outbound observation Port: `BrainObservationSink` (a
  Protocol with `emit`/`snapshot`), the immutable `BrainObservation` envelope
  and `NoOpSink`, all defined in `elfie/brain/observation.py`. Assembly injects
  at most one optional sink through
  `Elfie.configure_cognition(observation_sink=...)` and `assemble_brain_runtime`
  distributes it to the holders; Brain defines no second observer callback.
- Every observable boundary emits one envelope whose `payload` is a named
  frozen model owned by its boundary group in dedicated payload modules:
  `elfie/brain/reasoning/observation_payloads.py`,
  `elfie/brain/reasoning/agent_loop_observations.py`,
  `elfie/brain/reasoning/run_controller_observations.py`,
  `elfie/brain/reasoning/coordinator_observations.py`,
  `elfie/brain/activity/observation_payloads.py` and
  `elfie/brain/memory/observation_payloads.py`. These modules fix the boundary
  taxonomy; payloads are never `Any` or raw dicts.
- Emit sites guard on `sink is not None` before constructing an envelope
  (guard-before-construct): a production path without a sink pays zero
  allocation cost. `test/elfie/test_observation_zero_cost.py` locks this.
- Observation must never affect brain behavior: `emit` does not raise and
  collection failures stay inside the sink.
- Developer tools (Elfie Lab, brain evaluation and brain-trace collection)
  consume the surface by implementing or wrapping the sink; they add no second
  brain callback path and no on-disk JSON Schema — the Pydantic models remain
  the single contract source.
- The Infrastructure model execution observer stays independent per ADR-0002:
  model endpoint observation is a capability-plane fact source and does not
  merge into, or implement, the brain observation surface.

## Consequences

One typed pipeline replaces the two dict callbacks, and all developer tools
read the same records. The Brain contract records the Port and payload modules
(version 1.10). Architecture tests keep the observation modules domain-pure —
no `infrastructure`, `app`, `nest` or `devtools` imports and no `Any`/raw
`dict` annotations — and keep the on-disk Schema ban for the observation
contracts.

## Rejected alternatives

- keeping `memory_observer`/`context_observer` and adding more per-feature
  dict callbacks;
- emitting `dict[str, Any]` payloads for flexibility;
- maintaining exported JSON Schema files as a parallel contract source;
- routing brain observations through the Infrastructure model execution
  observer, which would mix capability-plane evidence into the cognitive
  boundary;
- letting sinks raise so the brain could react to collector failures.
