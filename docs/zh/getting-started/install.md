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

## 唯一开发路径

源码开发不属于安装方式。在 checkout 中运行唯一开发入口：

```bash
./elfienest.sh
```

它会先检查锁定的开发环境，再进入产品菜单。

## 恰好三种安装方式

1. **当前机器的源码安装。** 在 checkout 中运行 `./install.sh`，为当前用户安装当前
   原生 target。
2. **手动原生安装包。** 从获授权的分发渠道取得与当前平台匹配的安装包，再按该平台的
   常规安装流程完成安装。
3. **远程校验 bootstrap。** 此方式保留给已经发布的 bootstrap endpoint：它下载并校验
   匹配的原生产物。当前没有公开 bootstrap 命令。

三种安装方式都面向同一 Runtime 产物契约。本页不表示当前存在任何可用安装包。

从源码为当前机器安装：

```bash
./install.sh
```

`install.sh` 使用 `uv.lock` 准备固定环境，并为当前用户安装全局 `elfienest` 命令。
不要用 `sudo`，也不要手工替换 Python 版本。

## 验证

```bash
elfienest version
```

成功时会显示版本信息并以状态码 `0` 退出。首次打开应用进入五步 Setup：创建 Owner、
选择可选的公共 Ollama、设置 4–32 个床位、配置或跳过模型与粮食、确认完成。
