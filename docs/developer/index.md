# Developer docs

The Developer docs are organized along "understand first, then modify, then
deliver". Each page owns exactly one problem; code and tests are the current
source of truth.

## Understand the system first

- [Current architecture](./architecture/): the system panorama, the core call
  chain and the process boundaries.
- [Architecture contracts](./contracts/): the long-lived normative rules.
- [Repository architecture governance](./contracts/repository-governance): how
  contracts, ADRs, local Agent rules, scanners, baselines and CI form one
  enforceable quality loop.
- [System architecture contract](./contracts/system): the target four-module
  structure, system Ports/Adapters and migration direction.
- [System architecture conformance](./conformance/system): the temporary root
  module and technical-boundary migration register.
- [Application architecture contract](./contracts/application): the
  normative ownership, dependency, Port/Adapter and composition rules for new
  and migrated `app/` code.
- [Application conformance](./conformance/application): the temporary register
  and exact-removal gates for current App architecture debt.
- [Module boundaries](./architecture/module-boundaries): what each root module is and
  is not responsible for.
- [Cognitive information flow](./architecture/cognitive-flow): the typed flow
  from perception input to execution receipt.
- [Runtime & data](./architecture/runtime): how configuration, data, services
  and build artifacts are isolated.
- [Architecture decisions](./decisions/): accepted reasoning for durable changes.

## Then start modifying

- [Development flow](./development): environment, branches, minimal changes and
  the local working order.
- [Testing & quality](./testing): test layers, quality baseline, pre-commit and
  CI.
- [Debugging & workbenches](./debugging): the purpose and isolation of Elfie
  Lab, Nest Lab and Runtime Lab.

## Finally verify and deliver

- [Command reference](./tooling): the unified CLI and the service, data and
  diagnosis commands.
- [Developer Tools](./devtools): the entry points and use cases of the three
  module workbenches.
- [Godot](./godot): ownership and inspection of scenes, space, characters and
  the Web Runtime.
- [Desktop](./desktop): the Electron host, resource discovery and process
  supervision boundary.
- [Build & release](./build-release): build directories, release artifacts, the
  docs site and the manual review gate.

## Collaboration rules

- [Code standards & constraints](./standards): directory boundaries, Python
  types, tests and how to write docs.
- [Security & data boundary](./security-data): the isolation between production
  data, keys, private material and the public site.

## Documentation rules

The Developer docs only collect finalized, verifiable content that helps others
get their work done. Discussion notes, model intermediate drafts, unimplemented
proposals and private worldbuilding do not enter the public sidebar; a key
design article needs its own topic, code evidence and maintainer review.
