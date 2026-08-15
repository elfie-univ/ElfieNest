# Configuration management contract

**Contract version:** 1.2
**Adopted:** 2026-08-15
**Scope:** application defaults, user configuration, loading and release packaging

> **Normative target.** This contract defines the one configuration-management
> model for ElfieNest. It organizes existing configuration without adding
> product capabilities. Current implementation gaps are tracked only in the
> [configuration-management conformance register](../conformance/configuration-management).

## Purpose and boundaries

ElfieNest has exactly two persistent configuration roots:

```text
repository config/                  ${ELFIE_HOME}/configs/
versioned bundled defaults          user-owned runtime configuration
read-only at application runtime    writable through typed application Ports
        |                                      |
        +---------- typed document loaders ----+
                              |
                    effective typed settings
```

The source root is named `config/` in lowercase and singular. The existing user
root remains `configs/` in lowercase and plural. They have different owners and
lifecycles and must never be treated as two copies of one directory.

Small constants needed to locate resources, reject invalid configuration or
report a startup failure may remain in code. They are not a third configuration
layer and must not duplicate product defaults. Required bundled product data
does not silently fall back to a second hard-coded copy.

This contract governs application configuration. Build-tool settings such as
`pyproject.toml`, CI, Electron Builder and Godot project files remain with their
tools. Protocol constants, algorithm invariants, derived values and safety
limits that require code review remain code unless a separate approved change
classifies them as product configuration.

## Physical layout

The initial bundled-default inventory is:

```text
config/
├── app/
│   └── system-defaults.yaml
├── models/
│   ├── provider-catalog.yaml
│   └── model-catalog.yaml
├── tools/
│   └── defaults.yaml
├── brain/
│   ├── energy.yaml
│   ├── selfhood.yaml
│   └── emotion-expressions.yaml
├── nest/
    └── defaults.yaml
└── species/
    ├── catalog.yaml
    └── <package>/
        ├── species.yaml
        ├── appearance.yaml
        ├── genesis.yaml
        └── assets/*.png
```

This tree is the source of bundled defaults and the registered species
configuration packages. `species/catalog.yaml` is the registered document;
the package members are validated as one immutable package by its Infrastructure
Adapter. Profile and Genesis receive typed values and do not read YAML. The
Godot 3D package remains under `godot_project/characters/`; only its semantic
package link and appearance bindings are represented in species configuration.

The user-owned layout remains:

```text
${ELFIE_HOME}/configs/
├── runtime.yaml
├── providers.yaml
├── tools.yaml
├── provider-catalog.yaml
├── auth.env
└── credentials/
    └── oauth/
        └── <connection_id>.json
```

`auth.env` and OAuth documents are secrets, not mergeable defaults. They live
under the user root because they are user-owned, but no matching source file may
exist under repository `config/`.

## Document registry, ownership and schemas

Every approved document has one closed `ConfigDocumentSpec` equivalent that
declares:

- a stable document ID and semantic owner;
- its bundled and/or user-relative path;
- whether the bundled document is required;
- its document version and typed validator;
- its effective-value policy; and
- its writer, reload and failure policies.

Production callers select a known document ID; they do not supply arbitrary
filesystem paths or dotted keys. Test and developer tooling may inject an
isolated sandbox root for deterministic tests, but the adapter still selects
the same registered document and fixed relative path, and it must never
default to the production `${ELFIE_HOME}`. Adding a document requires an
owner, schema, policy, tests and release coverage. The document registry is
not a plug-in registry.

The semantic owner defines the strict model and validation rules. The
Infrastructure configuration Adapter owns path resolution, decoding, merge
execution, atomic file I/O and technical errors. Physical placement in
`config/` does not transfer App, Elfie, Nest, model or tool semantics to
Infrastructure.

