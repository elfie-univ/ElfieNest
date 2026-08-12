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

成功时会显示版本信息并以状态码 `0` 退出。

## 首次 Setup

首次打开应用会进入四步 Setup：

1. 创建 Owner 账号。
2. 配置可选的本地离线保障。启用后复用唯一的公共 Ollama，并从三个受支持的本地模型中
   选择：`qwen2.5:0.5b`（推荐）、`qwen3.5:0.8b` 或 `gemma3:270m`。
3. 设置精灵巢床位数。
4. 汇总四项配置并确认安装。

前三步只保存草稿，不会创建账号、下载或生成任何内容；只有最后确认后才开始执行。确认后
配置会锁定，安装器依次执行 Owner、Ollama、模型、保底粮和精灵巢床位五个可重试阶段。页面
显示一个总进度条和当前阶段，执行期间不提供取消或返回操作。
