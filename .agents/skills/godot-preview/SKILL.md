---
name: godot-preview
description: Runs one controlled headless Godot validation through the repository's shared toolchain boundary.
---

# Godot Preview Skill

This skill allows you to execute one supplied Godot validation script through `godot_guard.py`. It does not open the editor, start a game, take screenshots, run in the background, or retry after a failure.

Real execution must happen on the authorized host, not inside the Codex sandbox. The skill cannot
elevate itself: when a validation is required, invoke the repository's host entrypoint with the
execution tool's explicit host-authorization mode (in Codex, the equivalent of
`sandbox_permissions=require_escalated`). If authorization is unavailable or denied, report the
validation as blocked; do not fall back to a sandbox launch.

## When to use this skill
Use this skill when:
- A Godot-specific validation script must be run once in a controlled, synchronous process.

## How to use this skill
1. Run `scripts/quality/checks/godot_host.sh <validation-script>` from an authorized host shell. The
   same command can be run manually from the user's Terminal as a fallback.
2. The host entrypoint checks for an existing process and then delegates to `godot_guard.py
   validate`, which executes exactly one synchronous headless invocation.
3. Use the emitted `GODOT_INVOCATION` record as the validation evidence. For visual inspection, use the separate approved browser/UI workflow; this skill never starts an editor.
