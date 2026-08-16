# Provider and endpoint-model availability design

> Status: accepted design<br>
> Confirmed: 2026-08-15<br>
> Review: adversarial review completed on 2026-08-15<br>
> Nature: cross-version product and technical design; it does not claim that the
> current implementation conforms<br>
> Normative behavior remains in the
> [Model, Food and tool behavior contract](../contracts/model-food-tool-behavior.md);
> current gaps are tracked in the
> [Provider/model availability conformance register](../conformance/provider-model-availability.md)

## 1. Goal and boundaries

This design defines how ElfieNest configures a local or remote Provider, loads a
useful endpoint-model inventory, learns endpoint-specific capabilities, validates
availability with the fewest additional model calls, maintains fresh evidence,
and exposes one status projection to the Owner UI and other application services.

The design does not benchmark model intelligence, infer quality from private
conversations, install or download large local models without user approval, or
allow business code to construct arbitrary Provider payloads.

The central distinction is:

- a catalog answers **which models may be selected**;
- an endpoint-model profile answers **what this connection/model pair supports**;
- evidence answers **what was observed and when**;
- availability answers **whether it can be used now**;
- the serving scope answers **whether its failure affects the running product**.

## 2. Fact layers and authority

| Fact | Meaning | Authority |
| --- | --- | --- |
| Provider product | Protocol, authentication, discovery strategy and adapter defaults without credentials | versioned Provider catalog |
| Provider connection | One account, subscription or local endpoint, credential reference and lifecycle | Provider connection store |
| Endpoint model | One exact `(connection_id, endpoint_model_id)` identity, metadata and request profile | connection model inventory |
| Evidence | Immutable validation and real-execution observations | report repository |
| Reference guard index | Every model reference, including inactive Foods, used to protect edits and deletion | projection from all persisted consumer references |
| Serving Food index | Foods and roles that can currently receive production traffic | projection from Food lifecycle, Elfie selection and production decisions |
| Availability | Current explainable Provider/model state | read-time projection from the facts above |

Dynamic availability, latency and errors must not be written back into Provider
configuration. A canonical model identity may enrich comparison metadata, but it
must never decide that a model supports a capability on a particular Provider.
The final capability and availability unit is always the exact endpoint model.

The bundled Provider and model catalogs are the registered documents at
`config/models/provider-catalog.yaml` and `config/models/model-catalog.yaml`.
Runtime code loads them through the typed configuration boundary defined by the
[Configuration management contract](../contracts/configuration-management.md);
package-local copies are not fallback authorities.

## 3. Provider configuration and model loading

### 3.1 Configuration flow

Known products ask for only an optional alias and the required credential. Their
base URL, protocol, authentication and discovery strategy come from the product
profile. A custom compatible endpoint exposes these advanced fields.

Custom endpoint URLs pass the product's outbound-network policy before any
credential is sent. HTTPS is required except for an Owner-approved local or LAN
Provider mode; link-local and cloud-metadata targets remain rejected, and a
redirect may never forward credentials to a different origin.

Saving a connection performs this ordered flow:

1. persist the editable connection and credential reference even if later checks fail;
2. perform a zero-generation HTTPS/API reachability check and authenticate when
   the product exposes a suitable non-generation endpoint;
3. load and merge the product-specific model inventory;
4. run one tiny text request against the designated representative model;
5. publish the inventory, evidence time and actionable result.

A network reachability check is not model validation. When no non-generation
authentication endpoint exists, the projection may say `reachable` while account
usability remains `unknown` until a real request succeeds.

### 3.2 Ordered inventory sources

Endpoint IDs come from the first usable indexed source:

1. an authenticated, product-specific official inventory or adapter;
2. a versioned ElfieNest curated remote catalog;
3. the bundled curated catalog shipped with the application;
4. guarded manual input.

A successful authoritative response with zero entitled models is an
authoritative empty inventory, not a discovery failure. Lower catalogs may then
show clearly labelled recommendations, but they cannot claim that the account
owns those endpoints. A refresh counts as successful for missing-model decisions
only after every required page has completed and the adapter has confirmed the
response is complete.

A generic `/models` response is used only when the product profile explicitly
declares it authoritative for that subscription. A broad platform inventory must
not be treated as a subscription inventory. Lower-priority catalogs may fill
missing metadata only when that metadata is product/endpoint-specific, and they
cannot replace IDs from a higher-priority source. A generic canonical-model
record may help grouping and display, but it cannot supply final context limits,
capabilities or request parameters for a connection endpoint.

