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
- Native tools (search, code, file, skill evolution) and their permission
  checks;
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

`custom_skills/` is the entry point for runtime custom skill packs; before
adding a capability, confirm it truly belongs to the Runtime rather than to the
product, a single Elfie, or the Nest domain.

## Provider and food identity

The bundled Provider catalog describes connectable products and contains no
credentials. User connections live in `ELFIE_HOME/configs/providers.yaml`; one
product may have multiple immutable connection IDs such as
`openai_api_0001`. Models preserve the endpoint model ID required by that
connection. Food roles reference models strictly as
`connection_id/endpoint_model_id`, so aliases may change without breaking an
Elfie's package and Runtime never silently crosses subscriptions.

Model discovery, connection verification and model benchmarks are separate
facts. Failed discovery preserves manually entered models. Sanitized reports
are written below `ELFIE_HOME/reports/`, while API keys and OAuth material stay
below `ELFIE_HOME/configs/credentials/`.

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

## Dependency direction

```text
app/orchestration ──> ai_runtime.gateway
app/features      ──> ai_runtime public entry points for config, policy, storage & validation
ai_runtime.gateway ──> models + providers + policy + food + tools + safety
```

The Runtime core does not depend on `elfie/` or `nest/`, and must not know about
real Elfies or activity-space objects. The current
`ai_runtime/setup/runtime_setup.py` calls the application configuration store
for install-time writes; this is an existing setup integration boundary and must
not be extended into the Gateway, Provider or tool cores.

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
- `test/ai_runtime/storage/`: configuration, keys and data boundary;
- `test/ai_runtime/validation/`: local validators and the Runtime Lab;
- `test/architecture/test_project_structure.py`: current source root, the
  legacy `runtime/` package ban, and quality gate entry points.
