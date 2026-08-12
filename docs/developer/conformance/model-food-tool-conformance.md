# Model, Food and tool conformance

> This is a temporary implementation gap register for the decomposed model,
> Food and tool implementation and the
> [model, Food and tool behavior contract](../contracts/model-food-tool-behavior). It records
> current non-conformance; target ownership is defined only by the
> [system architecture contract](../contracts/system).

## Status rules

- `open`: the contract is not implemented or the current implementation is unsafe.
- `in progress`: implementation exists locally but all acceptance checks do not pass.
- `closed`: code, focused tests, architecture tests and the end-to-end contract pass.
- A compatibility path is not a valid fix unless the design contract explicitly
  requires that compatibility.

## Blocking gaps

| ID | Severity | Status | Gap | Acceptance |
| --- | --- | --- | --- | --- |
| AR-001 | P0 | closed | `configs/providers.yaml` has both a version-2 connection writer and a legacy version-1 bundle writer. Writing unrelated system or tool settings can erase all connection instances. | One typed owner and one schema write the file. System and tool writes cannot change Provider connection bytes. A regression test reproduces and prevents the loss. |
| AR-002 | P0 | closed | Provider and model validation now feed the shared model-evidence projection consumed by Food. | Provider inventory and the latest SQLite observations compose one derived evidence projection. Food generation sees it without restart, copied YAML or a second configuration source. |
| AR-003 | P1 | closed | Food writes now require fresh evidence and a live, visible connection/model reference. | Every saved role resolves to an enabled connection and a present, visible endpoint model. Generation leaves a role unconfigured when no valid candidate exists. |
| AR-004 | P1 | closed | The food domain now uses permanent Emergency and Common rows plus administrator-created packages. | A new home initializes Emergency first and Common second. Both system packages remain visible and undeletable. Additional packages are ordinary user-created records, not compiled kinds. |
| AR-005 | P1 | closed | Food lifecycle now has distinct enabled, archived and guarded deletion semantics. | Enable/disable, archive/restore and delete are separate commands. System foods cannot archive/delete. Custom delete requires archived and unreferenced state. |
| AR-006 | P1 | closed | Main-food resolution now uses the assigned/default package, one global emergency package and an explicit `no_available_food` result. | Resolution follows assigned primary, then global emergency, then a typed unavailable result. It never silently selects an arbitrary first or legacy food. |
| AR-007 | P1 | closed | Food visibility and the Elfie editor use one Main-food selection backed by the package visibility field. | Emergency and Common are visible to every user; only custom packages have user grants; the Elfie page has one Main-food field whose options are all visible, enabled, healthy packages except Emergency. |
| AR-008 | P1 | closed | The package catalog and visibility state are now a single `nest.db.food_packages` fact source; legacy per-Elfie `food_policy.yaml` reads and fixed-food routes are removed. | The database-backed package catalog plus Nest DB assignments are the only facts. Missing legacy files produce no fallback reads or writes. |
| AR-009 | P1 | closed | Brain memory and structured generation now request semantic Food roles through the injected FoodPort/runtime boundary. | Brain requests semantic roles such as `primary` or `reasoning`; the injected `FoodPort` returns the Elfie's effective package directly; structured generation can use the selected role without an App Orchestration proxy. |
| AR-010 | P1 | closed | The ordinary and structured Runtime paths now share the injected safe ToolPort loop. | The model/Food/Tool end-to-end contract proves an Elfie request can invoke an allowed safe tool, receive a bounded result and continue generation. |
| AR-011 | P1 | closed | Safe tool results are clipped before model reinjection and record truncation evidence. | Per-tool byte/item limits and a final result envelope trim output, preserve truncation metadata and prevent unbounded context growth. |
| AR-012 | P1 | closed | Refresh now merges by endpoint model ID, preserves manual records and marks disappeared discovered records unavailable; deletion checks Food references. | Discovery merges by endpoint model ID, preserves manual records, marks disappeared discovered records unavailable, and refuses destructive removal while referenced. |
| AR-013 | P1 | closed | Provider management and runtime routing now use the connection-backed models and semantic Food resolver; retired writers and routing fields are absent. | One connection API and one food resolver remain. Legacy writers and runtime routing sources are removed rather than kept as hidden fallbacks. |
| AR-014 | P1 | closed | Model, Food and tool observations now use the dedicated append-only report database and typed storage Ports. | All observations append to `reports/ai-runtime.sqlite`; current/as-of/run queries pass; exports are write-only; architecture tests reject legacy fact paths and root-level receipts. |
| AR-015 | P2 | closed | Provider cards, lifecycle actions and the unified add flow now match the agreed UI contract; bundled brand assets resolve from the local public asset tree. | Cards expose Models, Validate, Edit and More. More owns lifecycle actions. One searchable chooser includes featured, categorized and custom products. Local assets load successfully. |
| AR-016 | P2 | closed | Provider/model catalog discovery now implements the official, ElfieNest remote, bundled local, then manual source chain without destructive refresh. | Catalog entries identify real products and authentication modes; discovery follows the four-level precedence, preserves manual records and requires validation before food eligibility. |
| AR-017 | P2 | closed | Tool advertising is limited to the implemented safe search and workspace-read capabilities; deferred code and Skill mutation are absent. | Phase-one defaults expose only implemented safe tools. Deferred tools and Skill mutation are disabled and cannot be advertised to a model; mutable or durable personal Skill state has no active fact source. |
| AR-018 | P1 | in progress | The clean-home semantic, architecture, full backend/frontend and quality gates now pass; the remaining acceptance artifact is durable browser visual evidence for Provider, matrix, food and Elfie flows. | A clean temporary `ELFIE_HOME` passes all 13 contract steps, including discovery precedence, comparison snapshots, lifecycle guards and `no_available_food`; Provider, matrix, food and Elfie browser acceptance has durable visual evidence; and the full quality gate passes. |
| AR-019 | P1 | closed | Validate-all and matrix queries now use append-only report runs with current, as-of and run-specific projections. | Bounded Validate-all writes one complete run; single validation appends one subject observation; current, as-of and run-specific matrix queries preserve measurement times. |
| AR-020 | P1 | closed | The food UI and planner implement permanent row ordering, connection-scoped generation, fresh-validation eligibility, the five-role table and dynamic package health. | Browser and API tests prove Emergency/Common ordering, scoped local-first generation, diff/manual/save flow, Primary/Reasoning/Vision/Tool/Fallback assignments and evidence-derived health, without food-level model capability fields. |

