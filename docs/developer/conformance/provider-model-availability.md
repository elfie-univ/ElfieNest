# Provider/model availability conformance

> Open migration register for version 1.8 of the normative
> [Model, Food and tool behavior contract](../contracts/model-food-tool-behavior).
> It records current implementation facts and remaining deletion gates; it
> does not weaken the accepted availability design.

**State:** partial

## Current conforming facts

- Provider product, connection, exact endpoint-model, report evidence,
  reference-guard and derived `ServingFoodIndex` are separate fact layers.
- Volcengine Coding Plan is `catalog_only` and currently exposes the eight
  curated Coding Plan model IDs; it never promotes the broad generic `/models`
  inventory into the normal subscription list. Generic discovery is bounded,
  rejects incomplete pagination, preserves authoritative empty results, and
  retains omitted inventory as `source_missing` instead of deleting it.
- Endpoint records carry connection-scoped limits, capability declarations,
  capability evidence and typed Request Profile ID/version. Dynamic health is
  derived from append-only observations and is not persisted in Provider model
  configuration. Production calls and validation use the same canonical
  configuration fingerprint.
- Passive exact-endpoint availability queries, bounded batch reads, permissioned
  active checks, process-local single-flight and cooldown are wired into App.
  The serving projection filters unused Foods and optional roles, and the
  Provider card, homepage Monitor and Ollama view consume the resulting gates.
- Ollama requires both a healthy service and the exact installed, eligible model;
  installation, startup repair and model download remain explicit actions.

## Open gaps

| ID | Severity | Status | Remaining deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| PMA-001 | P0 | in progress | Generic/curated discovery is bounded and integrity-pinned remote catalogs are rejected safely. No active bundled product currently uses `provider_adapter`; explicit obsolete-model cleanup now rechecks all references and the 30-day production-use gate before one replacement. | Add an official adapter whenever a product declares `provider_adapter`; finish the user-facing management surface separately. | `infrastructure/models/validation/provider_validation.py`, `infrastructure/models/providers/discovery.py`, `infrastructure/models/providers/remote_catalog.py`, `app/features/configuration/providers/service.py` |
| PMA-002 | P0 | in progress | Exact endpoint capability declarations, evidence levels, Request Profiles and side-effect-free vision/tool/reasoning/structured-output probes are implemented; capability evidence is persisted separately and latest evidence wins. | Prove the probes and fingerprint invalidation against every supported live Provider profile. | `infrastructure/models/provider_records.py`, `infrastructure/models/providers/endpoint_capabilities.py`, `infrastructure/models/providers/request_profiles.py`, `infrastructure/models/validation/capability_probes.py` |
| PMA-003 | P0 | in progress | Production/validation observations, fingerprints, read-time projection and a distinct five-minute reachability evidence stream are implemented. Bounded retention/rollups and live transport acceptance remain. | Add the retention/rollup policy without weakening append-only evidence, then run live transport/auth acceptance. | `infrastructure/models/model_execution_observations.py`, `infrastructure/persistence/provider_availability.py`, `infrastructure/models/validation/provider_availability.py`, `infrastructure/models/validation/provider_validation_runs.py` |
| PMA-004 | P0 | in progress | `ServingFoodIndex` implements assignment/default/emergency/direct-use and 24-hour/30-day role windows, persisted required-role policy, generation changes and cancellation of obsolete queued work. | Prove every Food mutation path refreshes the same generation and no stale scheduled task can execute in a live Core. | `infrastructure/models/validation/serving_food.py`, `app/bootstrap/container.py`, `app/features/configuration/food/port_models.py`, `infrastructure/models/validation/core_validation_scheduler.py` |
| PMA-005 | P0 | in progress | Typed error scope, account early-stop, transient hysteresis, cross-model transport promotion, bounded concurrency, single-flight/cooldown, cross-process lease and periodic Core-only worker are implemented. | Run multi-process and crash/restart acceptance and prove worker shutdown cannot block Core shutdown. | `infrastructure/models/provider_errors.py`, `infrastructure/models/validation/provider_validation_runs.py`, `infrastructure/models/validation/core_validation_scheduler.py`, `infrastructure/models/validation/core_validation_worker.py` |
| PMA-006 | P1 | in progress | Card background/badge semantics, bounded summaries, serving-core homepage filtering and local service/model gates are implemented. Obsolete-model view/cleanup UI and live-provider/browser acceptance evidence remain. | Add the obsolete-model management surface and record a served-checkout/browser acceptance run with real credentials supplied out of band. | `app/interfaces/web/frontend/src/components/OwnerProviderPanel.tsx`, `app/interfaces/web/frontend/src/components/ManageMonitorPanel.tsx`, `app/interfaces/web/frontend/src/components/OwnerOllamaPanel.tsx` |

## Closure order

1. Add the retention/rollup policy without weakening append-only evidence.
2. Prove cross-platform/core-worker and real Provider capability/transport acceptance.
3. Finish obsolete-model UI and live/browser acceptance.

The design register remains open until every row has `target`, `inventory`,
`references`, `verification` and `residuals` evidence, and the permanent
behavior, architecture and browser gates remain deny-all.
