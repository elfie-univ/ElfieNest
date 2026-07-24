# 安装与环境

## 系统前提

- Git
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- 能够下载 CPython `3.9.25` 和项目依赖的网络环境

## 获取源码

```bash
git clone https://github.com/elfie-univ/ElfieNest.git
cd ElfieNest
```

## 准备环境

```bash
./install.sh --env-only
```

如果希望在终端直接使用 `elfienest` 命令：

```bash
./install.sh
```

安装脚本使用 `uv.lock` 准备固定环境。不要用 `sudo`，也不要手工替换 Python 版本。

## 验证

```bash
./elfienest.sh version
```

成功时会显示版本信息并以状态码 `0` 退出。
