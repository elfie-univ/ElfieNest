# Elfie Memory conformance

> Status: Memory implementation and the reviewed hardening pass are complete on this branch; deterministic and real Ark gates passed, and the owner approved the anonymized experience samples. Focused verification for the hardening pass is green; production data cutover remains a separate operation under MEM-007; OPT-003/004 remain deferred<br>
> Baseline: 2026-08-27<br>
> Target: [Elfie Memory design](../designs/elfie-memory-architecture)

This is a temporary migration register. It records the current gaps against the
Memory design and the evidence required to close them. It does not redefine the
Memory model, authorize schema changes or describe an implementation diary.

## Implementation register

| ID | Severity | Status | Current deviation | Target and closure gate | Evidence / references | Residuals |
| --- | --- | --- | --- | --- | --- | --- |
| MEM-001 | P0 | closed | The old entity/subtype and embedded-edge layout has been replaced for the target Adapter by the reviewed Episode, node, assertion and evidence tables. | Target tables, constraints, ownership and rebuildable lexical projections are implemented without a second edge authority. | target=design §9.1–9.2; inventory=`infrastructure/persistence/memory/{schema.py,sqlite_memory_store.py,node_store.py,sqlite_episode_store.py,sqlite_graph_store.py,sqlite_retrieval_store.py}`; references=persistence scan; verification=target schema/round-trip/reopen tests, 299 affected Memory/Brain/Genesis/adoption tests, 21 architecture tests, Ruff, pycompile and `git diff --check`; residuals=an existing live legacy file still requires the explicit importer/cutover below. | None for the development target. |
| MEM-002 | P0 | closed | Closed Episodes now have complete content, source IDs, full-source hashes, idempotency and restart-safe writes; completed interaction candidates and Genesis seeds use the source-first path. Unknown time, occurrence precision, attribution, privacy and projection provenance are explicit. | One validated Episode is the detailed historical source; Memory does not group raw turns. | target=design §3 and §9.1/§9.4; inventory=`sqlite_episode_store.py`, `memory_system.py`, `genesis/initializer.py`; references=Episode and E1 vertical-slice tests; verification=duplicate-submit, content-hash, unknown-time, low-intensity candidate, Genesis source-chain and reopen tests; residuals=upstream event boundary remains the owner of event closure; legacy `record_episode` is compatibility-only. | None for the target path. |
| MEM-003 | P0 | closed | Nodes, aliases, descriptions, mentions, typed-literal qualified assertions, evidence and many-to-many assertion/evidence links are durable; identity merges retarget history and preserve conflicts. | Independent importance, confidence, polarity, viewpoint, time, typed values and contradiction are retained without blind triple overwrite. | target=design §4 and §9.1–9.3; inventory=`sqlite_graph_store.py`, `schema.py`, `predicates.py`; references=source-first graph tests; verification=alias/cross-Episode resolution, merge retargeting, typed source assertion, predicate rejection, conflict/evidence and projection-diagnostic tests; residuals=historical versions already overwritten by the old database cannot be reconstructed automatically. | Existing legacy data may have unrecoverable conflicting versions. |
| MEM-004 | P0 | closed | Bounded workers claim Episodes, validate grounded model proposals or use the conservative deterministic extractor, then commit a retryable sourced projection in one transaction. A versioned predicate registry, source-hash/revision check and bounded rejection diagnostics are enforced. | Canonical identity, evidence attachment, compatible merge and conflict retention are deterministic; source Episodes survive failures. | target=design §5 and §9.3–9.4; inventory=`elfie/brain/memory/consolidation.py`, `predicates.py`, `sqlite_graph_store.py`; references=source-first worker tests; verification=model grounding, global semantic IDs, retry/lease recovery, predicate/version rejection, projection revision and source-preservation tests; residuals=provider and scheduling policy remain injected/operational choices. | No unbounded model call occurs inside a write transaction. |
| MEM-005 | P0 | closed | `RecallRequest` now performs deterministic Basic/Text candidate search followed by bounded Local Graph traversal, source lookup, relation/time/facet/privacy filters and declared limits. Active, superseded and conflicting claims retain status and evidence. | Text covers rare/unresolved wording; graph traversal covers explicit relationships; sources and conflicts remain visible. | target=design §6 and §9.4; inventory=`sqlite_retrieval_store.py`, `node_store.py`, `sqlite_graph_store.py`; references=source-first retrieval tests; verification=rare-term/alias, person-network, knowledge-object, seed, time-window, positive AND/OR facets, unknown-time, privacy, hop/limit and representative latency checks; residuals=Global/community and vector retrieval remain later projections. | Current lexical projection is intentionally simpler than FTS5 and is rebuildable. |
| MEM-006 | P0 | closed | `RecallBundle` and its deterministic renderer are implemented; the reasoning Memory reader consumes independent typed items with real source IDs. | Upper layers receive bounded nodes, assertions, paths, Episodes, evidence and conflicts through the semantic contract, not raw SQL. | target=design §6 and §9.5; inventory=`memory_records.py`, `recall_renderer.py`, `reasoning/memory_context.py`; references=reasoning and renderer tests; verification=stable rendering, hard character cap, provenance and no synthetic source for typed nodes; residuals=final natural-language narration remains Reasoning's responsibility. | None for the Memory boundary. |
| MEM-007 | P0 | closed (development) | A fresh-target importer, source read-only guard, count/digest/hash reconciliation, lease recovery and retention operations are implemented. Source-less legacy edges and unverified links are skipped with deterministic warnings instead of becoming active facts. | Import is Episodes-first, auditable and reversible; old data is not mutated and no long-term dual write is introduced. | target=design §9.6; inventory=`migration.py`, `sqlite_memory_store.py`; references=ADR-0018 and persistence rules; verification=legacy import, namespaced ID mapping, eligible Episode hash match, source-less edge skip, evidence mapping, reopen and forget/archive tests; residuals=production data migration/cutover was intentionally not run and requires a separate explicit approval. | No live user database was touched. |
| MEM-008 | P0 | closed | Deterministic structural gates, the complete real Ark gate and the owner experience review are complete for Stage 1. | A replayable redacted report must show deterministic gates, source grounding, relationship/conflict behavior, restart and latency before Stage 1 promotion. | target=design §9.7 and `docs/.internal/elfie-stage1-memory-backed-chat-execution-plan.md`; inventory=`devtools/evals/stage1_chat_ark.py`, scenario set and focused tests; references=`build/evaluations/stage1-chat/e1-ark-real-final/report.json`; verification=final-candidate report records 86 deterministic E1 tests, 33/33 repeated machine scenarios, 33 structured Ark judge calls with every applicable dimension worst score at least 4, persistence scan exit 0, and the owner-approved anonymized samples; one transient provider empty response was recovered by the existing bounded failure path; residuals=production-data migration/cutover remains a separately approved MEM-007 operation; OPT-003/004 remain deferred. | Ark authentication and structured judge completion passed; no secret was written to the report. |

