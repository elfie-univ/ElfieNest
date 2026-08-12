<div align="center">
  <table border="0">
    <tr>
      <td align="center" valign="middle" style="border: none;">
        <img src="docs/public/assets/logo.png" alt="ElfieNest Logo" width="115" />
      </td>
      <td align="left" valign="middle" style="border: none;">
        <pre>
███████╗██╗     ███████╗██╗███████╗     ███╗   ██╗███████╗███████╗████████╗
██╔════╝██║     ██╔════╝██║██╔════╝     ████╗  ██║██╔════╝██╔════╝╚══██╔══╝
█████╗  ██║     █████╗  ██║█████╗       ██╔██╗ ██║█████╗  ███████╗   ██║
██╔══╝  ██║     ██╔══╝  ██║██╔══╝       ██║╚██╗██║██╔══╝  ╚════██║   ██║
███████╗███████╗██║     ██║███████╗     ██║ ╚████║███████╗███████║   ██║
╚══════╝╚══════╝╚═╝     ╚═╝╚══════╝     ╚═╝  ╚═══╝╚══════╝╚══════╝   ╚═╝
        </pre>
      </td>
    </tr>
  </table>

  <p><strong>🦊 Embodied AI Creature Simulation — 仿生生命体系统</strong></p>

  <p>
    <a href="README_zh.md">简体中文</a> · English
  </p>
</div>

An open-source embodied AI creature project: every Elfie carries its own profile,
perception, emotion, energy, memory, body and a typed cognitive loop, and lives
inside a Nest world rendered by Godot.

In 2026, while parsing an anomalous deep-space signal, [the Creator] captured a
wormhole transmission from Elfaria. To keep that fragile channel stable, they
built the first ElfieNest on Earth — a private station bridging two worlds. On
the other side, beings called Elfie are signing up for the "Earthbound Program".
They want to understand Earth, meet humans, and find a home they can share.

Now you can host your own ElfieNest on your own computer and adopt the first
Elfie willing to come to you.

Start at the [documentation home](https://elfienest.dev/), then move through
[World & Story](docs/story/index.md), [Getting Started](docs/getting-started/index.md),
and the [Developer Docs](docs/developer/index.md) layer by layer.

> 中文版请阅读 [README_zh.md](README_zh.md)。

## What the project is made of

- A stable profile, three-layer brain, memory, emotion, energy, nervous system
  and a swappable body for each individual Elfie;
- Body and Communication each feed the perceptual workspace, the cognitive
  coordinator forms a typed decision, then routes it to body, communication or
  internal effectors;
- A Nest that only holds resident IDs and in-nest semantic state, plus a Godot
  project that owns rooms, geometry, motion, collision and rendering;
- Model, Food and tool runtime capabilities, a product application layer, an Electron desktop
  host and isolated module workbenches.

## Core experience

ElfieNest is not about making a model return one chat message. It is about
keeping perception, thought and action flowing along clear boundaries:

```text
Body / Communication
        ↓
PerceptualWorkspace
        ↓
BrainCoordinator → DecisionPlan
        ↓
OutputRouter → body / communication / internal state
        ↓
ExecutionReceipt flows back into the perceptual workspace
```

The physical clock does not wait for model inference to finish. A real Elfie
and a Nest are combined only in the application orchestration layer. Godot
remains the single source of truth for space and rendering.

## Quick start

Development mode is separate from installation. A source contributor uses the
pinned CPython `3.9.25` and `uv.lock` through this entry point:

```bash
./elfienest.sh version
.venv/bin/python main.py
```

`main.py` runs a three-tick local demo. Public Ollama is optional: Setup can
skip it or bind one chosen endpoint, but the application never silently bundles
or installs a private engine or model weights.

To build the current source as a native application for this machine and install
the user-level `elfienest` command, run:

如需把当前源码构建为本机原生应用，并安装当前用户可直接调用的 `elfienest` 命令：

```bash
./install.sh
elfienest version
```

The installer supports user-level installation only — do not run it as `root`
or with `sudo`. For the full set of prerequisites, error handling and platform
notes, see [Getting Started](docs/getting-started/index.md).

Manual native packages and a future verified remote bootstrap enter the same
installed runtime. The bootstrap contract is locally tested, but its public URL
is not live yet.

## Documentation entry points

- [Documentation home](docs/index.md): project intro and reading entry;
- [World & Story](docs/story/index.md): for first-time readers of ElfieNest;
- [Getting Started](docs/getting-started/index.md): build and run a Nest from
  source;
- [Developer Docs](docs/developer/index.md): architecture, workflow and tooling;
- [Current architecture](docs/developer/architecture/index.md): module boundaries and
  information flow;
- [Commands & dev tools](docs/developer/tooling.md): CLI, workbenches, Godot and
  build entry points.

The docs site is built with VitePress. The site source contains only finalized
documents intended for the public; historical designs, process evidence and
unrevealed worldbuilding material are not part of the public site.

## Contributing

Before changing anything, please read:

- [Contributing guide](CONTRIBUTING.md): environment, tests, quality gates and
  collaboration flow;
- [Security policy](SECURITY.md): vulnerability reporting and key handling;
- [Project rules](AGENTS.md): directory boundaries and engineering constraints
  that apply to both humans and coding agents;
- [Code of conduct](CODE_OF_CONDUCT.md): community collaboration boundaries.

Common dev checks:

```bash
uv sync --locked --extra dev
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_baseline.py
```

Test paths, Desktop and Godot build commands are maintained separately by the
[test guide](test/README.md), [Desktop guide](app/interfaces/desktop/README.md) and
[Godot guide](godot_project/README.md).

## Minimal directory map

| Directory | Responsibility |
| --- | --- |
| [`elfie/`](elfie/README.md) | One complete Elfie: profile, brain, body, communication and skills |
| [`nest/`](nest/README.md) | Activity-space state, environment clock, interaction, Godot protocol boundary |
| `infrastructure/` | Model, tool, persistence, Godot, device, communication and platform adapters |
| [`app/`](app/README.md) | Product use-cases, interfaces, infrastructure and cross-module orchestration |
| [`app/interfaces/desktop/`](app/interfaces/desktop/README.md) | Visible Electron windows, system integration and the public Runtime lifecycle client |
| [`godot_project/`](godot_project/README.md) | Standalone Godot source project: rooms, geometry, coordinates, collision, characters and rendering |
| [`devtools/`](devtools/README.md) | Module workbenches isolated from the end-user product |
| [`scripts/`](scripts/README.md) | Launch, build, check and manual diagnosis entry points |
| [`test/`](test/README.md) | Tests mirroring source boundaries, architecture contracts and E2E |
| [`docs/`](docs/index.md) | VitePress public documentation site source |

The full dependency direction, process boundaries, `ELFIE_HOME` data boundary,
and the `build/` / `dist/` artifact rules live in the
[developer architecture doc](docs/developer/architecture/index.md).

## License

ElfieNest is released under the [Apache License 2.0](LICENSE).
