---
name: godot-preview
description: Runs one controlled headless Godot validation through the repository's shared toolchain boundary.
---

# Godot Preview Skill

This skill allows you to execute one supplied Godot validation script through `godot_guard.py`. It does not open the editor, start a game, take screenshots, run in the background, or retry after a failure.

## When to use this skill
Use this skill when:
- A Godot-specific validation script must be run once in a controlled, synchronous process.

## How to use this skill
1. Run `scripts/preview.sh <validation-script>` from the repository checkout.
2. The script delegates to `godot_guard.py validate`, which checks for an existing process and then executes exactly one synchronous headless invocation.
3. Use the emitted `GODOT_INVOCATION` record as the validation evidence. For visual inspection, use the separate approved browser/UI workflow; this skill never starts an editor.