| Effective configuration | Bundled source | User source | Semantic owner | Policy |
| --- | --- | --- | --- | --- |
| System settings | `app/system-defaults.yaml` | `runtime.yaml` owned sections | App configuration settings | schema-aware field overlay |
| Provider product catalog | `models/provider-catalog.yaml` | `provider-catalog.yaml` | Infrastructure Models metadata | validated complete replacement |
| Model metadata catalog | `models/model-catalog.yaml` | none | Infrastructure Models metadata | bundled only |
| Global tool settings | `tools/defaults.yaml` | `tools.yaml` | App configuration capabilities | tool-and-field overlay |
| Energy creation defaults | `brain/energy.yaml` | none | Elfie Brain Energy | bundled only |
| Selfhood creation defaults | `brain/selfhood.yaml` | none | Elfie Brain Selfhood | bundled only |
| Emotion-expression mapping | `brain/emotion-expressions.yaml` | none | Elfie Brain Emotion | bundled only |
| Nest initialization defaults | `nest/defaults.yaml` | none | Nest | bundled only |
| Species catalog and packages | `species/catalog.yaml` and `species/<package>/` | none | Infrastructure loader, typed values injected into Profile/Genesis/Adoption | bundled only |
| Provider connections and endpoint models | none | `providers.yaml` | App configuration providers | user only |
| API and OAuth credentials | none | `auth.env`, `credentials/oauth/` or process environment | secret capability | user only; never merged |

Each YAML document has an explicit top-level document version. Code types are
the machine-readable schema authority; this contract does not create a second
JSON Schema. Version checks happen before values are exposed to consumers.

The existing `runtime.yaml` also contains explicitly opaque compatibility
buckets for other current consumers: `runtime_policy`, `models`, and
unowned `system` sections. The Settings Adapter preserves those buckets but
does not interpret or extend them; owned settings sections remain strict.

## Loading boundary

The implementation provides roles equivalent to:

```text
BundledConfigSource       RuntimeConfigSource
read config root          read/write ELFIE_HOME/configs
          \                 /
           document-specific typed Adapter
           validate + apply declared policy
                         |
        SystemSettings / ProviderCatalog / ToolSettings /
        Brain defaults / Nest defaults
```

The rules are:

- development resolves bundled documents from the repository `config/` root;
- an installed application resolves them only from its staged
  `resources/config/` root supplied by the launcher/resource resolver;
- installed code never searches the current working directory or a source
  checkout as a fallback;
- `infrastructure/persistence/configuration/` is the technical runtime boundary
  for global configuration files;
- build and release validators may read `config/` to validate and copy it, but
  do not become runtime configuration sources;
- App Features, Interfaces, Orchestration, Elfie and Nest do not resolve these
  roots, import YAML parsers or read configuration files directly;
- Bootstrap constructs and injects sources or typed results; it does not parse,
  merge, copy or own configuration facts; and
- consumers receive named typed values, never a generic nested dictionary,
  arbitrary section API or service locator.

A static bundled-only value may be injected directly at construction. A Port is
required only when a real consumer needs replaceable reads or writes; this
contract does not require a ceremonial Port for every immutable value.

## Precedence and merge semantics

“User configuration overrides bundled defaults” is shorthand for the declared
policy of one document. It is not authorization for a repository-wide generic
deep merge.

For schema-aware field overlays:

- an absent user document or absent field uses the bundled value;
- a present, valid user scalar replaces the bundled scalar;
- mappings merge only along fields declared by that document's schema;
- explicitly declared opaque extension buckets may preserve data owned by
  another registered consumer, but an owned section remains strict;
- a user list replaces the bundled list as one value unless that document
  explicitly defines a keyed-list policy;
- `null` is a value only for fields whose schema is nullable; it is not a
  universal delete marker;
- unknown fields are rejected unless the typed schema explicitly owns an
  extension field; and
- document-version metadata is validated independently and is never merged.

The Provider catalog is intentionally different: a valid user catalog replaces
the complete bundled catalog. Provider connections are user-only facts and are
never synthesized from a bundled connection template. Secrets are resolved
only from the process environment or user secret storage and never participate
in YAML merge logic.

