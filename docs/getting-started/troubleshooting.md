# Troubleshooting

## `uv` command not found

Install uv following its official guide first, then re-run:

```bash
./install.sh
```

## Wrong Python version

The project is pinned to CPython `3.9.25`. Do not reuse other virtual
environments — just re-run the installer.

## Port already in use

First check the services registered by the current project:

```bash
./elfienest.sh status
```

Once you have confirmed they belong to the current project, run:

```bash
./elfienest.sh stop
```

Do not use broad `kill` commands against unknown processes.

## Model connection failure

First validate the basic pipeline with fallback mode:

```bash
./elfienest.sh serve --fallback
```

If fallback mode works, check the Ollama address, the provider configuration and
the environment variables.

## Abnormal data directory

Set an isolated `ELFIE_HOME` for this experiment; do not delete the default data
directory:

```bash
ELFIE_HOME=/tmp/elfienest-debug .venv/bin/python main.py
```