Remote catalogs must be schema-valid, version-compatible and signed or
integrity-pinned, and they must never contain credentials. Discovery adapters
apply bounded response-byte and record-count limits. An oversized response is a
discovery failure and falls back to the curated source; it is not silently
truncated into an apparently authoritative list.

The normal UI inventory is the union of curated, manual and currently referenced
models. Additional IDs from a genuinely authoritative official inventory are
retained in a bounded, hidden endpoint inventory and shown only in a collapsed
**Other discovered** view. They do not affect card counts or automatic
validation until selected or referenced, but the user can enable one without
retyping its ID. A large raw discovery result is never shown as the normal
subscription list or validated wholesale.

### 3.3 Endpoint metadata and request profiles

Each endpoint model records stable or slowly changing facts with their source,
catalog version and update time:

- endpoint ID, display identity, source and last-seen state;
- context window and maximum output;
- text, vision, tool, reasoning and structured-output support;
- a typed request-profile ID and version;
- hidden, retired and source-missing lifecycle state.

Capability values are `supported`, `unsupported` or `unknown` per channel and
carry an evidence level such as `declared`, `accepted` or `verified`. Final
`supported` requires a product/endpoint-specific authoritative declaration or a
successful controlled probe. Merely accepting a request payload is not proof
that the model used the feature. A text success proves only text availability;
it does not prove vision, tools or reasoning. Reasoning capability means that
the endpoint's reasoning control is accepted and observable, not that the system
has measured model intelligence or hidden thought quality.

Manual capability input is retained as a `declared_by_user` hint. It may make a
model selectable for an explicit experiment, but it cannot silently become
verified capability evidence for a serving role.

Business code sends semantic options such as reasoning mode, tool definitions,
image input and output format. One Provider adapter profile maps them to the
wire protocol. Sparse endpoint-model overrides handle real exceptions. Users do
not maintain arbitrary JSON payload templates.

Catalog declarations are preferred for context limits and stable capabilities.
A tiny, side-effect-free capability probe is allowed only when a required value
is unknown, its profile version changed, or the model first enters a serving
role. Tool probes use a local no-op tool and can never invoke an external action.

### 3.4 Missing and obsolete models

A failed or empty refresh never removes inventory. After two consecutive
successful authoritative refreshes omit a discovered model, it becomes
`source_missing` and is hidden from the normal list. It remains visible in an
obsolete-model view with its reason and last-seen time.

A model is eligible for guarded cleanup only when it is source-managed, absent
for at least 30 days, not manual, not referenced by any Food or other consumer,
and has no production use during that period. Evidence history remains. The
first implementation should require an explicit cleanup action; rediscovery
recreates the model safely.

## 4. Serving Foods and core models

Core models are not derived from every Food definition. An enabled Food that no
one selected, a draft, an archived package, a visibility grant and a preview do
not justify scheduled model calls or affect system health.

The serving projection must not replace the all-reference guard. Inactive Food
references still protect Provider connections and models from deletion and keep
their dependency visible; they simply do not spend validation resources or
affect homepage health.

### 4.1 Serving Food projection

A Food is deployed only when it is enabled, not archived and has a resolvable
exact primary-model reference; current model health is not part of this lifecycle
test. A deployed Food enters the `ServingFoodIndex` when at least one condition
is true:

1. the same Food resolver used by Runtime accepts it as an existing Elfie's
   currently requested Food after lifecycle and visibility checks, even when
   model health temporarily sends execution to Emergency;
2. Common Food is the effective default for at least one Elfie with no stored
   primary selection;
3. Emergency Food is the enabled final fallback for at least one existing Elfie;
4. an authorized production route attempt selected or requested it during a
   short direct-use lease, initially 24 hours, even if the model attempt failed;
   preview, validation, benchmark, test and Developer Tool calls do not qualify.

Online, away and offline presence do not change membership: an assigned Elfie
may return at any time. Removing the assignment, disabling or archiving the Food,
or expiry of the direct-use lease removes it on the next projection refresh.
The index is derived and may be cached with a generation number; it is never a
second manually maintained list. It reuses the Runtime's pure Food-resolution
policy and preserves both requested and actual fallback routes instead of
copying assignment and visibility rules into a new SQL query. Model health can
change the actual route but cannot remove the requested Food from serving scope.

### 4.2 Role-sensitive core set

For every serving Food:

