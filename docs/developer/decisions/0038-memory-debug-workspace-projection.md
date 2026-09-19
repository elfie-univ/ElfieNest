# ADR-0038: Memory Debug Workspace is a read-only Brain developer projection

- **Status:** accepted
- **Date:** 2026-09-19
- **Scope:** Memory Debug Workspace design placement and authority boundary

## Context

The Memory Debug Workspace needs a durable public design because it documents the whole-library
view, Episode processing, Recall explanation, and the Elfie Lab link. The page is a developer
debugging surface, not a new Memory subsystem or a replacement for the existing Memory and
Reasoning designs.

## Decision

Keep the design under `docs/developer/designs/elfie/brain/` with the other Brain designs and
maintain its Chinese mirror. The workspace is a read-only projection owned by Developer Tools:

- Memory remains the authority for durable Episodes, Evidence, Nodes, Assertions, and Recall
  selection facts.
- Elfie Lab remains the authority for the Brain Turn, Prompt Context, and final context order.
- The workspace may show observed operation and Recall traces, but it must not become a second
  Memory store or infer missing observations.
- Production viewing stays read-only; add-Episode experiments use an isolated or dry-run boundary.

The documentation architecture test registers the new Brain design explicitly. This extends the
design catalog without changing the system's ownership, dependency direction, or runtime
authority.

## Consequences

Developers have one documented place to understand the three debugging questions: what exists in
the library, how an Episode affects Memory, and why a Recall returned its results. Future changes
to the page must preserve the source-first and single-authority boundaries above.

## Rejected alternatives

- Treating the workspace as a second Memory implementation or persistence authority.
- Placing the design in a generic Developer Tools tree and separating it from the Brain design
  chain.
- Claiming Prompt Context order from Memory Debug alone.
