# Troubleshooting

## `uv` command not found

Install uv following its official guide first, then re-run:

```bash
./elfienest.sh
```

## Wrong Python version

The project is pinned to CPython `3.9.25`. Do not reuse other virtual
environments — use `./elfienest.sh` for source development or `./install.sh`
for a complete current-machine installation.

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

Ollama is optional. If you chose it during Setup, check the one saved Ollama
endpoint and its Provider configuration; do not replace it by scanning for a
different local service. You can skip or configure another Provider in Setup.

## Abnormal data directory

Set an isolated `ELFIE_HOME` for this experiment; do not delete the default data
directory:

```bash
ELFIE_HOME=/tmp/elfienest-debug .venv/bin/python main.py
```