## Current implementation map

The version-1.5 behavior contract preserves current accepted semantics while
the system contract decomposes the package. The current code differs in five
connected areas:

| Area | Current implementation | Contract difference | Gap IDs |
| --- | --- | --- | --- |
| Persistence and reports | `providers.yaml` has one connection-backed writer. Provider/model results and Food evidence are projected from the append-only report database through typed storage Ports. | Each configuration file needs one typed owner. Reports must append to `reports/ai-runtime.sqlite` and expose current, as-of and run projections. | AR-001, AR-008 |
| Provider and model inventory | Connection IDs and multiple accounts now use non-destructive refresh, protected model deletion, report-backed validation/matrix projections, the four-level discovery chain and the configured-card/add-flow UI. | One four-level discovery chain, non-destructive merge, validated food eligibility and a complete/partial cross-connection matrix are required. | None |
| Food domain and Owner UI | `nest.db.food_packages` contains permanent system rows and custom packages with five simple role-to-model assignments, enabled/archive state, guarded deletion and evidence-derived health. | Permanent Emergency/Common rows plus custom packages, simple role-to-model assignments, fresh-evidence filtering, scoped generation and evidence-derived health are implemented. | AR-004, AR-005, AR-020 |
| Access and Elfie routing | Food visibility is a flat `global`/`users` field in the package row; legacy package YAML reads and coarse/focus routing are gone. | The Elfie page has one Main-food field from the user's eligible set; the Elfie resolver uses the package role, one optional fallback, Emergency, then `no_available_food`. | AR-007, AR-008 |
| Tools and acceptance | Ordinary and structured Food execution share the injected safe-tool loop; workspace reads are bounded and truncation is recorded. Deferred code and skill mutation are disabled. | Safe tools must run in the real cortex path with Elfie-workspace isolation and bounded results; deferred tools stay disabled; all 13 acceptance steps must pass. | AR-018 |

## Migration groups

These groups express dependency order, not permission to land a partially
working phase. Every merged migration slice must keep the product runnable and
must satisfy its focused gate before the next slice depends on it.

Implementation follows "establish the new fact source, switch every caller,
then remove the old implementation." New and old code may coexist while one
unmerged slice switches callers, but one fact has only one active writer. A
legacy reader retained across merged slices requires an explicit gap row and
deletion gate, creates no new data, and is removed as soon as its replacement
passes acceptance. It cannot become a permanent compatibility layer.

### Phase 1: single-source storage and report database

Scope:

- make version-2 Provider connections the only `providers.yaml` schema, switch
  callers first, then remove the legacy bundle writer; remove legacy Provider
  fact routes only after every caller moves;