## Post-baseline optimization register

The following records the current development priorities after the baseline; it does not rewrite the closed or deferred
status of `MEM-001`–`MEM-008`.

| ID | Priority | Status | Current gap | Next acceptance gate | Evidence / references |
| --- | --- | --- | --- | --- | --- |
| OPT-001 | P0 | closed | The bounded slice compiles the frozen E1 fixture through typed Elfaria World Canon/Genesis, removes duplicated identity facts from the reasoning prompt, verifies publish-failure cleanup, and passes the deterministic E2/E3 gates. | No further OPT-001 implementation gate. | target=OPT-001; inventory=`config/world/elfaria.yaml`, typed Genesis and adoption modules; references=OPT-001 execution brief and E1/E2/E3 scenario set; verification=typed fixture, affected Memory/Reasoning tests, deterministic E2/E3, Ruff and persistence scan passed; residuals=production backfill intentionally not run. |
| OPT-002 | P0 | closed | WorkingContext closes bounded topic Episodes, captures source records before inference, extracts explicitly attributed owner/person facts, preserves aliases and supports explicit correction chains. | The deterministic continuous-learning regression passes all eight source-first scenarios. | target=OPT-002; inventory=`conversation_context.py`, `settlement.py`, `consolidation.py` and SQLite Memory adapter; references=OPT-002 execution brief and Memory design §§9.4–9.5; verification=eight continuous-learning scenarios, affected suite, Ruff and persistence scan passed; residuals=production cutover remains separately governed by MEM-007. |
| OPT-003 | P1 | deferred | The bounded Lifecycle/Memory Maintenance implementation is present, but long-run compaction, forgetting, archiving, growth and latency still lack endurance validation. | Establish bounded-growth, retry/recovery and lifecycle-p95 evaluation before enabling unattended long-running maintenance. | target=design §6 and §9.2/§9.6; inventory=`sqlite_lifecycle_store.py`, `memory_system.py`; references=Memory contract hardening tests; verification=bounded maintenance, source-protection and idempotent decay tests pass; residuals=endurance/10k-Episode capacity evidence is still required. |
| OPT-004 | P1/P2 | deferred | Real Nest observation, activity and multi-Elfie interaction are outside the current chat loop. | After Stage 2 world integration, validate embodied memory and world-event provenance. | — |

