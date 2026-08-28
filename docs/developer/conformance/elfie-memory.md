# Elfie Memory conformance

> Status: implementation complete on the current branch; the real Ark evaluation passed its machine and soft gates, while Stage 1 promotion remains gated by owner review and production cutover<br>
> Baseline: 2026-08-27<br>
> Target: [Elfie Memory design](../designs/elfie-memory-architecture)

This is a temporary migration register. It records the current gaps against the
Memory design and the evidence required to close them. It does not redefine the
Memory model, authorize schema changes or describe an implementation diary.

## Implementation register

| ID | Severity | Status | Current deviation | Target and closure gate | Evidence / references | Residuals |
| --- | --- | --- | --- | --- | --- | --- |
| MEM-001 | P0 | closed | The old entity/subtype and embedded-edge layout has been replaced for the target Adapter by the reviewed Episode, node, assertion and evidence tables. | Target tables, constraints, ownership and rebuildable lexical projections are implemented without a second edge authority. | target=design §9.1–9.2; inventory=`infrastructure/persistence/memory/schema.py`, `node_store.py`, `edge_store.py`; references=persistence scan; verification=target schema/round-trip/reopen tests and 332 combined affected tests; residuals=an existing live legacy file still requires the explicit importer/cutover below. | None for the development target. |
| MEM-002 | P0 | closed | Closed Episodes now have complete content, source IDs, hashes, idempotency and restart-safe writes; completed interaction candidates and Genesis seeds use the source-first path. | One validated Episode is the detailed historical source; Memory does not group raw turns. | target=design §3 and §9.4; inventory=`sqlite_episode_store.py`, `memory_system.py`, `genesis/initializer.py`; references=Episode and E1 vertical-slice tests; verification=duplicate-submit, content-hash, low-intensity candidate, Genesis source-chain and reopen tests; residuals=upstream event boundary remains the owner of event closure; legacy `record_episode` is compatibility-only. | None for the target path. |
| MEM-003 | P0 | closed | Nodes, aliases, descriptions, mentions, qualified assertions, evidence and many-to-many assertion/evidence links are durable; identity merges retarget history and preserve conflicts. | Independent support, polarity, viewpoint, time and contradiction are retained without blind triple overwrite. | target=design §4 and §9.1–9.2; inventory=`sqlite_graph_store.py`, `schema.py`; references=source-first graph tests; verification=alias/cross-Episode resolution, merge retargeting, sourced assertion and conflict/evidence round-trip tests; residuals=historical versions already overwritten by the old database cannot be reconstructed automatically. | Existing legacy data may have unrecoverable conflicting versions. |
| MEM-004 | P0 | closed | Bounded workers claim Episodes, validate grounded model proposals or use the conservative deterministic extractor, then commit a retryable sourced projection in one transaction. | Canonical identity, evidence attachment, compatible merge and conflict retention are deterministic; source Episodes survive failures. | target=design §5 and §9.4; inventory=`elfie/brain/memory/consolidation.py`; references=source-first worker tests; verification=model grounding, global semantic IDs, retry/lease recovery, merge/conflict and source-preservation tests; residuals=provider and scheduling policy remain injected/operational choices; a strict predicate registry is later hardening, not a P0 dependency. | No unbounded model call occurs inside a write transaction. |
| MEM-005 | P0 | closed | `RecallRequest` now performs deterministic Basic/Text candidate search followed by bounded Local Graph traversal, source lookup, relation/time filters and declared limits. | Text covers rare/unresolved wording; graph traversal covers explicit relationships; sources and conflicts remain visible. | target=design §6 and §9.5; inventory=`sqlite_retrieval_store.py`, `node_store.py`, `sqlite_graph_store.py`; references=source-first retrieval tests; verification=rare-term/alias, person-network, knowledge-object, seed, time-window, hop/limit and representative latency checks; residuals=Global/community and vector retrieval remain later projections. | Current lexical projection is intentionally simpler than FTS5 and is rebuildable. |
| MEM-006 | P0 | closed | `RecallBundle` and its deterministic renderer are implemented; the reasoning Memory reader consumes independent typed items with real source IDs. | Upper layers receive bounded nodes, assertions, paths, Episodes, evidence and conflicts through the semantic contract, not raw SQL. | target=design §6 and §9.5; inventory=`memory_records.py`, `recall_renderer.py`, `reasoning/memory_context.py`; references=reasoning and renderer tests; verification=stable rendering, hard character cap, provenance and no synthetic source for typed nodes; residuals=final natural-language narration remains Reasoning's responsibility. | None for the Memory boundary. |
| MEM-007 | P0 | closed (development) | A fresh-target importer, source read-only guard, count/digest/hash reconciliation, lease recovery and retention operations are implemented. | Import is Episodes-first, auditable and reversible; old data is not mutated and no long-term dual write is introduced. | target=design §9.6; inventory=`migration.py`, `sqlite_memory_store.py`; references=ADR-0018 and persistence rules; verification=legacy import, eligible Episode hash match, evidence mapping, reopen and forget/archive tests; residuals=production data migration/cutover was intentionally not run and requires a separate explicit approval. | No live user database was touched. |
| MEM-008 | P0 | blocked | Deterministic structural gates and the authorized real Ark candidate/judge run now pass; owner experience review is not complete, so Stage 1 is not promoted. | A replayable redacted report must show deterministic gates, source grounding, relationship/conflict behavior, restart and latency before Stage 1 promotion. | target=design §9.7 and `docs/.internal/elfie-stage1-memory-backed-chat-execution-plan.md`; inventory=`devtools/evals/stage1_chat_ark.py`, scenario set and focused tests; references=`build/evaluations/stage1-chat/e1-ark-fixed-v2/report.json`; verification=81 deterministic E1 tests passed, real Ark candidate 36 calls and judge 24 calls, machine hard gate passed, all five Ark dimensions passed (worst alien-world-boundary 5, history 4, identity 5, memory grounding 5, naturalness 4), persistence scan exit 0; residuals=owner experience review and separate production-data cutover remain. | Ark authentication and structured judge completion passed; no secret was written to the report. |

