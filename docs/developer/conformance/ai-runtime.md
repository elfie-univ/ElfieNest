# AI Runtime conformance

> This is a temporary implementation gap register for the current
> `ai_runtime/` migration package and the
> [model, Food and tool behavior contract](../contracts/ai-runtime). It records
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
| AR-002 | P0 | in progress | New connection and model validations do not feed the model-evidence query consumed by food generation. | Provider inventory and the latest SQLite observations compose one derived evidence projection. Food generation sees it without restart, copied YAML or a second configuration source. |
| AR-003 | P1 | open | Food generation can use stale or invented model references because references receive syntax-only validation. | Every saved role resolves to an enabled connection and a present, visible endpoint model. Generation leaves a role unconfigured when no valid candidate exists. |
| AR-004 | P1 | closed | The food domain now uses permanent Emergency and Common rows plus administrator-created packages. | A new home initializes Emergency first and Common second. Both system packages remain visible and undeletable. Additional packages are ordinary user-created records, not compiled kinds. |
| AR-005 | P1 | closed | Food lifecycle now has distinct enabled, archived and guarded deletion semantics. | Enable/disable, archive/restore and delete are separate commands. System foods cannot archive/delete. Custom delete requires archived and unreferenced state. |
| AR-006 | P1 | open | Main-food and emergency resolution falls through legacy default/allowed-food behavior and has no explicit `no_available_food` result. | Resolution follows assigned primary, then global emergency, then a typed unavailable result. It never silently selects an arbitrary first or legacy food. |
| AR-007 | P1 | closed | Food visibility and the Elfie editor use one Main-food selection backed by the package visibility field. | Emergency and Common are visible to every user; only custom packages have user grants; the Elfie page has one Main-food field whose options are all visible, enabled, healthy packages except Emergency. |
| AR-008 | P1 | closed | The package catalog and visibility state are now a single `nest.db.food_packages` fact source; legacy per-Elfie `food_policy.yaml` reads and fixed-food routes are removed. | The database-backed package catalog plus Nest DB assignments are the only facts. Missing legacy files produce no fallback reads or writes. |
| AR-009 | P1 | open | Brain memory calls still request `coarse` and `focus`; structured cortex generation always uses the primary role. | Brain requests semantic roles such as `primary` or `reasoning`; the injected `FoodPort` returns the Elfie's effective package directly; structured generation can use the selected role without an App Orchestration proxy. |
| AR-010 | P1 | open | Tool allow-lists reach the Runtime request but the actual structured cortex path does not run the tool loop. | An end-to-end test proves an Elfie request can invoke an allowed safe tool, receive a bounded result and continue generation. |
| AR-011 | P1 | open | Tool results and local file reads are not bounded before model reinjection. | Per-tool byte/item limits and a final result envelope trim output, preserve truncation metadata and prevent unbounded context growth. |
| AR-012 | P1 | open | Model refresh replaces manual records and model deletion is not guarded by food references. | Discovery merges by endpoint model ID, preserves manual records, marks disappeared discovered records unavailable, and refuses destructive removal while referenced. |
| AR-013 | P1 | in progress | Legacy Provider CRUD, legacy routing and `cheap/deep/multimodal` defaults coexist with connection-based routing and food packages. | One connection API and one food resolver remain. Legacy writers and runtime routing sources are removed rather than kept as hidden fallbacks. |
| AR-014 | P1 | in progress | Reports are split across YAML files and legacy paths instead of the dedicated report database; runtime receipt paths also differ from the contract. | All observations append to `reports/ai-runtime.sqlite`; current/as-of/run queries pass; exports are write-only; architecture tests reject legacy fact paths and root-level receipts. |
| AR-015 | P2 | open | Provider UI differs from the agreed configured-card actions and unified add flow; bundled brand assets are missing or served from the wrong URL. | Cards expose Models, Validate, Edit and More. More owns lifecycle actions. One searchable chooser includes featured, categorized and custom products. Local assets load successfully. |
| AR-016 | P2 | open | Provider and model catalogs are incomplete and stale, and discovery does not implement the official, ElfieNest remote, bundled local, then manual source chain. | Catalog entries identify real products and authentication modes; discovery follows the four-level precedence, preserves manual records and requires validation before food eligibility. |
| AR-017 | P2 | open | Tool configuration advertises unavailable code and shared skill-evolution capabilities as enabled. | Phase-one defaults expose only implemented safe tools. Deferred tools are disabled and cannot be advertised to a model. Personal skills remain under the Elfie workspace. |
| AR-018 | P1 | in progress | A clean temporary `ELFIE_HOME` passes the focused semantic and architecture acceptance checks, and browser interaction covers Provider and food flows. The whole-repository Python gate is still failing, and screenshot-capable desktop/mobile visual review has not been completed. | A clean temporary `ELFIE_HOME` passes all 13 contract steps, including discovery precedence, comparison snapshots, lifecycle guards and `no_available_food`; Provider, matrix, food and Elfie browser acceptance has durable visual evidence; and the full quality gate passes. |
| AR-019 | P1 | open | The cross-connection model matrix does not use report runs or provide a Validate-all workflow. | Bounded Validate-all writes one complete run; single validation appends one subject observation; current, as-of and run-specific matrix queries preserve measurement times. |
| AR-020 | P1 | closed | The food UI and planner implement permanent row ordering, connection-scoped generation, fresh-validation eligibility, the five-role table and dynamic package health. | Browser and API tests prove Emergency/Common ordering, scoped local-first generation, diff/manual/save flow, Primary/Reasoning/Vision/Tool/Fallback assignments and evidence-derived health, without food-level model capability fields. |

