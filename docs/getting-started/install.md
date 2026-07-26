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

## Install / 安装

```bash
./install.sh
```

The installer uses `uv.lock` to prepare a pinned environment, builds a native
application for the current machine, and installs the global `elfienest`
command. Do not use `sudo` or manually swap the Python version.

安装器会使用 `uv.lock` 准备固定环境，在当前机器构建原生应用，并安装全局
`elfienest` 命令。不要用 `sudo`，也不要手工替换 Python 版本。

## Verify

```bash
elfienest version
```

On success it prints version information and exits with status code `0`.
