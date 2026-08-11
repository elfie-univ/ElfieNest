# Cognitive information flow

> This page explains the current executable flow. Ownership, Facades and the
> target Food/model/tool, Body, communication and persistence Ports are
> normative in the [Elfie internal architecture contract](../contracts/elfie);
> current deviations are listed in [Elfie conformance](../conformance/elfie).

An Elfie's inputs and outputs are not a single unified chat string — they are
typed events routed separately across body, communication and internal
execution.

```text
Body → NervousSystem ───────┐
                            ├→ PerceptualWorkspace
Communication ─────────────┘
                                      ↓
                              BrainCoordinator
                                      ↓
                               BrainContext
                                      ↓
                               DecisionPlan
                         ┌────────────┼────────────┐
                         ↓            ↓            ↓
                       Body     Communication   Internal
                         └────── ExecutionReceipt ────┘
                                      ↓
                              PerceptualWorkspace
```

## One turn

1. `ElfieNestEngine` advances the clock and pumps body events;
2. `NervousSystem` and `Communication` each write independent events into the
   workspace;
3. `BrainCoordinator` seals the perception frame and submits an async cognitive
   turn;
4. The `DecisionPlan` is dispatched by `OutputRouter` to the specific output
   endpoints;
5. The execution result produces an `ExecutionReceipt` for the next round of
   perception.

This chain lets physical actions keep advancing without waiting for the model to
finish, and lets every category of input, output and receipt be tested and
replayed on its own.
