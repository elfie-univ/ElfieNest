# Provider/model availability conformance

> Open migration register for version 1.8 of the normative
> [Model, Food and tool behavior contract](../contracts/model-food-tool-behavior).
> It records current implementation facts and remaining deletion gates; it
> does not weaken the accepted availability design.

**State:** in progress

## Current conforming facts

- Provider product, connection, exact endpoint-model, report evidence,
  reference-guard and derived `ServingFoodIndex` are separate fact layers.
- Volcengine Coding Plan uses a product-specific adapter against the
  subscription-scoped `/models` endpoint under the `/api/coding` gateway. Its
  eight bundled IDs are only the product-maintained core/fallback set; they do
  not stand in for account entitlement. The adapter is bounded, rejects
  incomplete pagination, preserves an authoritative empty result, and retains
  omitted inventory as `source_missing` instead of deleting it.
- Built-in OpenAI-compatible/API products read the live authenticated model
  inventory. The small bundled list marks the core models shown by default;
  other IDs returned by a complete authoritative endpoint are retained as
  hidden **Other discovered** models and can be enabled with one click. Custom
  OpenAI-compatible endpoints also use `/models`, so users do not need to
  retype every returned ID. A product-specific adapter is required whenever a
  broad platform inventory is not the product entitlement source.
- Endpoint records carry connection-scoped limits, capability declarations,
  capability evidence and typed Request Profile ID/version. Dynamic health is
  derived from append-only observations and is not persisted in Provider model
  configuration. Production calls and validation use the same canonical
  configuration fingerprint.
- Passive exact-endpoint availability queries, bounded batch reads, permissioned
  active checks, process-local single-flight and cooldown are wired into App.
  The serving projection filters unused Foods and optional roles, and the
  Provider card, homepage Monitor and Ollama view consume the resulting gates.
- Capability probes are endpoint-scoped and channel-specific. Tool, vision,
  reasoning and structured-output evidence is stored separately from text
  health, and only observed feature use can promote accepted evidence to
  verified.
- Provider reachability has its own five-minute projection and does not consume
  model-generation tokens. Core model checks run through a SQLite-backed
  cross-process lease scheduler; only endpoints in the current `ServingFoodIndex`
  enter the periodic model-validation queue.
- Source-missing models remain outside the normal model list and now have an
  explicit Owner-only obsolete-model view and guarded cleanup action. Cleanup
  rechecks the 30-day source/production-use conditions and all Food references.
- The report repository has guarded daily rollups and retention: ordinary
  callers cannot mutate observations, while explicit maintenance aggregates
  old rows without prompt/response content before deleting only observations
  from finished runs.
- A scheduler run captures the ServingFoodIndex generation and abandons the
  remaining snapshot if Food/model configuration changes during the run; the
  next tick schedules the new generation.
- Ollama requires both a healthy service and the exact installed, eligible model;
  installation, startup repair and model download remain explicit actions.

## Conformance rows

Rows marked `closed` are retained as audit evidence for this migration; the
remaining `in progress` rows are the outstanding gaps.