OPT-001 and OPT-002 may be developed in parallel, using separate feature branches and independent evaluations; run a
combined regression after both pass. Do not start OPT-003 or OPT-004 before then.

OPT-001 first-slice evidence (2026-08-28): target=OPT-001 plan §§3–5; inventory=`config/world/elfaria.yaml`,
configuration registry/schema, `elfie/genesis/{contracts.py,initializer.py}`, and
`infrastructure/persistence/elfie_workspace/adoption_profiles.py`; references=Elfaria World Canon/species cards and
typed Genesis tests; verification=the typed fixture compiler test, 15 focused adoption/evaluation tests, the
affected Memory/Reasoning suite, Ruff, `git diff --check`, and the existing persistence scan, with the Canon
containing 42 facts and each published-species adoption selecting 40 eligible knowledge seeds, plus 5 Episodes and
13 private relationship objects; materialization cleanup is now covered by an injected publish-failure test and the
reasoning prompt no longer repeats Selfhood identity facts already supplied by Profile/Canon. The typed `stage1-e1.v2`
fixture passed the deterministic gate and a real Ark single-repetition run (26 provider calls; machine and judge gates
passed) in `/private/tmp/elfie-e1-real-20260828-final2/report.md`. The deterministic E2/E3 gate passed 2 published
species, 96 eligible knowledge queries per species, 240 unknown-boundary queries, and 24 biography combinations
(4 life stages × 3 seeds per species) in `build/evaluations/stage1-chat/opt001-e2e3-final/report.json`. The owner
approved the Stage 1 experience; no production backfill was performed; OPT-002 is closed and OPT-003/004 remain deferred.

OPT-002 implementation and evaluation evidence (2026-08-28): target=continuous-learning source-first flow and WorkingContext boundary; inventory=`elfie/brain/reasoning/conversation_context.py`, `coordinator.py`, `settlement.py`, `elfie/brain/memory/consolidation.py`, `infrastructure/persistence/memory/{schema.py,sqlite_memory_store.py,sqlite_graph_store.py}`; references=OPT-002 execution brief §3–§7 and Memory design §9.4–§9.5; verification=`devtools/evals/opt002_continuous_learning.py` and `test/devtools/evals/test_opt002_continuous_learning.py` pass all eight scenarios: episode boundaries, entities/aliases/ambiguity, owner correction/restart, conflicts, idempotent replay, failure retry, delivery-failure boundary and Elfie isolation; the combined affected suite is 36/36, Ruff and persistence scan exit 0, report=`build/evaluations/stage1-chat/opt002-final/report.json`; production cutover remains under MEM-007; OPT-003/OPT-004 are intentionally deferred.

## Post-acceptance follow-ups

1. Approve and execute any production-data cutover separately if an existing user database must be switched; development migration is complete.
2. After the Stage 1 product window, establish the bounded-growth and recoverable-lifecycle evaluation for OPT-003.
3. After Stage 2 world integration, establish the embodied-memory evaluation for OPT-004.

The required read-only persistence inventory is:

```text
uv run --no-sync python scripts/governance/persistence/scan.py --project-root . --check
```

It must be rerun after schema changes. A row closes only when its target,
inventory, references, verification and residuals are recorded. The reviewed Memory hardening pass is closed for the
development target; production cutover and long-run OPT-003 capacity evidence remain separately governed.

**Closure state:** ready