## Missing, invalid and changing configuration

| Condition | Required behavior |
| --- | --- |
| Required bundled document missing, malformed or unsupported | fail build validation or startup with the document ID and safe diagnostic; do not use a duplicate code default |
| Optional user document missing | treat it as no user value; do not create a default copy |
| `runtime.yaml`, `providers.yaml` or `tools.yaml` malformed | reject the affected typed load or write; do not partially apply data |
| User `provider-catalog.yaml` malformed | log a safe warning and use the validated bundled catalog, preserving its existing whole-document fallback behavior |
| Secret missing | report the existing typed unavailable/not-configured state; never insert a placeholder secret |
| Unknown or incompatible document version | reject according to that document's typed failure policy; never guess or silently rewrite it |

Writers modify only their owned user document or section, preserve unrelated
owned data, remove plaintext secrets from ordinary YAML and use same-directory
atomic replacement. Backup behavior may be document-specific. A read does not
repair, migrate or rewrite a user file as a side effect.

Centralization does not add a global file watcher or hot reload. Each document
retains its existing explicit reload boundary until a separate behavior change
is approved.

## Installation and upgrade lifecycle

Source and installed resolution are:

```text
development:  <repository>/config/
release:      <application>/resources/config/
user writes:  ${ELFIE_HOME}/configs/
```

The staged release shape contains one bundled copy:

```text
resources/
├── config/
├── web/
├── godot-web/
├── python-core/
├── management-cli/
└── manifest.json
```

Release assembly validates every registered bundled document, copies the source
tree once to `resources/config/`, and records every file size and hash in the
release manifest. The Python executable and package data must not contain a
second authoritative copy.

First run creates the required `${ELFIE_HOME}` directories only. It does not
copy bundled defaults into `configs/`. User files are created only by their
actual writer. An application upgrade replaces bundled resources as part of the
application while preserving user configuration. Effective values are
recomputed on the next declared load boundary.

## Quality gates and change control

The governance layer is active before implementation:

- this bilingual contract fixes the target;
- ADR-0017 and ADR-0020 record the species-configuration decision;
- the Contract Registry binds the contract, ADR, Agent rules, machine-governance
  test and temporary conformance register; and
- the conformance register names every current implementation gap without
  weakening the target.

The configuration migration cannot close until focused evidence proves all of
the following:

1. an inventory classifies every relocated default, old loader, direct path,
   package-data entry and release consumer, with no unclassified residual;
2. architecture checks reject package-local bundled configuration, direct
   business/domain YAML reads, production arbitrary-path configuration access
   and duplicate hard-coded product defaults covered by this contract; tests
   and developer tools may use injected sandbox roots;
3. document tests cover schemas, versions, every policy in the table, missing
   fields, lists, nullable values, unknown fields and corrupt documents;
4. persistence tests cover atomic writes, unrelated-field preservation, secret
   exclusion, a clean first run and preservation of user files;
5. release tests prove exact `config/` staging, one-copy packaging, complete
   manifest hashes and installed-mode startup with no source checkout; and
6. the final conformance closure records `target`, `inventory`, `references`,
   `verification` and `residuals` evidence for every row.

After the temporary gaps close, permanent checks run deny-all. Relaxing a path,
owner, precedence rule, secret boundary or packaging invariant requires a
bilingual contract-version change and ADR before implementation. Ordinary
configuration additions must still update the closed document registry, typed
schema and focused tests together.

## Explicit non-goals

This reorganization does not add a Provider, model, tool, Brain or Nest
capability. It does not add filesystem auto-discovery, configuration-driven
protocol implementations, a public arbitrary-config API, UI fields, data
migration, dual reads, dual writes, compatibility aliases, remote
configuration or global hot reload. Species package registration is fixed by
the catalog and still requires a matching Godot package and code-owned runtime
protocol support.
