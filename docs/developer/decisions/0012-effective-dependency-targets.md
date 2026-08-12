# ADR-0012: Effective dependencies include dynamic execution targets

**Status:** Accepted
**Date:** 2026-08-12

## Context

The architecture scanners historically treated Python imports as dependency
edges. A product entry point could therefore launch a forbidden repository
module with `python -m` or a script path and bypass the same boundary without an
import. Equivalent gaps exist in dynamic loaders, Node child processes and shell
commands. A rule aimed only at the module that exposed this gap would miss the
next forbidden target and would not express the architecture contract.

## Decision

Repository-module targets that can be resolved from Python, Node, Godot or shell
execution surfaces are effective dependencies. They follow the same caller-to-
target ownership matrix as static imports.

`scripts/architecture/effective_dependency_scan.py` therefore:

- classifies callers and targets by their architectural owner across the whole
  repository rather than blacklisting one directory;
- detects literal Python module commands, repository script paths,
  `importlib`/`runpy`, Node dynamic loads and child-process calls, Godot process
  calls, and shell module/script commands; unknown source roots fail closed;
- ignores external executable names because they are technical dependencies,
  not repository-module edges;
- runs without a legacy baseline and rejects every forbidden effective edge;
- is executed both as a candidate check and, after this governance change
  reaches the base branch, from the immutable base commit in CI.

Indirect launch plans that cannot be resolved statically are not automatically
approved. Product layers receive them through a narrow Port, while Bootstrap or
the owning Infrastructure Adapter constructs the concrete plan; semantic review
remains required.

## Consequences

Moving a forbidden target from an import into a command string no longer changes
the dependency decision. Interfaces continue to call public Feature or
Orchestration boundaries; Developer Tools may use public product boundaries for
isolated experiments, while product roots and product entry scripts do not
launch Developer Tools. Fixture tests attack multiple source and target owners
so the gate cannot collapse into a one-off `devtools` check.

This decision extends enforcement of the frozen architecture. It does not
change top-level ownership, authority, Port semantics or the macro architecture
baseline.
