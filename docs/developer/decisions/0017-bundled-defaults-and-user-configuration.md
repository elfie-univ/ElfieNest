# ADR-0017: Separate bundled defaults from user configuration

- **Status:** Accepted
- **Date:** 2026-08-15
- **Scope:** repository-wide configuration placement, loading and packaging

## Context

Existing application defaults are split across package-local YAML files,
hard-coded dictionaries and domain constructors. Their loaders commonly derive
paths from `__file__`, while user-owned documents already live under
`${ELFIE_HOME}/configs/`. Release packaging collects only selected package data,
so the source location, installed location and effective-value rules are not one
coherent contract.

Copying every default into the user directory on installation would create two
long-lived copies, obscure which version owns a value and risk overwriting user
changes. Allowing each consumer to read YAML directly would preserve the path
and merge scattering even if the files were moved.

## Decision

Adopt two persistent configuration roots:

- repository `config/` is the immutable, versioned source of bundled product
  defaults and is staged once as `resources/config/`;
- `${ELFIE_HOME}/configs/` remains the writable source of user configuration and
  secrets.

First run creates directories but does not copy defaults. Effective values are
produced by document-specific typed Infrastructure Adapters. User values take
precedence only according to the declared document policy: system and tool
settings use schema-aware overlays, the Provider catalog uses validated complete
replacement, bundled-only documents remain bundled-only, and connections and
secrets remain user-only.

The root `config/` directory is a non-Python resource root, not a fifth system
authority. Semantic models remain with App, Elfie, Nest, Models or Tools;
Infrastructure owns technical loading and writing, and Bootstrap only wires the
boundary.

The initial move is strictly structural. Existing species declarations,
appearance profiles and Genesis behavior are outside this migration and remain
in their current Profile-owned source. This decision adds no species fields,
normalization, discovery, registration, assets or behavior.

## Decision update: registered schemas and execution boundaries

The registered document metadata is the single authority for document IDs,
fixed relative paths, versions, schemas, writer policy, reload boundary and
failure policy. Bundled and user sources validate a document before returning
it, and semantic owners reject unknown fields in their owned records. A small
set of explicitly declared opaque extension buckets may preserve data owned by
another existing consumer; they are not permission to add arbitrary fields to
owned sections.

Production callers use registered document IDs and resolver-owned roots only.
Test and developer tooling may inject an isolated root for sandboxing, but it
must reuse the registered filenames and validators and must never default to a
production `ELFIE_HOME`.

## Consequences

- Source defaults have one visible location and installed applications have one
  manifest-covered copy.
- Business and domain code no longer owns file paths, YAML parsing or generic
  merge behavior.
- Missing required bundled data becomes a build/startup defect instead of being
  hidden by a duplicate hard-coded default.
- User configuration survives application upgrades and is never overwritten by
  bundled defaults.
- The conformance register remains as a closure-ready record until a later
  governance-only change removes it; it cannot be used to authorize new
  scattered configuration.

This ADR changes the frozen system root structure and therefore revises the
bilingual System contract before product migration. It also registers the new
Configuration Management contract and its governance artifacts. No product
implementation is part of this decision change.