## Post-baseline optimization register

The following records the current development priorities after the baseline; it does not rewrite the closed or blocked
status of `MEM-001`–`MEM-008`.

| ID | Priority | Status | Current gap | Next acceptance gate |
| --- | --- | --- | --- | --- |
| OPT-001 | P0 | in progress | The bounded slice now compiles the frozen E1 fixture through the typed Elfaria World Canon/Genesis path, removes duplicated identity facts from the reasoning prompt, and verifies cleanup on cross-file publish failure. Full E2/E3 coverage and owner experience review remain open. | Freeze the story/knowledge coverage matrix; pass the relevant E2/E3 new-adoption, paraphrase and restart gates, then complete owner review. |
| OPT-002 | P0 | in progress | WorkingContext now closes bounded topic Episodes, captures source records before inference, extracts explicitly attributed owner/person facts, preserves aliases and supports explicit correction chains. Full longitudinal evaluation is still open. | Pass the continuous-learning regression for new people, names, preferences, corrections, conflicts, duplicates, restart and failed delivery/model paths. |
| OPT-003 | P1 | deferred | Long-run compaction, forgetting, archiving, growth and latency have not had endurance validation. | After OPT-001/002 pass, establish bounded-growth and recoverable-lifecycle evaluation. |
| OPT-004 | P1/P2 | deferred | Real Nest observation, activity and multi-Elfie interaction are outside the current chat loop. | After Stage 2 world integration, validate embodied memory and world-event provenance. |

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
passed) in `/private/tmp/elfie-e1-real-20260828-final2/report.md`. Residuals=full E2/E3 coverage and owner experience
review remain; no production backfill and no OPT-002/003/004 work.

OPT-002 implementation evidence (2026-08-27): target=continuous-learning source-first
flow and WorkingContext boundary; inventory=`elfie/brain/reasoning/conversation_context.py`,
`coordinator.py`, `settlement.py`, `elfie/brain/memory/consolidation.py`,
`infrastructure/persistence/memory/{schema.py,sqlite_memory_store.py,sqlite_graph_store.py}`;
references=OPT-002 execution brief §3–§7 and Memory design §9.4–§9.5;
verification=`test/elfie/brain/reasoning/test_conversation_context.py`,
`test/elfie/brain/reasoning/test_memory_context.py`,
`test/elfie/brain/reasoning/test_turn_settlement.py`,
`test/infrastructure/persistence/memory` (40 tests), Ruff and persistence scan;
residuals=full BrainRuntime longitudinal replay, production cutover, owner experience
review and OPT-003/OPT-004 capabilities remain open.

## Remaining acceptance order

1. Perform the owner experience review and record the promotion decision.
2. Approve and execute any production-data cutover separately; development migration is complete.

The required read-only persistence inventory is:

```text
uv run --no-sync python scripts/governance/persistence/scan.py --project-root . --check
```

It must be rerun after schema changes. A row closes only when its target,
inventory, references, verification and residuals are recorded. MEM-008 remains
blocked until the human acceptance gate is completed.
