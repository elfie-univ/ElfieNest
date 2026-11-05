# ADR-0042: Project-scoped image review and fresh-chat skills

**Status:** Accepted
**Date:** 2026-11-05
**Scope:** Coding-agent instructions and reusable project skills

## Context

Image-heavy coding conversations can accumulate substantial request bytes before
token-based history compaction is triggered. Loading every reference and its
enlarged copies also duplicates visual input. Starting another conversation
does not control the images loaded afterward.

The review procedure and clean-restart procedure must travel with ElfieNest so
contributors can reuse them after checking out the relevant project revision.
User-only skill installations do not provide that repository-level distribution.

## Options

- Keep user-level copies: available locally but not distributed with the project.
- Rely on repeated compaction or conversation forks: neither guarantees that
  historical images are absent from the new request.
- Version the procedures and their helpers as project skills, with concise root
  AGENTS guidance: selected.

## Decision

Store `lightweight-image-review` and `worktree-fresh-chat` under `.agents/skills/`,
including their executable helpers. The root `AGENTS.md` routes local image
inspection and explicitly requested clean restarts to these skills.

Image inspection first checks metadata, then loads a bounded overview or labeled
contact sheet. It targets roughly 2 MB of newly added Base64 image payload per
tool result, uses native-resolution crops when details matter, avoids enlarged
duplicates and preserves source files. Lossy previews cannot establish exact
color, transparency, pixel detail or final visual acceptance.

A clean restart requires an explicit user request. It creates a fresh thread
with the existing worktree as its persisted working directory, preserves Git
state, and carries no previous messages or images. It does not archive the old
thread or transfer managed-worktree ownership. System instructions and automatic
memory injection remain subject to the normal application behavior.

## Consequences

The skills are discoverable from project checkouts that contain this revision;
other branches and computers must first synchronize the files. The helpers use
available Codex, Node, Git and Pillow environments without installing dependencies
or editing application configuration.

These are agent workflow rules, not a hard application-level image limit or a
guarantee of lower end-to-end latency. They do not alter product architecture,
public protocols, persistent data contracts or CI policy. Existing validation,
Git authorization and protected-main delivery requirements continue to apply.
