# ADR-0009: Repository-wide implementation change classification

- **Status:** accepted
- **Date:** 2026-08-12
- **Scope:** repository architecture governance

## Context

The governance ratchet rejected a pull request only when architecture rules and
files under a small set of product roots changed together. Developer Tools,
ordinary scripts, root launchers, tests, executable documentation-site files
and non-governance workflows were outside that set. Those files can still alter
runtime, build, test or delivery behavior, so a governance change could modify
one of them while also changing the rule that judges it.

The gap is a classification problem, not a special case for `devtools/`. Any
new executable surface left outside both change classes would recreate the same
self-approval path.

## Decision

The governance/implementation separation applies repository-wide.

- Governance artifacts are contracts, ADRs, `AGENTS.md`, architecture
  scanners, architecture tests and governance CI definitions.
- After governance artifacts and ordinary prose documentation are identified,
  every other tracked file is implementation-side. This includes product
  packages, Developer Tools, build/release scripts, root runtime and toolchain
  configuration, ordinary tests, executable manifests, assets,
  documentation-site code and non-governance workflows.
- Governance identity takes precedence when architecture scanners and tests
  live below broadly classified script or test roots.
- Exact architecture baselines remain implementation-side artifacts. A product
  migration may shrink them; a governance change may not edit them.
- Ordinary prose documentation remains neutral and follows the class of the
  behavior it describes.
- Classification is path-based, repository-wide and fail-closed. A new
  directory, extension or executable surface cannot remain unclassified, and
  the rule must not use a blacklist naming one current offender.

Focused architecture tests exercise representative files from every class and
prove that governance cannot be mixed with any implementation-side surface.

## Consequences

Governance changes can no longer hide product, developer, build, test or
delivery behavior outside the former production roots. A new executable
surface is automatically implementation-side unless it is an explicitly
recognized governance artifact or ordinary prose document. Product changes
remain free to carry ordinary documentation and to shrink legacy baselines
without being mislabeled as governance.

Rejected alternatives are a `devtools` blacklist, retaining only the six
historical production roots, using file extensions as the primary classifier,
and treating every documentation file as implementation source.
