# Security & data boundary

ElfieNest keeps "an Elfie's long-term life data" separate from "source code,
build artifacts and public docs". Any new feature must first explain where its
data is written, who owns it, and how it is cleaned up.

## Product data roots

- Installed runs resolve the data root in this order: `--data-home PATH`,
  `ELFIE_HOME`, then `~/.elfienest`.
- Source and worktree runs resolve it in this order: `--data-home PATH`,
  `ELFIE_HOME`, then `<current-worktree>/.elfienest.local`.
- `serve` and `start` accept `--data-home PATH`. Lifecycle commands remember
  that selection so `status`, `stop`, and `restart` use the same root. PID and
  lock receipts, `runtime.json`, logs, CLI history, and `nest.db` all follow the
  selected root.
- Tests, workbenches and doc acceptance must use an isolated `ELFIE_HOME` or a
  temporary directory.
- `build/` stores only intermediate artifacts, `dist/` only final release
  artifacts; neither is a source-doc location.

Inside the production root, ownership is split into the Nest layer and the
Elfie layer. `nest.db` stores Nest identity, account/ownership, rooms and
runtime state; each Elfie's profile, memory, work content and chat live under
`elfies/<elfie_id>/`. `elfie_id` is an immutable directory ID; renaming must
never move data. New chat may only be written into
`elfies/<elfie_id>/conversations/history.sqlite`; do not create user chat
directories and do not write copies into `nest.db.chat_messages`.

Developer Tools uses an independent `${ELFIE_DEV_HOME:-~/.elfienest-dev}` with
separate `elfie_lab/`, `nest_lab/`, and `runtime_lab/` children. It must not
read or write the product root by default. `nest.db.chat_messages`
is a deprecated table from the unreleased phase and is deleted on database
upgrade; no compat read or migration entry is kept.

## Keys and external services

- API keys, tokens and passwords are read only from environment variables or
  Git-ignored user configuration.
- Example configuration may only use placeholders like `${API_KEY}` or
  `<your-api-key-here>`.
- Never write real credentials into READMEs, design docs, test fixtures or
  screenshots.

## Public docs boundary

The public site only publishes reviewed product intros, usage guides and
finalized developer notes. Intermediate design drafts, experiment evidence,
unreleased capabilities and private worldbuilding stay outside public docs and
must not be referenced by the VitePress build.

## Change checklist

1. Confirm the new file is not in a private-material or build directory.
2. Search for key patterns and local absolute paths.
3. Check that the docs build output contains no deny-list terms.
4. Run external services with least privilege; do not expose debug ports in
   end-user navigation.
