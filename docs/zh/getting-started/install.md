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

## 三种安装方式

开发模式不属于安装方式。源码开发者在 checkout 中运行 `./elfienest.sh`，它会检查并补齐
开发依赖，然后进入交互菜单。

从源码为当前机器安装：

```bash
./install.sh
```

`install.sh` 使用 `uv.lock` 准备固定环境，构建当前平台的原生应用并安装全局
`elfienest` 命令。不要用 `sudo`，也不要手工替换 Python 版本。

另外两种正式安装方式与它进入相同的已安装运行态：下载当前平台的原生安装包并双击安装；
或使用未来的远程 bootstrap 自动下载经校验的原生包。后者的本地契约已验证，但正式 URL
尚未上线，当前不能作为可复制下载命令。

## 验证

```bash
elfienest version
```

成功时会显示版本信息并以状态码 `0` 退出。首次打开应用进入五步 Setup：创建 Owner、
选择可选的公共 Ollama、设置 4–32 个床位、配置或跳过模型与粮食、确认完成。
