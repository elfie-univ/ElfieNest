# ADR-0019: Provider availability is endpoint-scoped and serving-driven

- **Status:** Accepted
- **Date:** 2026-08-15
- **Scope:** Provider inventory, endpoint capabilities, validation evidence and health projections

## Context

Provider reachability, account state, endpoint-model availability and model
capabilities have different failure scopes and refresh rates. Treating a generic
platform `/models` response as a subscription list can create hundreds of false
candidates. Combining a global model capability with a Provider capability can
claim support that one concrete Provider endpoint does not expose. Revalidating
every configured model wastes paid calls, while validating only models with
recent successes can make a failed assigned route disappear from recovery.

Food definitions create another distinction: every persisted reference must
protect deletion, but only Foods that can receive production traffic should
affect scheduled validation and homepage health.

## Decision

Adopt the following model:

- bundled Provider/model metadata has one registered source under
  `config/models/`; product profiles explicitly select product-specific discovery
  authority, and broad inventories remain diagnostic rather than normal lists;
- final capabilities, request profiles and availability belong to the exact
  `(connection_id, endpoint_model_id)`; canonical identities are display-only
  enrichment and never final endpoint authority;
- an all-reference guard protects deletion, while a separately derived
  `ServingFoodIndex` identifies current production routes and role-sensitive core
  models without using online presence or current model health as membership;
- immutable production and controlled-check observations feed one read-time
  availability projection; passive reads make no external call, and explicit
  active checks are freshness-aware, single-flight, rate-limited and scoped by
  typed failure classification;
- Provider cards, homepage health and local Ollama use that shared projection,
  while retaining different endpoint-count and serving-role-path summaries.

The normative details are version 1.8 of the
[Model, Food and tool behavior contract](../contracts/model-food-tool-behavior).
Current gaps stay explicit in the
[Provider/model availability conformance register](../conformance/provider-model-availability).

## Consequences

- Account-wide failures can be reused safely without manufacturing per-model
  failures; model and request errors remain narrow.
- Real traffic refreshes health at zero additional model-call cost, and scheduled
  work is limited to stale serving-core paths.
- Inactive Food references still block unsafe deletion but do not make system
  health yellow or consume validation calls.
- Endpoint metadata and evidence require schema and query changes before the UI
  can claim conformance; this ADR itself contains no product implementation.
