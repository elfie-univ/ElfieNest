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

## Prepare the environment

```bash
./install.sh --env-only
```

If you want the `elfienest` command available in your terminal:

```bash
./install.sh
```

The installer uses `uv.lock` to prepare a pinned environment. Do not use
`sudo`, and do not manually swap the Python version.

## Verify

```bash
./elfienest.sh version
```

On success it prints version information and exits with status code `0`.
