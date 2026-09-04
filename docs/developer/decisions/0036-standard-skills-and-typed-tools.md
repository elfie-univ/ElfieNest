# ADR-0036: Standard procedural Skills and typed executable Tools

- **Status:** accepted
- **Date:** 2026-09-03
- **Scope:** Brain Reasoning, bundled Skill resources and Infrastructure Tools

## Context

The previous implementation called a map of executable tool keys a “Skill” and
used provider-visible text markers to request execution. That conflated two
different capabilities and made the model protocol dependent on prompt parsing.

## Decision

Skills and Tools are separate contracts:

- A Skill is a first-party directory containing `SKILL.md` with `name` and
  `description` frontmatter followed by procedural instructions. Brain exposes
  metadata first and loads one approved document through a read-only native
  `load_skill` control operation inside a deliberate `ReasoningRun`.
- A Tool is an executable, typed capability with a stable name, description,
  JSON input/output schemas, handler and safety limits. Built-in definitions are
  explicitly registered under `infrastructure/tools/`; the existing `ToolPort`,
  configuration, permissions, scoped resources, observations and limits remain
  the execution authority.
- Bundled Skill sources live at `config/brain/skills/<name>/SKILL.md` and are
  staged to `resources/config/...`. User/third-party installation, Skill scripts,
  mutation and durable per-Elfie Skill state are disabled in this phase.
- DIRECT never advertises Skills or Tools. DELIBERATE may advertise the typed
  capabilities supported by the selected provider. A provider that lacks native
  Tool Calling receives no Tools and no text-marker fallback.

## Consequences

The model/provider boundary carries native Tool calls and provider-native
observation messages. Tool authorization remains independent of Skill loading,
so loading a procedural document cannot expand technical capability. Existing
web-search and scoped local-file behavior is retained through the same
production `ToolPort` chain.

## Rejected alternatives

- treating Tool keys as Skill definitions;
- parsing `[SEARCH]`/`[READ_FILE]` markers as a compatibility execution protocol;
- scanning arbitrary directories or executing Skill scripts;
- allowing a provider without native Tool Calling to receive hidden marker
  instructions.
