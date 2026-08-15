# Configuration management conformance

> Open migration register for the normative
> [Configuration management contract](../contracts/configuration-management).
> It records current implementation facts and deletion gates; it does not
> authorize new scattered configuration or product behavior.

**State:** open

## Current inventory

The eight registered bundled YAML documents now live under the repository
`config/` root: system, Provider and model catalogs, tools, Brain Energy,
Selfhood and emotion expressions, and Nest defaults. Species/Profile
declarations are explicitly outside this migration. Algorithm constants, build
configuration and protocol constants remain outside this migration unless the
contract's classification rule identifies them as product configuration.

Small direct-construction safety defaults remain in domain types and adapters;
they are not packaged product documents. Production composition loads the
registered bundled documents and injects typed values.

The user path resolver and atomic YAML writer already target
`${ELFIE_HOME}/configs/`, and first-run layout creation does not copy defaults.
Those conforming behaviors must be preserved during migration.

## Open gaps

| ID | Severity | Status | Current deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| CFG-001 | P0 | open | The in-scope defaults have been relocated to the root `config/`; old Provider/model/Brain package-local YAML files and the Python-literal model catalog were removed, and production consumers now use registered loaders or injected typed values. | Record the complete inventory and verify no unclassified in-scope residual remains, without touching Profile species declarations or adding capabilities. | code: `config/`, deleted legacy YAML, `infrastructure/persistence/configuration/bundled_defaults.py`, `infrastructure/models/catalog.py`; final inventory evidence pending |
| CFG-002 | P0 | open | The closed registry, bundled/runtime sources, document-specific policies and permanent negative architecture checks exist. The complete policy acceptance matrix and closure evidence are still pending. | Prove field overlays, complete replacement, bundled-only, user-only, failure and secret rules, and leave no business/domain YAML or arbitrary-path access. | `infrastructure/persistence/configuration/documents.py`, `test/architecture/test_configuration_management.py`; focused tests pass, final matrix pending |
| CFG-003 | P0 | open | Desktop staging copies repository `config/` once to `resources/config/`; package-data collection and legacy catalog copies were removed; the release manifest requires all eight documents. | Prove complete manifest hashes and installed-mode startup without a source checkout while preserving user configuration. | `scripts/assemble_desktop_resources.py`, `scripts/release_manifest.py`, packaged-runtime tests; final matrix pending |
| CFG-004 | P1 | open | Configuration-specific permanent structure and boundary checks are registered in the Contract Registry and run in deny-all form; the required five-part closure evidence has not yet been recorded. | Complete the required five-part closure evidence and leave permanent target checks in deny-all mode. | `scripts/architecture/contract_registry.py`, `test/architecture/test_configuration_management.py`; final audit pending |

## Closure order

1. Freeze and classify the complete in-scope source/default/path/packaging inventory; record Profile species declarations as out of scope.
2. Complete the focused policy and boundary acceptance matrix without adding
   product behavior.
3. Record five-part evidence for every row and close only rows whose residual
   inventory is empty.

The register is removed in a later governance-only closure after every row is
closed with complete evidence and marked ready. Product migration cannot delete
or weaken this register, the contract or its permanent checks.
