# 开始使用

这条路径帮助你从源码运行 ElfieNest 当前的开发者预览。它不会假设已经存在正式
桌面安装包，也不会把未经验证的平台写成“支持”。

## 当前状态

ElfieNest 目前没有公开发布的 Windows、macOS 或 Linux 桌面安装包。当前唯一
可核验的主路径是获取源码、准备锁定的 Python 环境，然后运行基础演示。

| 环境 | 当前验证状态 |
| --- | --- |
| Ubuntu | CI 验证环境安装与版本入口 |
| macOS | CI 验证环境安装与版本入口 |
| Windows | 当前 CI 尚未验证 |

仓库包含跨平台 Desktop 源码与资源布局，但这不等于对应安装包已经发布。

## 系统前提

开始前需要：

- Git；
- [uv](https://docs.astral.sh/uv/getting-started/installation/)；
- 能够下载 CPython 和项目依赖的网络环境。

项目固定使用 CPython `3.9.25`。安装脚本会通过 uv 准备这个精确版本，不使用
系统 Python 代替。

## 获取源码

```bash
git clone https://github.com/elfie-univ/ElfieNest.git
cd ElfieNest
```

后续命令都从仓库根目录运行。

## 安装

只为当前源码树准备环境：

```bash
./install.sh --env-only
```

安装当前用户可直接调用的 `elfienest` 命令：

```bash
./install.sh
```

两种方式都使用 `uv.lock`。安装脚本只支持用户级安装，请不要使用 `root` 或
`sudo`。

## 验证安装

如果使用源码树内入口：

```bash
./elfienest.sh version
```

如果执行了完整用户安装：

```bash
elfienest version
```

成功时会显示 ElfieNest 版本信息并以状态码 `0` 退出。

## 运行最小示例

```bash
.venv/bin/python main.py
```

这个示例会创建一只 Elfie，模拟一次巢内互动并推进三次 tick，然后主动关闭本地
通信服务。

没有可用的 Ollama 服务时，Runtime 可以进入回退路径，用来验证基本生命循环。
它不等同于完整模型体验；运行这条最短路径也不要求你填写 API Key。

## 常见问题

### 找不到 uv

安装器会明确提示缺少 uv。请从 uv 官方安装说明完成安装，再重新运行
`./install.sh --env-only`；不要改用 `sudo`。

### Python 版本不一致

不要手工把项目切换到其他 Python 版本。重新执行环境安装命令，让 uv 按
`.python-version` 和 `pyproject.toml` 准备 CPython `3.9.25`。

### 依赖下载失败

先检查网络和包索引是否可访问，然后重试安装。不要删除 `uv.lock`，也不要通过
修改依赖版本绕过一次临时网络故障。

### Ollama 没有运行

最小示例可以使用回退路径。需要检查完整 Runtime 配置时，运行：

```bash
./elfienest.sh doctor
```

API Key 只能放在环境变量或 Git 已忽略的本地配置中，不要写进源码、命令参数或
公开文档。

### 担心影响日常数据

测试或实验时使用独立目录：

```bash
ELFIE_HOME=/tmp/elfienest-preview .venv/bin/python main.py
```

不要通过删除 `~/.elfienest/` 来排查安装问题。

## 下一步

- 想继续读故事：前往[世界观与故事](/story/)；
- 想理解架构：阅读[当前架构](/developer/architecture)；
- 想调试模块或贡献代码：进入[开发者文档](/developer/)。
