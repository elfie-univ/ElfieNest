# Install & environment

## Prerequisites

- Git
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A network connection that can download CPython `3.9.25` and the project
  dependencies

## Get the source

```bash
git clone https://github.com/elfie-univ/ElfieNest.git
cd ElfieNest
```

## One development path

Source development is not an installation method. In a checkout, run the one
development entry point:

```bash
./elfienest.sh
```

It checks the locked development environment before opening the product menu.

## Exactly three installation methods

1. **Source installation on the current machine.** Use `./install.sh` from a
   checkout; it installs the current native target for the current user.
2. **Manual native installer.** Obtain the installer matching the current
   platform from an authorized distribution channel, then use that platform's
   normal installer flow.
3. **Verified remote bootstrap.** This method is reserved for a published
   bootstrap endpoint that downloads and verifies the matching native artifact.
   No public bootstrap command is available yet.

All three installation methods target the same Runtime artifact contract. This
page does not assert that any particular installer is currently available.

## Source installation

```bash
./install.sh
```

The installer uses `uv.lock` to prepare a pinned environment and installs the
global `elfienest` command for the current user. Do not use `sudo` or manually
swap the Python version.

## Verify

```bash
elfienest version
```

On success it prints version information and exits with status code `0`.

## First-run Setup

The first launch opens a four-step Setup wizard:

1. Create the Owner account.
2. Configure optional local offline support. This keeps the single public
   Ollama installation enabled when selected and lets you choose one of the
   three supported local models: `qwen2.5:0.5b` (recommended),
   `qwen3.5:0.8b`, or `gemma3:270m`.
3. Set the Elfie Nest bed count.
4. Review the four saved choices and confirm installation.

The first three steps only save a draft. Nothing is created, downloaded, or
generated until the final confirmation. After confirmation, the configuration
is locked and the installer runs five retryable phases: Owner, Ollama, model,
emergency food, and Nest beds. The page shows one overall progress bar and
the current phase. It does not provide a cancel or back action while these
phases are running.