- add `reports/ai-runtime.sqlite`, explicit schema initialization, WAL, report
  runs, immutable observations and current/as-of/by-run queries;
- replace YAML Provider/model validation writers and `model_evidence.yaml` with
  the report repository and derived evidence query;
- align `runtime/runtime.json`, locks and path helpers with the contract;
- remove legacy root report fact reads; prohibit new per-Elfie
  `food_policy.yaml` writes in this phase, while retaining legacy reads only
  until the phase-four replacement passes acceptance.

Gate:

- changing Runtime or Tool settings leaves Provider and food files byte-for-byte
  unchanged;
- single, partial batch, complete batch and historical as-of report tests pass;
- architecture tests reject removed writers, legacy report fact paths and every
  new `food_policy.yaml` write.

Closes or advances: AR-001, AR-002, AR-008, AR-013, AR-014.

### Phase 2: Provider inventory, discovery and model matrix

Scope:

- implement `official`, optional `remote_catalog`, `bundled_catalog`, then
  `manual` discovery precedence with non-destructive merge;
- keep the remote catalog behind a configured client boundary until a server is
  available, while making official and bundled paths functional now;
- add connection enabled/archive/restore/guarded-delete and model
  hidden/retired/reference protection;
- make validation write report runs and make only fresh passed models food
  eligible;
- finish the configured-card actions, unified searchable product chooser,
  official local assets, connection model view and Validate-all matrix.

Gate:

- two accounts of one product coexist with immutable readable IDs;
- each discovery fallback is tested and manual models survive refresh;
- single validation changes one matrix subject and Validate-all produces one
  complete run;
- browser tests verify `[Models] [Validate] [Edit] [More]` and the unified add
  flow.

Closes or advances: AR-003, AR-012, AR-015, AR-016, AR-019.

### Phase 3: food domain, lifecycle and Owner workflow

Scope:

- replace fixed food kinds and `ExecutionProfile` with stable packages whose
  only role data is Primary, Reasoning, Vision, Tool and exactly one optional
  Fallback model reference;
- initialize permanent Emergency first and Common second; add enabled state,
  custom archive/restore and guarded deletion;
- derive locality and package health from Provider inventory plus SQLite
  observations instead of stored status;
- implement one/many/all-connection generation scope, Emergency local-first
  policy, fresh-validation filtering, diff preview, manual role adjustment and
  explicit save;
- make Emergency/Common globally visible and user grants apply only to custom
  packages.

Gate:

- a clean home contains only the two permanent system rows;
- `nest.db.food_packages` contains no model capability, context, output or
  tool-permission facts;
- unavailable models cannot be selected or generated;
- browser tests cover row order, scoped generation, five role rows, lifecycle,
  visibility and dynamic health.

Closes or advances: AR-004, AR-005, AR-007, AR-020.

### Phase 4: Elfie routing and safe tool execution

Scope:

- expose one Main-food field whose options are the user's visible, enabled,
  healthy packages except Emergency;
- keep API, CLI, Owner projections and Runtime callers on the database-backed
  package repository; legacy allowed/fallback fields and all `food_policy.yaml`
  reads are removed;
- replace `coarse/focus` calls with semantic Primary/Reasoning/Vision/Tool role
  requests;
- resolve selected package, optional role-to-Primary, one optional package Fallback,
  global Emergency and typed `no_available_food`;
- run safe search and read-only files in both ordinary and structured cortex
  paths, bound to the Elfie workspace with timeout/item/byte clipping;
- disable code execution and skill mutation until their later isolation
  contract exists.

Gate:

- main-food changes take effect without rebuilding an Elfie;
- structured and ordinary generation share one role/fallback resolver;
- end-to-end tests prove safe tool use and bounded reinjection;
- unavailable primary and Emergency states return the exact contract result.

Closes or advances: AR-006, AR-008, AR-009, AR-010, AR-011, AR-017.

### Phase 5: contract acceptance and cleanup

Scope:

- implement the clean temporary `ELFIE_HOME` 13-step acceptance scenario;
- add Browser interaction checks for Provider, matrix, food and Elfie flows;
- remove obsolete tests that assert fixed foods or legacy UI and replace them
  with contract tests;
- run focused suites, architecture tests, full frontend/backend gates and
  sensitive-data scanning;
- close each conformance row only with its acceptance evidence.

Gate:

- all 13 contract steps pass without legacy files or fallback readers;
- the conformance register contains no open item;
- current code and both language mirrors agree with behavior contract 1.5;
- ownership and migration steps do not recreate a target `ai_runtime/` or
  `infrastructure/ai_runtime/` module.

Closes: AR-018 and every remaining open row.
