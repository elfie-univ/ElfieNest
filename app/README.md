# App module

> 中文版：[`README_zh.md`](README_zh.md)

## Module positioning

`app/` is the product application layer of ElfieNest: it owns user use-cases and
inbound interfaces, composes infrastructure, and performs application-level
orchestration only when a flow crosses `elfie/`, `nest/` or another authority.

## Responsibilities and non-responsibilities

Responsible for:

- Product use-cases such as accounts, adoption, configuration and setup;
- Inbound interfaces: HTTP, Web and CLI;
- Product infrastructure adapters: databases, file systems and device
  capabilities;
- Cross-authority flows between real Elfies, the Nest, Godot and devices;
- Application-level lifecycle orchestration of desktop service processes.

Not responsible for:

- Re-implementing an Elfie's brain, body, memory or communication at the
  application layer;
- Persisting Nest geometry, coordinates or Godot scene facts at the application
  layer;
- Implementing model providers and tool runtimes directly inside `features/`
  or `interfaces/`;
- Putting business rules in `bootstrap/`. `bootstrap/` may only create objects,
  inject dependencies and assemble the composition root.

## Directory map

```text
app/
├── bootstrap/       # Application composition root — dependency wiring only
├── features/        # Product use-cases: accounts, adoption, configuration, setup, ...
├── interfaces/      # Inbound interfaces: api, cli, web
└── orchestration/   # Cross-authority flows across Elfie, Nest, Godot and platforms
```

## Public entry points

- `app.interfaces.api.create_app`: creates the HTTP/Web application;
- `app.orchestration.ElfieNestEngine`: advances the Nest environment clock and
  pumps typed inputs;
- `app.orchestration.NestSession`: the only place where real `Elfie` instances
  and `Nest` are composed;
- `app.orchestration.embodiment`: orchestrates real body binding, hosting and
  homing through persistent leases, including its typed presence state machine;
- `infrastructure.devices.DeviceGatewayTransport`: brings authenticated
  LAN devices into the `infrastructure.devices.ExternalTransport` contract; device
  events, action polling and receipts never enter the Nest.

`NestSession` holds the real Elfie objects, while the Nest only receives Elfie
IDs and in-nest state; no other module may build its own composition of Elfies
and activity spaces.

## Architecture contract

The versioned authority for application code is the
[Application architecture contract](../docs/developer/contracts/application.md).
Permanent scanners and architecture tests enforce its machine-checkable rules.

The target dependency direction is:

```text
interfaces    ──> public feature use-cases / orchestration facades
features      ──> owned models and ports + approved domain public APIs
orchestration ──> application ports + elfie / nest public APIs
infrastructure──> implements feature/orchestration ports + technical libraries
bootstrap     ──> all of the above (wiring only)
```

Product flows that cross Elfie, Nest or another authority belong in
`app/orchestration/`; an Elfie's ordinary Food read, model call or tool execution
does not. Concrete adapters are created in `bootstrap/` and injected through
Ports; lower layers must not import `app.interfaces` in reverse. Retired paths
must not be restored.

## Run & debug

Run the most relevant application-layer checks from the repository root:

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q test/app/

UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q \
  test/app/orchestration/test_engine.py \
  test/app/orchestration/test_engine_cognitive_loop.py
```

For the full environment setup, the unified quality gate and product launch
flows, see [`CONTRIBUTING.md`](../CONTRIBUTING.md); for the current overall
boundaries, see [`docs/developer/`](../docs/developer/).

## Corresponding tests

- `test/app/features/`: product use-cases;
- `test/infrastructure/`: persistence and other infrastructure;
- `test/app/interfaces/`: API, CLI and Web boundaries;
- `test/app/orchestration/`: engine, cognitive loop and platform lifecycle;
- `test/architecture/test_project_structure.py`: top-level directories, legacy
  package bans and quality gate contracts.
