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
| PMA-001 | P0 | in progress | The generic and curated discovery paths are bounded and integrity-pinned remote catalogs are rejected safely, but there is no concrete product-specific official adapter for every `provider_adapter` product and no user-facing transactional cleanup action for source-managed obsolete models. | Add each required official adapter and an explicit cleanup command that rechecks all references and 30-day production-use absence in the deletion transaction. | `infrastructure/models/validation/provider_validation.py`, `infrastructure/models/providers/discovery.py`, `infrastructure/models/providers/remote_catalog.py` |
| PMA-002 | P0 | in progress | Exact endpoint capability declarations, evidence levels and Request Profiles are implemented; controlled vision/tool/reasoning/structured-output probes and verified evidence promotion are not. | Add side-effect-free capability probes and persist channel-specific verified/unsupported evidence without treating text success as proof. | `infrastructure/models/provider_records.py`, `infrastructure/models/providers/endpoint_capabilities.py`, `infrastructure/models/providers/request_profiles.py` |
| PMA-003 | P0 | in progress | Production/validation observations, fingerprints, read-time projection and query Port are implemented. A distinct five-minute reachability evidence stream and bounded retention/rollups are not yet present. | Add transport/auth observations with five-minute freshness and retention/rollup policy while preserving exact endpoint evidence. | `infrastructure/models/model_execution_observations.py`, `infrastructure/persistence/provider_availability.py`, `infrastructure/models/validation/provider_availability.py` |
| PMA-004 | P0 | in progress | `ServingFoodIndex` implements assignment/default/emergency/direct-use and 24-hour/30-day role windows with endpoint deduplication. Required optional-role policy is not persisted/exposed and queued-work cancellation is not implemented. | Persist required role policy, increment the projection generation on Food changes, and cancel obsolete scheduled work. | `infrastructure/models/validation/serving_food.py`, `app/bootstrap/container.py`, `app/features/configuration/food/port_models.py` |
| PMA-005 | P0 | in progress | Typed error scope, account early-stop, transient hysteresis, cross-model transport promotion, bounded concurrency, single-flight and cooldown are implemented. There is no cross-process scheduler lease or periodic core-validation worker. | Add one leased scheduler entry point that validates only due core endpoint/channel subjects. | `infrastructure/models/provider_errors.py`, `infrastructure/models/validation/provider_validation_runs.py`, `infrastructure/persistence/provider_availability.py` |
| PMA-006 | P1 | in progress | Card background/badge semantics, bounded summaries, serving-core homepage filtering and local service/model gates are implemented. Obsolete-model view/cleanup UI and live-provider/browser acceptance evidence remain. | Add the obsolete-model management surface and record a served-checkout/browser acceptance run with real credentials supplied out of band. | `app/interfaces/web/frontend/src/components/OwnerProviderPanel.tsx`, `app/interfaces/web/frontend/src/components/ManageMonitorPanel.tsx`, `app/interfaces/web/frontend/src/components/OwnerOllamaPanel.tsx` |

## Closure order

1. Complete official discovery/cleanup and endpoint capability evidence.
2. Add transport evidence and persisted serving-role policy.
3. Add the leased core-only scheduler and retention policy.
4. Finish obsolete-model UI and live/browser acceptance.

The design register remains open until every row has `target`, `inventory`,
`references`, `verification` and `residuals` evidence, and the permanent
behavior, architecture and browser gates remain deny-all.