- `primary` is always core;
- configured `fallback` is core because it protects the serving route;
- `reasoning`, `vision` and `tool` are core only when the Food policy declares
  that role required or an authorized production request attempted that role
  inside the role-activity window, initially 30 days.

An unused optional role is checked on demand before or during its first real use
and does not receive periodic synthetic validation. A newly assigned Food enters
the serving projection immediately; it does not wait for historical logs.

The core projection deduplicates by exact `(connection_id, endpoint_model_id)`
while retaining every `(Food, role, capability_channel)` reason and the highest
criticality. Ten Foods using one endpoint therefore produce one general due
heartbeat, plus at most one due capability check for each distinct required
channel, not ten copies of either check.

Provider management may still show availability for all curated models, but
scheduled health work and homepage system health use only this role-sensitive
core set.

## 5. Evidence model and availability projection

Every model-call observation required for health contains the stable connection
ID, endpoint model ID, Food ID and semantic role when applicable, workload kind,
start/completion time, status, first-token latency, total latency, token counts,
typed error category and configuration/catalog fingerprint. It never contains
prompt or response text. Error messages and Provider response fragments are
sanitized before persistence so credentials, headers and user content cannot
enter reports.

Evidence sources are:

1. real production execution for the exact endpoint and capability channel;
2. explicit single, connection or full validation;
3. scheduled core-model heartbeat;
4. non-generation connectivity/authentication probe;
5. catalog metadata, which never proves current availability.

Projection applies gates in this order:

1. connection or model lifecycle exclusion;
2. a newer typed connection-wide blocker;
3. local runtime and installation gates when applicable;
4. exact model and capability-channel evidence with transient-failure hysteresis;
5. evidence freshness, otherwise `unknown`.

The model-facing states are mutually exclusive:

- `available`: fresh successful evidence and no newer blocker;
- `degraded`: temporary failure or mixed recent evidence while a usable path remains;
- `unavailable`: a deterministic blocker or a transient-failure threshold was reached;
- `unknown`: never checked, stale or insufficiently scoped evidence.

Provider internals preserve lifecycle, reachability and account state separately.
The Owner UI receives only `healthy`, `degraded`, `unavailable`, `unknown` or
`disabled`, plus a reason code and evidence time.

Initial freshness policy:

- reachability evidence: 5 minutes;
- model success from production or controlled validation: 24 hours;
- temporary failure: until its bounded retry time, normally 5–30 minutes;
- capability declaration: until the endpoint/profile fingerprint changes.

Typed account blockers are retried with bounded exponential backoff or an
explicit user action. Any later credible success at the same scope clears the
blocker. Credential, endpoint, model alias/digest or adapter-profile changes
invalidate only the evidence whose fingerprint they changed.

## 6. Cost-aware validation policy

| Trigger | Work | Additional generation cost |
| --- | --- | --- |
| Page or homepage read | Read projection immediately; refresh a stale reachability probe asynchronously | zero |
| Real production call | Append evidence and refresh the exact model/role projection | zero extra |
| New or materially edited connection | Refresh inventory, probe transport/auth and check one representative model | one tiny call |
| Serving core evidence older than 24 hours with no real traffic | Check a representative first, then only stale core endpoint models | minimum required |
| Normal **Validate** | Reuse fresh evidence and check stale visible curated models only | stale models only |
| Single-model check | Check that exact endpoint and requested capability channel | one targeted call |
| Explicit **Force full validation** | Check every enabled visible curated model, subject to early stop | user-authorized full cost |

Controlled text checks use no tools, no retry, a deterministic tiny prompt and
one to eight output tokens. Concurrency defaults to two per connection. Periodic
work never validates non-core models. Multiple callers share one in-flight check
per `(connection_id, model_id, capability_channel, fingerprint)`.

## 7. Failure scope and hysteresis

Provider adapters classify structured responses; substring matching is not
sufficient to fan a failure out across models.

| Evidence | Scope and effect |
| --- | --- |
| Invalid/revoked credential, expired subscription, typed billing or account quota blocker | Mark this connection unavailable immediately, stop the remaining batch, and let the connection blocker cover its models without creating fake per-model failures |
| Invalid base URL, incompatible protocol or a known Provider route returning a deterministic configuration error | Mark the connection configuration invalid immediately and require editing before scheduled retries |
| Model missing, retired or not entitled | Mark only that exact endpoint model unavailable and continue the batch |
| Rate limit | Degrade the returned scope until `retry_at`; never retire the model |
| Network error, timeout or 5xx | One event degrades only; three consecutive failures within ten minutes make the subject unavailable |
| Transient failures on two endpoint models, or one model plus a failed transport probe | Promote to a connection-level outage and stop the remaining batch |
| Context overflow, malformed request, safety refusal or caller-generated tool/schema error | Request-specific evidence; do not change general model health |
| Controlled feature probe returns unsupported | Mark only that capability channel unsupported; text availability is unchanged |

