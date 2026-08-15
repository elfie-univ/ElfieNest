# Configuration management conformance

> Open migration register for the normative
> [Configuration management contract](../contracts/configuration-management).
> It records current implementation facts and deletion gates; it does not
> authorize new scattered configuration or product behavior.

**State:** closed
**Closure state:** ready

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

## Closed migration register

| ID | Severity | Status | Current deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| CFG-001 | P0 | closed | The in-scope defaults have one root `config/`; legacy package-local YAML, duplicate model catalog data and scattered runtime readers are removed or classified. Profile species declarations remain outside this migration. | Keep the two-root inventory exact and reject unclassified bundled files. | target=two-root-source-inventory; inventory=`config/` eight bundled documents, user `configs/` documents, legacy paths, loaders, package data and release consumers; references=`infrastructure/persistence/configuration/documents.py`, `bundled_defaults.py`, `test/architecture/test_configuration_management.py`; verification=registry inventory test plus repository/package audit; residuals=zero |
| CFG-002 | P0 | closed | The registry now carries schema, writer, reload and failure metadata; bundled and user sources validate before exposure, semantic owners reject unknown owned fields, and production/user roots are resolver-owned. Test and developer tools explicitly retain injected sandbox roots. | Keep field overlay, complete replacement, bundled-only, user-only, failure, secret and production-path rules under permanent tests. | target=registered-document-boundary; inventory=all thirteen document IDs, strict schemas, semantic catalog/connection validators, secret boundary and test/dev sandbox seam; references=`infrastructure/persistence/configuration/documents.py`, `schemas.py`, model/provider parsers, `test/infrastructure/persistence/configuration/test_documents.py`; verification=focused configuration and architecture tests; residuals=zero |
| CFG-003 | P0 | closed | Desktop staging copies repository `config/` once to `resources/config/`; the release manifest covers every staged file and user configuration is not copied or overwritten. Release-mode resolution requires a launcher-provided resource root. | Keep one staged copy, complete hashes, source-checkout independence and user-file preservation. | target=single-staged-bundled-root; inventory=resource assembly, manifest required paths/hashes, release resolver and first-run/user-write behavior; references=`scripts/assemble_desktop_resources.py`, `scripts/release_manifest.py`, `test/scripts/test_assemble_desktop_resources.py`, `test/scripts/test_release_manifest.py`; verification=assembly, manifest, installed-root and user-preservation tests; residuals=zero |
| CFG-004 | P1 | closed | The bilingual contract, ADR, Contract Registry, Agent rules and permanent deny-all checks now agree on the two-root configuration contract and its explicit sandbox exception. | Keep the five-part evidence shape and leave permanent target checks in deny-all mode until a later governance-only removal. | target=configuration-contract-closure; inventory=contract, ADR, registry, Agent rules, architecture gates and bilingual conformance rows; references=`docs/developer/contracts/configuration-management.md`, `docs/developer/decisions/0017-bundled-defaults-and-user-configuration.md`, `scripts/architecture/contract_registry.py`; verification=governance architecture tests and mirrored-document checks; residuals=zero |

## Closure order

1. Freeze and classify the complete in-scope source/default/path/packaging inventory; record Profile species declarations as out of scope.
2. Complete the focused policy and boundary acceptance matrix without adding
   product behavior.
3. Record five-part evidence for every row and close only rows whose residual
   inventory is empty.

The register is removed in a later governance-only closure after every row is
closed with complete evidence and marked ready. Product migration cannot delete
or weaken this register, the contract or its permanent checks.
