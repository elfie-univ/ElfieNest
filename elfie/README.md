# Elfie module

> 中文版：[`README_zh.md`](README_zh.md)

## Module positioning

`elfie/` implements a single complete creature: a stable profile, a three-layer
brain, memory and homeostasis, a nervous system, a swappable body, digital
communication and the skills usable during cognition.

This page describes the current package. The normative authority is the
[Elfie internal architecture contract](../docs/developer/contracts/elfie.md),
enforced by permanent architecture tests without changing the macro system
contract.

## Responsibilities and non-responsibilities

Responsible for:

- A single Elfie's identity, appearance, personality, capabilities and stable
  limits;
- The event-frame → context → reasoning decision → output routing →
  execution-receipt loop;
- Emotion, energy, long-term memory and the Elfie's own clock;
- Body identity, capabilities, typed commands/events, registry, binding and
  nervous-system semantics; deterministic no-I/O references and fakes may stay
  here, while concrete platform and device I/O belongs to Infrastructure;
- The Elfie's own digital message channel and its skill allowlist.

Not responsible for:

- Accounts, Web/API, desktop windows or product service lifecycles;
- Storing rooms, furniture, coordinates, Godot scenes or Nest resident tables;
- Choosing product-level model providers, persisting Runtime configuration or
  implementing model tools;
- Composing real Elfies with the Nest — that responsibility belongs solely to
  `app.orchestration.NestSession`.

## Directory map

```text
elfie/
├── elfie.py             # single-Elfie facade and lifecycle
├── factory.py           # Profile, Body, Communication, Runtime assembly
├── cognitive_context.py # sources of the individual context needed for cognition
├── cognitive_runtime.py # Coordinator, Router and worker lifecycle composition
├── message_types.py     # cross-boundary ID, Actor, time and error base types
├── profile/             # identity, species, appearance and the stable Profile
├── brain/               # ten-system cognitive core and private runtime
├── nervous_system/      # perception normalization, filtering, reflexes and physical output
├── body/                # Headless, Native, External swappable bodies
├── communication/       # digital message channel bypassing the NervousSystem
└── brain/reasoning/       # Reasoning ports, policy and bounded Skill loading
```

## Entry points

- `elfie.Elfie` — facade and async lifecycle of a complete Elfie;
- `elfie.ElfieFactory` — create an Elfie or restore it from a config directory;
- `elfie.brain.EventWorkspace` — admits typed events into isolated Turns;
- `elfie.brain.BrainCoordinator` — produces cognitive frames, context and
  reasoning runs;
- `elfie.brain.DecisionPlan` — the typed decision produced by Reasoning Core;
- `elfie.brain.reasoning.execution_router.OutputRouter` — routes a decision to body,
  communication or Persistent Activity.

Only `elfie.Elfie` and `elfie.ElfieFactory` are stable production aggregate
entry points. The deeper imports above describe current internal module APIs
used by implementation and focused tests; App production code must not compose
an Elfie by coordinating those mutable internals directly.

The core loop is:

```text
Body -> NervousSystem ----\
                          -> EventWorkspace -> BrainCoordinator
Communication ------------/                         -> DecisionPlan
                                                     -> OutputRouter
ExecutionReceipt ----------------------------------> EventWorkspace
```

The physical clock, perception collection, model inference and output execution
are all decoupled. The historical synchronous cognitive entry has been removed
from the product path; callers must cooperate through typed perception, the
cognitive lifecycle and output receipts.

Typed boundaries are defined by Pydantic v2 frozen models or discriminated
unions. Pydantic models are the single source of truth for internal contracts;
when a JSON Schema is needed, call `model_json_schema()` on the public model on
demand — do not maintain Schema files or export scripts in the repo.

## Dependency direction

```text
app/orchestration ──> elfie
elfie.elfie ──> profile + brain + nervous_system + body + communication
brain/output ──> abstract Food, model, tool and execution ports
```

`elfie/` does not import `app/`, `nest/` or `ai_runtime/` in reverse. Model
and Food access use Elfie-owned Ports; Bootstrap injects concrete Infrastructure
Adapters directly. Ordinary model/tool calls do not pass through App
Orchestration.

## Run & debug

Run single-Elfie and cognitive-loop checks from the repository root:

```bash
uv run --no-sync pytest -q test/elfie/

uv run --no-sync pytest -q \
  test/elfie/test_cognitive_lifecycle.py \
  test/elfie/brain/workspace/test_system.py \
  test/elfie/brain/reasoning/test_coordinator.py \
  test/elfie/brain/reasoning/test_output_router.py
```

For the full environment setup and quality gate see
[`CONTRIBUTING.md`](../CONTRIBUTING.md); for cross-module timing see
[`docs/developer/`](../docs/developer/).

## Corresponding tests

- `test/elfie/`: single-Elfie facade, factory, identity and cross-submodule
  composition;
- `test/elfie/brain/`: perception, context, decision, emotion, energy and
  memory;
- `test/elfie/body/`, `test/elfie/nervous_system/`: body and physical
  boundaries;
- `test/elfie/communication/`, `test/elfie/brain/reasoning/`: messages and Reasoning;
- `test/architecture/test_elfie_cognitive_contracts.py`: cognitive entry
  points, dependency direction, Pydantic contracts and the on-disk Schema ban.