A success clears the matching transient streak. A Provider-product error never
blocks another connection of the same product. When a response cannot be safely
classified as account-wide, it defaults to the narrowest model/request scope.
Caller-specific malformed requests remain neutral, but the same adapter-generated
protocol error reproduced by a controlled minimal probe marks the affected
endpoint request profile or capability channel degraded.

## 8. Local Ollama projection

Local availability uses the same model states plus local gates:

```text
Ollama installed and healthy
+ exact model installed
+ model enabled and not hidden/retired
+ fresh successful endpoint evidence
= local model available
```

When Ollama is installed and its configured local connection is enabled, App
lifecycle may attempt one automatic start with backoff. It must not loop. A
failed attempt exposes **Start** or **Repair**. Installation and model downloads
always require an explicit user action.

The local model view contains installed, recommended and referenced models. A
running service with no model is degraded and offers **Download recommended
model**. An Ollama model digest or resolved `latest` target change invalidates
the corresponding capability and validation fingerprint.

## 9. Shared query API

In-process consumers use an App-owned query Port rather than calling Provider
adapters or HTTP internally:

- `get(reference)` reads one projection without network access;
- `get_many(references)` performs a bounded batch read;
- `ensure(reference, max_age, capability, probe_policy)` may share or start one
  targeted check only when the caller explicitly permits active probing.

The result contains exact reference, effective state, reason code, Provider
state, evidence source, `observed_at`, `expires_at`, endpoint capabilities and
serving/core roles. Owner HTTP endpoints mirror these queries for management UI.
An actual generation remains the final proof and always records its own result.
The normal production execution path performs a passive read and then uses its
real generation as evidence; it must not pay for a synthetic check immediately
before the same generation. Active `ensure` is permissioned, rate-limited and
subject to a connection cooldown, so callers cannot force repeated checks by
requesting an arbitrarily small `max_age`.

## 10. UI projections

The Provider management card keeps its large semantic background and one status
badge. It does not list models or draw one dot per model. Its summary is bounded,
for example:

```text
6/8 available · 2/2 core
```

The card's curated visible inventory determines its mutually exclusive color:

- green: every enabled in-scope model has fresh available evidence;
- amber: at least one is available but not all are available and fresh;
- red: zero models are available and there is a fresh deterministic model failure
  or connection blocker;
- grey: zero models are available but evidence is absent/stale, or the connection
  is disabled or archived.

Model colors appear only in the model view. Lifecycle tags such as hidden,
retired and source-missing are text labels, not competing health colors.

Homepage model health ignores unused Foods and non-core inventory:

- green: all required serving-core paths are available;
- amber: at least one serving primary path works, but another required primary,
  optional or fallback path is not available and fresh;
- red: at least one Food is serving and every serving primary path has a fresh
  deterministic unavailable result;
- grey: no Food is serving, no model is configured, or the serving primary
  evidence is still unknown.

The Provider card's core count is a count of distinct endpoint models. Homepage
health is stricter and counts serving role paths, so one endpoint used for both
text and vision can have one healthy path and one failed path. The homepage shows
only compact totals such as `Core paths 4/5 · Local 1/1 · Remote 3/4`. Color is
always accompanied by status text and an actionable reason.

## 11. Concurrency, retention and consistency

- Scheduler workers use a lease so only one process owns a due validation.
- On-demand checks use single-flight deduplication and bounded concurrency.
- Projection orders observations by completion time and stable sequence; it
  rejects evidence with an obsolete configuration fingerprint.
- Food assignment/lifecycle changes increment the ServingFoodIndex generation
  and cancel queued checks that are no longer core.
- Cleanup rechecks references transactionally immediately before deletion.
- Raw observations have a bounded retention period; long-term reliability uses
  rollups without content or secrets.

## 12. Adversarial review decisions