## Current implementation map

The version-1.3 behavior contract preserves current accepted semantics while
the system contract decomposes the package. The current code differs in five
connected areas:

| Area | Current implementation | Contract difference | Gap IDs |
| --- | --- | --- | --- |
| Persistence and reports | `providers.yaml` has incompatible version-1 and version-2 writers. Provider/model results are YAML `latest` plus `history`; model evidence is another YAML file and older root report paths still exist. | Each configuration file needs one typed owner. Reports must append to `reports/ai-runtime.sqlite` and expose current, as-of and run projections. | AR-001, AR-002, AR-008, AR-013, AR-014 |
| Provider and model inventory | Connection IDs and multiple accounts exist, but source values remain `discovered/manual/provider_catalog`; refresh can replace manual models; official/remote/bundled/manual precedence and a run-based all-model report do not exist. | One four-level discovery chain, non-destructive merge, validated food eligibility and a complete/partial cross-connection matrix are required. | AR-003, AR-012, AR-015, AR-016, AR-019 |
| Food domain and Owner UI | `nest.db.food_packages` contains permanent system rows and custom packages with five simple role-to-model assignments, enabled/archive state, guarded deletion and evidence-derived health. | Permanent Emergency/Common rows plus custom packages, simple role-to-model assignments, fresh-evidence filtering, scoped generation and evidence-derived health are implemented. | AR-004, AR-005, AR-020 |
| Access and Elfie routing | Food visibility is a flat `global`/`users` field in the package row; legacy package YAML reads are gone. Brain role-routing work remains tracked separately. | The Elfie page has one Main-food field from the user's eligible set; Runtime resolves package role, internal fallback, Emergency, then `no_available_food`. | AR-006, AR-007, AR-008, AR-009 |
| Tools and acceptance | Ordinary food execution has a tool loop, but structured cortex generation bypasses it. File/search results are unbounded; code and skill mutation are advertised despite deferred safety. No clean-home contract test exists. | Safe tools must run in the real cortex path with Elfie-workspace isolation and bounded results; deferred tools stay disabled; all 13 acceptance steps must pass. | AR-010, AR-011, AR-017, AR-018 |

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
  only role data is Primary, Reasoning, Vision, Tool and ordered Fallback model
  references;
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
- resolve selected package, optional role-to-Primary, ordered package Fallback,
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
- current code and both language mirrors agree with behavior contract 1.3;
- ownership and migration steps do not recreate a target `ai_runtime/` or
  `infrastructure/ai_runtime/` module.

Closes: AR-018 and every remaining open row.
