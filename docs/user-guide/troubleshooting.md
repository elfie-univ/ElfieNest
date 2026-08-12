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

Local Ollama is optional. Setup only reports whether it is installed; the
actual health check happens after final confirmation. The installer reuses the
single public Ollama when it is available, starts it when it is stopped,
repairs it when startup or the health check fails, and installs it when it is
absent. It never creates a second private Ollama instance.

If the model phase fails, use the retry action on the locked Setup page. The
installer rechecks completed phases and does not ask you to re-enter the
configuration.

## Abnormal data directory

Set an isolated `ELFIE_HOME` for this experiment; do not delete the default data
directory:

```bash
ELFIE_HOME=/tmp/elfienest-debug .venv/bin/python main.py
```
