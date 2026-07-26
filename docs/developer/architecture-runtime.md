# Runtime & data

## Process relationships

```text
Electron Desktop
  ├─ Python Core
  ├─ Ollama or other provider
  └─ Godot Web Runtime
```

Desktop owns windows, resources and process supervision; the Python Core owns
the product, Elfie, Nest and Runtime; Godot owns spatial facts and rendering;
the model service owns inference capability.

## Data directories

| Type | Location | Committed? |
| --- | --- | --- |
| User configuration, databases, Elfie profiles, local keys | `${ELFIE_HOME:-~/.elfienest}` | No |
| Reproducible intermediate artifacts | `build/` | No |
| Final release artifacts | `dist/` | No |
| Public documentation source | `docs/` | Yes |
| Historical and private process material | `.omo/`, `.agents/knowledge/` | No |

## Production directory contract

A single computer has only one production Nest root:
`${ELFIE_HOME:-~/.elfienest}`. The root holds Nest-level facts: `config.yaml`,
`.env`, `foods.yaml`, `nest.db`, backups, runtime state and logs. `nest.db`
only stores accounts, permissions, Elfie registration/ownership, the Nest world
and runtime state; it no longer accepts new chat messages.

Each Elfie uses an immutable `elfie_id` as its workspace name. Display names may
change, but the directory must never move:

```text
${ELFIE_HOME:-~/.elfienest}/
├── nest.db                         # Nest, accounts, ownership and world state
├── config.yaml / .env / foods.yaml # local production config and key references
└── elfies/
    └── <elfie_id>/                 # stable ID, never a mutable name
        ├── profile.yaml and other profile, memory and work content
        └── conversations/
            └── history.sqlite      # all local-channel chat for this Elfie
```

`history.sqlite` records sessions, channels, senders, user relationships, text,
metadata and attachment references. It does not build user-view local chat
copies, and it does not stuff attachment binaries into the database. Channels
such as web, desktop, WeChat or Feishu all write into this one workspace under
the owning Elfie.

## Development boundary

Developer Tools defaults to an independent root
`${ELFIE_DEV_HOME:-~/.elfienest-dev}`; the `elfie_lab/`, `nest_lab/` and
`runtime_lab/` underneath must never fall back to reading the production root.
Tests should set both a temporary `ELFIE_HOME` and `ELFIE_DEV_HOME`.

`nest.db.chat_messages` is a deprecated table left over from the unreleased
phase. A database upgrade deletes it outright; no compat read, copy or migration
path is provided. New chat lives only inside the corresponding Elfie workspace.

## Internal contracts

Pydantic models are the single source of truth for internal data structures.
When the code needs one, it can call `model_json_schema()` at runtime; the repo
does not maintain a second JSON Schema file.
