---
name: task-closure
description: Enforce evidence-backed completion for implementation, bug-fix, migration, release, cleanup, and contract-conformance tasks. Use whenever Codex must change a repository and the result must truly converge rather than stop at a passing main path or partial implementation.
---

# Task Closure

Use this skill for every requested implementation, bug fix, migration, release,
cleanup, or contract-conformance task. It prevents a passing subset of tests or
an implemented “main path” from being reported as final completion.

## Non-negotiable rules

- Freeze the approved design and turn every acceptance clause into one matrix row.
- Use only these states: `not_started`, `implementing`, `verifying`, `complete`,
  and `blocked`. Never report “mostly complete” or “core complete”.
- A row is `complete` only with implementation evidence, automated tests, a
  replayable runtime scenario, platform/install conditions, recorded evidence,
  and an empty residual list.
- A missing OS, service, credential, package, or clean machine is `blocked`, not
  complete. Name the missing condition and the next replayable check.
- A local checkpoint may explicitly pass only rows marked
  `blocker_class: "external_environment"`; this preserves their `blocked` status
  and never authorizes a final completion claim.
- Do not commit or push a final result while an in-scope row, P0 condition,
  release condition, or conformance row is open.

## Workflow

1. Read the governing contract, design, current conformance rows, and directory
   rules. Create a compact `task-closure.json` at the repository root before
   editing code.
2. Put every changed path in `scope` and classify every requirement in `rows`.
   Link affected contract/conformance IDs; if none apply, record an explicit
   reason under `conformance.reason`.
3. Implement one complete slice at a time. Keep the matrix at `implementing` or
   `verifying` until its required runtime evidence exists.
4. Verify in layers: focused behavior, negative/failure, concurrency/crash/
   recovery, platform/install, architecture/quality, and the final gate.
5. Use the tiered gate for feedback during implementation:

   ```bash
   bash scripts/pre_submit_gate.sh --stage commit \
     --base-sha "$(git rev-parse origin/main^{commit})" \
     --closure-file task-closure.json
   ```

   A feature-branch push uses `--stage push`. The selector may escalate either
   command to the main tier when the impact is unknown or governance-sensitive.
   These progress checks must use `--mode progress`; they do not close the task.

6. Run both final checks before claiming completion:

   ```bash
   .venv/bin/python3 scripts/check_task_closure.py \
     --file task-closure.json --base-sha "$(git rev-parse origin/main^{commit})"
   bash scripts/pre_submit_gate.sh --stage main \
     --base-sha "$(git rev-parse origin/main^{commit})" \
     --closure-file task-closure.json
   ```

   A local checkpoint may add
   `--allow-external-environment-blockers` when the only open rows are
   explicitly classified external-environment gaps. The default gate remains
   strict for final delivery and protected branches.

   The main stage is the complete CI-aligned backstop. It may reuse only a
   successful exact-candidate result from `build/validation-cache/`; a changed
   candidate, base, lockfile or toolchain invalidates that result.

6. Report `complete`, `blocked`, and remaining items separately. If a required
   check is blocked, stop with the exact environment and next check; do not turn
   it into a successful completion claim.

## Bootstrapping or changing the gate

Treat changes to this skill, the closure checker, the pre-submit gate, or their
governance classifier as governance work. The immutable-base checker intentionally
requires two phases: first land the governance-only classifier/contract test that
recognizes the new guard paths; then land the skill, checker, gate integration and
their behavior tests. Do not weaken the base-aware check to make both phases pass
in one change, and do not claim the second phase complete until its own gate passes.

## Matrix schema

The matrix is intentionally compact and machine-checkable:

```json
{
  "schema_version": 1,
  "task": "short task name",
  "scope": ["app/example.py", "test/app/example/", "task-closure.json"],
  "conformance": {
    "rows": ["LFC-001"],
    "reason": ""
  },
  "rows": [{
    "id": "REQ-001",
    "requirement": "One exact acceptance clause",
    "status": "complete",
    "implementation": ["path and behavior"],
    "automated_tests": ["command or test path"],
    "runtime_scenarios": ["replayable scenario"],
    "platform_conditions": ["macOS 14; clean data root"],
    "evidence": ["command: ...", "artifact: ..."],
    "residuals": []
  }]
}
```

`scope` is a bounded list of paths/globs; unclassified changes fail the gate.
Do not use a catch-all `*` or `**` scope. `conformance.rows` must be closed by
the candidate when listed; otherwise the gate fails.

Blocked rows must include `blocker_class`; the only checkpoint-allowable value
is `external_environment`. A code failure, missing evidence or unclassified
blocker remains a hard gate failure.
