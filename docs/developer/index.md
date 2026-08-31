# Developer docs

The Developer docs are organized along "understand first, then modify, then
deliver". Each page owns exactly one problem; code and tests are the current
source of truth.

## Current architecture

- [Current architecture](./architecture/): the system panorama, the core call
  chain and the process boundaries.
- [Module boundaries](./architecture/module-boundaries): what each root module is and
  is not responsible for.
- [Cognitive information flow](./architecture/cognitive-flow): the typed flow
  from perception input to execution receipt.
- [Communication channels](./architecture/communication): the verified Telegram-shaped
  Discord account, pairing, routing and lifecycle boundary.
- [Runtime & data](./architecture/runtime): how configuration, data, services
  and build artifacts are isolated.

## Design & governance

- [Designs](./designs/): accepted cross-version intent, system boundaries and
  future implementation direction.
- [Elfie top-level module design](./designs/elfie-top-level-module-design): the
  target first-class ownership of one complete Elfie.
- [Elfie Brain ten-system architecture](./designs/elfie-brain-ten-system-architecture):
  Brain's conceptual systems, runtime relationships and incremental implementation order.
- [Elfie Brain evaluation and evolution system](./designs/elfie-brain-evaluation-system):
  evidence-first Q6/P0 evaluation, constrained promotion and long-term evolution.
- [Elfie Memory architecture](./designs/elfie-memory-architecture): episodic memory, the personal
  knowledge graph and hybrid graph/text retrieval.
- [Service lifecycle state-machine design](./designs/service-lifecycle-state-machine):
  stable service tiers, entrypoints, process ownership and convergence.
- [Provider and endpoint-model availability](./designs/provider-model-availability):
  curated loading, serving-core scope and cost-aware health evidence.
- [Architecture contracts](./contracts/): the long-lived normative rules.
- [Repository architecture governance](./contracts/repository-governance): how
  contracts, ADRs, local Agent rules, scanners, baselines and CI form one
  enforceable quality loop.
- [Documentation structure contract](./contracts/documentation-structure): the
  public sections, Developer document classes and bilingual structure rules.
- [System architecture contract](./contracts/system): the target four-module
  structure, system Ports/Adapters and migration direction.
- [Service lifecycle contract](./contracts/service-lifecycle): the normative
  Runtime states, entrypoint semantics and managed-process invariants.
- [Elfie internal architecture contract](./contracts/elfie): one Elfie's
  aggregate, life-system and Port ownership boundaries.
- [Elfie Brain internal architecture contract](./contracts/brain): Turn,
  reasoning, mental-state and persistent-activity ownership.
- [Elfie conformance](./conformance/elfie): closure-ready evidence for the
  aggregate life-system migration pending governance-only removal. Brain
  conformance is complete and its contract is enforced by permanent
  architecture tests.
- [Elfie Memory conformance](./conformance/elfie-memory): implementation status
  and remaining external-acceptance gates for storage, consolidation, retrieval and the compatibility boundary.
- [Application architecture contract](./contracts/application): the
  normative ownership, dependency, Port/Adapter and composition rules for new
  and migrated `app/` code.
- [Service lifecycle conformance](./conformance/service-lifecycle): open gaps
  between the accepted lifecycle contract and the current implementation.
- [Architecture decisions (ADRs)](./decisions/): accepted reasoning for durable changes.

## Engineering

- [Repository quality governance](./engineering/quality-governance): how
  contracts, Agent guidance, machine checks, ratchets and review protect the repository.
- [Development flow](./engineering/development): environment, branches, minimal changes and
  the local working order.
- [Testing & quality](./engineering/testing): test layers, quality baseline, pre-commit and
  CI.
- [Debugging & workbenches](./engineering/debugging): the purpose and isolation of Elfie
  Lab and Nest Lab.
- [Command reference](./engineering/tooling): the unified CLI and the service, data and
  diagnosis commands.
- [Developer Tools](./engineering/devtools): the entry points and use cases of the two
  module workbenches and the Brain evaluation batch tool.
- [Brain evaluation workflow](./engineering/brain-evaluation): capture, judge calibration,
  protected confirmations, paired comparison and artifact review.
- [Godot](./engineering/godot): ownership and inspection of scenes, space, characters and
  the Web Runtime.
- [Desktop](./engineering/desktop): the Electron host, resource discovery and process
  supervision boundary.
- [Code standards & constraints](./engineering/standards): directory boundaries, Python
  types, tests and how to write docs.
- [Security & data boundary](./engineering/security-data): the isolation between production
  data, keys, private material and the public site.
- [Build & release](./engineering/build-release): build directories, release artifacts, the
  docs site and the manual review gate.

## Documentation rules

The Developer docs only collect finalized, verifiable content that helps others
get their work done. Discussion notes, model intermediate drafts, unimplemented
proposals and private worldbuilding do not enter the public sidebar; a key
design article needs its own topic, code evidence and maintainer review.
