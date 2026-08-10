# Application conformance

> This is the temporary implementation-gap register for the normative
> [Application architecture contract](../contracts/application). It records
> current legacy non-conformance; it does not define architecture or authorize
> another exception. When every item is closed and the exact machine baseline
> is empty, this page and its navigation entry are removed.

## Status and evidence rules

- `open`: current production code still violates the contract.
- `in progress`: one domain is being migrated, but its complete definition of
  done has not passed.
- `closed`: callers, implementation, tests and machine baseline are all clean.
- An item cannot close because a document, interface or replacement class exists;
  the old production call chain must also be removed.
- Every machine exception carries one gap ID. No unregistered exception is
  allowed, and a gap ID never permits a new occurrence.

The executable source is
`test/architecture/baselines/app_layer.py`. Its entries identify exact
imports, functions, constructors or routes. The architecture test requires an
exact match: deleting debt requires deleting its baseline entry in the same
change; adding or restoring debt fails. This page groups those entries by cause
and acceptance gate rather than copying the full generated inventory.

## Current gaps

| ID | Severity | Status | Current gap | Acceptance gate |
| --- | --- | --- | --- | --- |
| APP-001 | P0 | open | Interfaces import concrete persistence/device implementations and therefore know technical storage and gateway details. | Every Interface depends only on injected public Feature/Orchestration services and protocol models; the `interface -> infrastructure` machine set is empty. |
| APP-002 | P0 | open | Features import concrete Infrastructure, some public use-cases receive `db_path`, one Feature imports FastAPI, and embodiment Orchestration imports a persistence implementation. | Consumer-owned Ports replace concrete dependencies, public use-cases receive typed dependencies, and the Feature/Orchestration isolation machine sets are empty. |
| APP-003 | P0 | open | The composition root is incomplete; API/CLI factories, routes and dependency helpers construct repositories, stores or registries. | Bootstrap owns construction and lifetime, entry points receive an application container or explicit services, and the Interface-construction machine set is empty. |
| APP-004 | P1 | open | Interfaces and Features import another Feature's internal modules; Infrastructure also depends on a private Feature module. Stable package facades are inconsistent. | Each migrated domain exports one public facade; cross-domain callers use it or an owned Port; internal-import machine sets are empty and the App import graph is acyclic. |
| APP-005 | P1 | open | Many JSON Routes have no named `response_model`, and loose dictionary/`Any` protocol annotations remain. | Every product Route has strict request/response models and the standard error envelope; non-JSON page/stream responses are explicit; Route model and loose-annotation machine sets are empty. |
| APP-006 | P1 | open | Authentication, role checks and error mapping are spread across Interface and Feature helpers without one Principal/RequestContext and business-error taxonomy. | Strict principals exist for user/setup/admin/observer/device; Interface authenticates, Feature authorizes; business errors have one tested protocol mapping. |
| APP-007 | P1 | open | Transaction ownership, Repository commit behavior, typed-file writers and external-workflow recovery are not uniformly expressed by Ports and tests. | Each migrated command declares its database, file or external-workflow consistency class; no external wait occurs inside a DB transaction; atomicity and recovery tests pass. |
| APP-008 | P1 | open | Some Features own threads/jobs or blocking platform work, while task cancellation, timeout, receipt and restart semantics are inconsistent. | Scheduler/Runner Ports own background work; Bootstrap/lifecycle owns runners; async boundaries and long-task semantics have focused tests. |
| APP-009 | P1 | open | Global MyPy remains non-strict and no migrated-domain strict zone has been established. | Each migrated domain and its public callers pass strict MyPy without `Any` escape hatches; the strict override expands as domains close. |
| APP-010 | P1 | open | External-body persistence and device registration have overlapping registries/repositories; embodiment contracts import persistence records and Orchestration carries `db_path`. | One external-body product model and consumer-owned Ports remain; device transport is an Infrastructure adapter; hosting/homing remains Orchestration; duplicate facts and concrete imports are removed. |
| APP-011 | P1 | open | Versioned and historical product APIs coexist, including duplicated caller projections and untyped legacy resources. | Migrate one API business domain at a time under `app/interfaces/api/AGENTS.md`, move every real caller, then delete the old Route, client, DTO and fixtures without aliases. |
| APP-012 | P1 | open | Configuration, secret access and caches do not yet share one enforced ownership template across App domains. | Every migrated configuration has one typed owner/writer and precedence; secrets use references/Secret Ports; caches declare authority, invalidation, lifetime and rebuild behavior. |

## Machine coverage

The exact App scanner and `app_layer.py` baseline currently cover
`APP-001`, `APP-002`, `APP-003`, `APP-004`, `APP-005`, `APP-008` and
`APP-011`. The remaining authorization, transaction, strict-typing,
embodiment-fact and configuration-ownership rows require domain-specific
tests and review as each migration is selected. A passing scanner proves only
that no covered violation was added and the baseline is exact; it does not
declare the whole App contract conformant.

## Migration-unit record

Each approved domain migration adds a short record to this section before code
changes begin:

```text
Domain:
Gap IDs:
Current authoritative facts:
Routes and production callers:
Target public facade and models:
Ports and adapters:
Consistency class:
Principal and authorization:
Timeout / retry / idempotency:
Legacy deletion list:
Focused tests and end-to-end gate:
Machine baseline entries to remove:
Status: open | in progress | closed
```

The record is an execution checklist, not a design authority. A migration is
closed only after all twelve completion conditions in the Application
architecture contract pass. API caller migration, persistence changes and UI
changes remain separately reviewable even when they belong to one domain.

## Initial domain inventory

The current application domains include accounts, administration, adoption,
configuration, setup, chat, Elfie profile, Nest management/registration and
embodiment. This inventory does not set priority and does not approve a broad
rewrite. The maintainer selects one domain; its exact call chain and deletion
gate are recorded before implementation.

The existing API cleanup remains the first already-discussed migration stream.
Capacity closure and hardware-aware local-model recommendation remain separate
product changes and are not hidden inside architecture migration.
