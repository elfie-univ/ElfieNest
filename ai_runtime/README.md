# AI Runtime Directory Layout

`ai_runtime/` is the L0 infrastructure layer for model access, model routing,
native tools, local fallback setup, storage helpers, and usage observation.
It should not depend on Elfie individual state or nest business logic.

Current package ownership:

- `gateway/`: runtime request entry points, generation loop, streaming,
  multimodal payloads, model readiness, and fallback handling.
- `providers/`: provider profiles plus Ollama, streaming, and API dispatch
  adapters.
- `models/`: model catalog, model groups, local model profiles, and registry.
- `policy/`: model food policy, scene classification, and route resolution.
- `tools/`: native anti-hallucination tools such as search, code execution,
  file access, and skill evolution.
- `storage/`: runtime data-home and migration helpers.
- `setup/`: install-time/runtime setup, including local Ollama fallback.
- `usage/`: token and usage observation. First-phase billing is intentionally
  observe-only.
- `safety/`: permission management for native tools.

New code should import from `ai_runtime` or the owned package above. The old
root-level `runtime/` package has been removed; do not add new compatibility
imports under that name.
