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