| ID | Severity | Status | Remaining deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| PMA-001 | P0 | in progress | Live `/models` discovery, core/other inventory separation, one-click enablement, the Volcengine Coding Plan product adapter and two-refresh obsolete retention are implemented. Deletion remains an explicit Owner action. | Exercise the guarded cleanup flow after the 30-day/reference gates pass. | `infrastructure/models/validation/provider_validation.py`, `infrastructure/models/providers/discovery.py`, `infrastructure/models/provider_administration.py`, `app/interfaces/web/frontend/src/components/ProviderModelsDialog.tsx` |
| PMA-002 | P0 | closed | Endpoint-scoped controlled probes, semantic Request Profile mapping and channel-specific evidence promotion are implemented. The configured, actively used Volcengine Coding Plan is the representative remote Provider for this release and passed its live 8-model text matrix plus per-endpoint tools/vision/reasoning probes. Unconfigured adapters are explicitly deferred until they become configured and actively used. | Every release must run the real-provider capability matrix against one configured, actively used remote Provider representative and record any adapter-specific gap; additional adapters enter scope when configured and used. | target=representative remote Provider capability matrix; inventory=8 configured Volcengine Coding Plan endpoint models and tools/vision/reasoning channels; references=`infrastructure/models/validation/provider_capability_probes.py`, `infrastructure/models/provider_administration.py`; verification=live run `run_81c08bccaf6e41d69ced2114d5fcb715` in `$ELFIE_HOME/reports/ai-runtime.sqlite`; residuals=unconfigured adapters deferred until configured and actively used |
| PMA-003 | P0 | in progress | Production/validation observations now coexist with a distinct five-minute transport/auth evidence stream and read-time reachability projection. The repository has guarded daily rollups and bounded raw retention; the periodic scheduler invokes compaction through the shared maintenance lease. | Verify retention and rollup behavior against a long-running installation, including restart and late-observation boundaries. | `infrastructure/models/validation/provider_validation_checks.py`, `infrastructure/models/validation/provider_availability.py`, `infrastructure/models/validation/provider_scheduler.py`, `infrastructure/persistence/reports/report_repository.py`, `infrastructure/persistence/reports/report_schema.py` |
| PMA-004 | P0 | closed | `ServingFoodIndex` implements assignment/default/emergency/direct-use and 24-hour/30-day role windows with endpoint deduplication and a content-derived generation. Required optional-role policy is persisted, exposed in the Food editor/API, and the scheduler abandons stale generations before probing. | A replayable runtime scenario changed the serving Food during an in-flight validation, cancelled every stale queued channel, and validated the next generation. | target=serving Food generation invalidation; inventory=Food assignment/default/emergency/direct-use roles, required-role policy, generation and queued validation channels; references=`infrastructure/models/validation/serving_food.py`, `infrastructure/models/validation/core_validation_scheduler.py`, `infrastructure/models/validation/provider_scheduler.py`; verification=`test/infrastructure/models/validation/test_core_validation_scheduler.py` replay scenario; residuals=none |
| PMA-005 | P0 | closed | Typed error scope, account early-stop, transient hysteresis, cross-model transport promotion, bounded concurrency, single-flight/cooldown, a SQLite lease, generation cancellation, periodic core-only validation and lease-guarded retention maintenance are implemented. | Two independent POSIX worker processes shared one report database; exactly one performed each model-validation and retention operation. | target=single-flight and cross-process validation/retention lease; inventory=typed error classification, account stop, hysteresis, cooldown, generation cancellation, worker and SQLite lease paths; references=`infrastructure/models/validation/provider_scheduler.py`, `infrastructure/persistence/reports/report_repository.py`; verification=`test/infrastructure/models/validation/test_provider_scheduler.py` multi-process lease scenarios; residuals=none |
| PMA-006 | P1 | in progress | Card background/badge semantics, bounded summaries, serving-core homepage filtering, local service/model gates, obsolete-model inspection and guarded cleanup UI are implemented. Live-provider/browser acceptance evidence remains. | Record a served-checkout/browser acceptance run with real credentials supplied out of band. | `app/interfaces/web/frontend/src/components/ProviderModelsDialog.tsx`, `app/interfaces/api/v1/admin/model_providers/routes.py`, `app/interfaces/web/frontend/src/api/owner-providers.ts` |

## Closure order

1. Add only the remaining non-generic discovery adapters and collect endpoint capability evidence.
2. Record long-running retention and live/browser acceptance evidence.
3. PMA-002 uses the configured, actively used remote Provider as the current
   release representative; other adapters enter the gate when configured.
4. PMA-004 and PMA-005 are closed by the current replayable generation and
   multi-process lease scenarios.

The design register remains open until every row has `target`, `inventory`,
`references`, `verification` and `residuals` evidence, and the permanent
behavior, architecture and browser gates remain deny-all.
