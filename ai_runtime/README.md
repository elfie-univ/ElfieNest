# AI Runtime module

> 中文版：[`README_zh.md`](README_zh.md)

## Module positioning

`ai_runtime/` is the runtime layer for model access, provider adapters,
compute / food policy, native tools, safety permissions, configuration storage
and invocation observability. It serves the upper layers with inference
capabilities that are agnostic to any specific Elfie or Nest.

## Responsibilities and non-responsibilities

Responsible for:

- Unified text, multimodal, streaming and structured generation requests;
- Model catalog, Provider configuration, routing policy and local Ollama
  fallback;
- Elfie-facing food recipes, selection, validation and execution;
- Shared native tool implementations, permission checks and bounded execution;
- `ELFIE_HOME` data paths, Runtime configuration, key resolution and migration
  helpers;
- Model / tool invocation observability, usage accounting and local Runtime
  validation.

Not responsible for:

- Storing Elfie identity, emotion, memory, body or Nest state;
- Composing real Elfies, activity spaces, Godot or desktop lifecycles;
- Implementing product use-cases such as accounts, adoption or chat pages;
- Restoring the legacy top-level Python package `runtime/` or adding compat
  imports for it.

## Directory map

```text
ai_runtime/
├── gateway/     # RuntimeAgent, request models, generation loop, streaming & multimodal entry
├── models/      # Model catalog, local model profiles and registry
├── providers/   # Ollama and other provider configuration & invocation adapters
├── policy/      # Task classification and model routing policy
├── food/        # Food recipes, selection, planning, evidence and execution
├── tools/       # Search, code, file and skill-evolution tools
├── safety/      # Tool permission management
├── storage/     # ELFIE_HOME, configuration, keys and migration helpers
├── setup/       # Runtime initialization entry
├── usage/       # Invocation events and token usage observability
├── validation/  # Local validation of providers, models, tools and food
└── lab/         # Local interactive runtime lab
```

Shared tool implementations currently live here. The target architecture
decomposes this migration package; personal skill definitions and learned skill
state still belong to the corresponding Elfie workspace.

## Behavior and migration authority

The normative Provider, model, food, tool, persistence and acceptance contract
is the [model, Food and tool behavior contract](../docs/developer/contracts/ai-runtime.md).
Target ownership is defined by the
[system architecture contract](../docs/developer/contracts/system.md); there is
no target `ai_runtime/` module. This README maps only the current package.
Implementation deviations are tracked separately in
[AI Runtime conformance](../docs/developer/conformance/ai-runtime.md).

## Public entry points

- `ai_runtime.LLMRuntimeConfig` — loads models, providers and Runtime policy;
- `ai_runtime.RuntimeAgent` — unified inference entry point;
- `ai_runtime.RuntimeRequest`, `ai_runtime.RuntimeResult` — plain generation
  request and result;
- `ai_runtime.gateway.RuntimeAgent` — the same Gateway public entry as the root
  package;
- `ai_runtime.lab.RuntimeLab` — interactive lab for local dev validation only.

Structured generation uses `RuntimeAgent.generate_structured()` together with
`StructuredRuntimeRequest`. Callers submit a runtime request; the application
layer is responsible for converting the result into the types expected by the
Elfie cognitive ports.

## Current dependency direction

```text
app/orchestration ──> ai_runtime.gateway
app/features      ──> ai_runtime public entry points for config, policy, storage & validation
ai_runtime.gateway ──> models + providers + policy + food + tools + safety
```

The Runtime core does not depend on `elfie/` or `nest/`, and must not know about
real Elfies or activity-space objects. First-time installation belongs to the
application Setup boundary; AI Runtime does not own a separate installer.

## Run & debug

Run Runtime tests from the repository root:

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q test/ai_runtime/

UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q \
  test/ai_runtime/test_runtime_agent.py \
  test/ai_runtime/test_structured_generation.py
```

The local Runtime Lab uses an isolated dev data directory to avoid reading
production configuration:

```bash
ELFIE_HOME=/tmp/elfienest-runtime-lab \
  .venv/bin/python -m ai_runtime.lab
```

For environment preparation, key rules and the unified quality gate, see
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Corresponding tests

- `test/ai_runtime/`: Gateway, providers, models, policy and tools;
- `test/ai_runtime/food/`: food recipes, planning, evidence and execution;
- `test/infrastructure/persistence/`: configuration, keys and data boundary;
- `test/ai_runtime/validation/`: local validators and the Runtime Lab;
- `test/architecture/test_project_structure.py`: current source root, the
  legacy `runtime/` package ban, and quality gate entry points.