| Attack or failure mode | Design control |
| --- | --- |
| Every saved Food makes its models core | Only deployed Foods with a current route or short production-use lease enter `ServingFoodIndex` |
| The serving filter is reused for deletion and removes an inactive Food's model | Deletion uses the all-reference guard; serving scope controls only health and scheduling |
| A newly assigned Food is missed because it has no logs | Current assignment activates it immediately |
| Raw `main_food_id` ignores visibility or fallback semantics | `ServingFoodIndex` reuses the same pure resolver as Runtime |
| A real production route fails before a success decision is recorded | An authorized route attempt grants the short direct-use and role-activity lease |
| An assigned Food falls out of core after Runtime falls back | Serving scope preserves the requested route independently of current model health |
| Offline presence incorrectly removes protection | Presence is not a serving-scope input |
| Preview, benchmark or Developer Tool traffic creates fake core usage | `workload_kind` is mandatory and only production decisions grant the direct-use lease |
| A text call is used to claim vision/tool/reasoning support | Capability evidence is channel-specific |
| A canonical model's native capability leaks into a restricted Provider endpoint | Generic identities only group/display; final capability requires endpoint-specific authority |
| A tool or image payload is accepted but the feature is not actually used | Capability keeps its evidence level; only an authoritative declaration or controlled proof yields final support |
| A manual capability checkbox becomes trusted endpoint truth | Preserve it as a user declaration and require controlled evidence before a serving role relies on it |
| A bad prompt makes a healthy model red | Request-specific errors do not affect general health |
| One account failure disables every account of the same brand | Provider-wide blockers are scoped to one connection |
| A generic 403 is treated as billing failure | Only typed adapter classification may widen scope; unknown errors stay narrow |
| One timeout flips the service red | Transient thresholds and cross-model correlation are required |
| A stale validation overwrites newer evidence after config rotation | Fingerprints, completion time and stable sequence reject obsolete evidence |
| Several pages or services trigger duplicate paid checks | Read APIs are passive; active `ensure` is explicit and single-flight |
| A caller repeatedly sets `max_age=0` to force paid checks | Active probes require permission and enforce policy-owned cooldown and rate limits |
| Failed discovery deletes good models | Only consecutive successful authoritative refreshes can mark a model missing |
| An authoritative empty result is treated as failure and bundled models reappear as usable | Preserve the empty entitlement result; lower sources are labelled recommendations only |
| Page one succeeds but later discovery pagination fails | An incomplete pagination run is a failed refresh and cannot advance missing-model counters |
| A broad or compromised catalog pollutes the normal list | Product-specific authority, schema/version checks and curated display filtering |
| A custom endpoint targets metadata services or redirects a key | Outbound URL policy, explicit local exception and no cross-origin credential forwarding |
| An inventory response exhausts memory or is partially trusted | Byte/record limits reject the response and fall back without partial authority |
| Full validation wastes calls after an account blocker | Representative-first ordering and connection-level early stop |
| Unused optional Food roles are checked forever | Optional roles require declared necessity or recent production role use |
| Several serving Foods reference one endpoint and multiply paid heartbeats | Core projection deduplicates general checks by endpoint and capability checks by endpoint/channel while preserving all usage reasons |
| One endpoint serves text and vision and a text heartbeat hides broken vision | Homepage health retains role paths and channel-specific evidence after endpoint deduplication |
| Automatic Ollama recovery loops or downloads large files | One backoff-controlled start; install and pull remain explicit |
| Multiple application processes duplicate schedules | Scheduler lease plus idempotent run identity |
| Report growth or private content becomes a risk | Bounded retention, aggregate rollups and no prompt/response storage |

## 13. Implementation entry gates and acceptance

Before implementation, the bilingual behavior contract must be revised and an
exact conformance entry must distinguish current support from this target. The
implementation should then proceed in independently verifiable slices:

1. endpoint-model metadata and typed request profiles;
2. stable production observations and `ServingFoodIndex`;
3. availability projection and passive/active query Port;
4. cost-aware scheduling, early stop and cleanup;
5. Provider, homepage and Ollama UI projections.

Acceptance must prove at least:

- an enabled but unassigned and unused Food causes no scheduled validation and
  does not affect homepage health;
- assigning a Food immediately activates its primary/fallback core models, and
  removing the assignment removes them after any legitimate lease expires;
- an assigned Food remains core while unavailable so later evidence can recover
  it, even when current execution uses Emergency;
- preview/test traffic never activates core scope;
- a connection-wide hard blocker stops the batch and is reused by its models,
  while a model-specific failure does not poison sibling models;
- a broad platform `/models` list cannot replace a product-specific curated list;
- passive availability reads perform no external call, while concurrent active
  checks collapse to one request;
- local health requires both a healthy Ollama runtime and the exact installed model.
