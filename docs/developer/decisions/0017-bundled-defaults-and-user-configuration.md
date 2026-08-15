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

## Consequences

- Source defaults have one visible location and installed applications have one
  manifest-covered copy.
- Business and domain code no longer owns file paths, YAML parsing or generic
  merge behavior.
- Missing required bundled data becomes a build/startup defect instead of being
  hidden by a duplicate hard-coded default.
- User configuration survives application upgrades and is never overwritten by
  bundled defaults.
- The existing scattered implementation requires a separate migration. Its
  gaps remain open in the configuration-management conformance register until
  source inventory, loaders, packaging and permanent tests close together.

This ADR changes the frozen system root structure and therefore revises the
bilingual System contract before product migration. It also registers the new
Configuration Management contract and its governance artifacts. No product
implementation is part of this decision change.
