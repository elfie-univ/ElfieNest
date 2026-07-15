# ElfieNest CLI 使用指南

## 两种使用方式

### 方式 1: 本地运行（开发模式）

直接运行 `elfienest.sh`，无需安装：

```bash
# 进入交互式命令行
./elfienest.sh

# 或直接使用命令
./elfienest.sh serve --fallback   # 启动服务
./elfienest.sh config             # 配置系统
./elfienest.sh status             # 查看状态
./elfienest.sh models             # 查看模型
```

### 方式 2: 用户安装（日常使用）

安装到系统，全局可用：

```bash
# 安装
./install.sh

# 使用
elfienest                    # 进入交互式命令行
elfienest serve --fallback   # 启动服务
elfienest config             # 配置系统
elfienest status             # 查看状态
```

## 交互式命令行

直接运行 `./elfienest.sh` 会显示：

```
                                    ▄     
  █▀▀█ █▀▀█ █▀▀█ █▀▀▄ █▀▀▀ █▀▀█ █▀▀█ █▀▀█ 
  █  █ █  █ █▀▀▀ █  █ █    █  █ █  █ █▀▀▀ 
  ▀▀▀▀ █▀▀▀ ▀▀▀▀ ▀  ▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ 

  🦊 仿生生命体系统 v1.0.0

elfienest>
```

输入命令进行操作：

```
elfienest> help              # 查看帮助
elfienest> serve --fallback  # 启动服务
elfienest> status            # 查看状态
elfienest> config            # 配置系统
elfienest> exit              # 退出
```

## 命令列表

### 服务管理

```bash
serve              # 启动服务（前台运行）
serve --fallback   # 使用内置引擎（不连 Ollama）
serve --force      # 强制重启（杀死占用端口的进程）
serve --port 8001  # 使用其他端口
restart            # 重启服务
stop               # 停止服务
status             # 查看服务状态
```

### 配置管理

```bash
config             # 交互式配置 TUI
models             # 列出可用模型
providers          # 管理 providers
setup              # 首次设置向导
```

### 监控和调试

```bash
stats              # 显示使用统计
session            # 管理会话
logs               # 查看日志
version            # 显示版本
```

### 数据库工具

```bash
db                 # 数据库信息
db backup          # 备份数据库
db reset           # 重置数据库
```

### 其他

```bash
web                # 启动服务并打开浏览器
help               # 显示帮助
exit               # 退出交互式命令行
```

## 快速开始

### 开发模式

```bash
# 1. 克隆代码
git clone https://github.com/xxx/ElfieNest.git
cd ElfieNest

# 2. 进入交互式命令行
./elfienest.sh

# 3. 启动服务
elfienest> serve --fallback

# 4. 访问
# http://localhost:8000/static/login.html
# 默认账号: admin / adminchangeme
```

### 用户模式

```bash
# 1. 安装
./install.sh

# 2. 进入交互式命令行
elfienest

# 3. 启动服务
elfienest> serve --fallback
```

## 安装说明

### Python 运行环境

项目统一使用 CPython `3.9.25`。版本由 `.python-version` 和
`pyproject.toml` 双重约束，依赖由 `uv.lock` 锁定；不要修改系统全局的
`python3`，项目环境只保存在仓库的 `.venv` 中。

首次使用需要安装 `uv`：

```bash
# macOS
brew install uv

# 检查 uv
uv --version
```

随后运行 `./install.sh`。安装脚本会自动下载 CPython `3.9.25`，每次都按
`uv.lock` 同步 `.venv`，并拒绝使用其他 Python 版本或 Python 实现。
直接运行 `./elfienest.sh` 时，如环境缺失，也只会自动修复项目 `.venv`，
不会顺带安装全局命令。

开发者需要测试和检查工具时，执行：

```bash
uv sync --locked --extra dev
source .venv/bin/activate
python --version  # Python 3.9.25
```

### 用户安装（不需要 sudo）

```bash
./install.sh
```

默认安装到 `~/.local/bin/elfienest`。如果目录不在 PATH 中，安装脚本会
提示添加：

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

安装器只允许当前用户安装，并明确拒绝 `root` 或 `sudo`。这是因为生成的
命令会指向当前 checkout；把它安装到系统目录会让其他用户执行一个仍可被
checkout 所有者修改的入口。

### 从旧版 sudo 安装迁移

旧版本可能把 `elfie` 和 `uninstall-elfie` 安装到了 `/usr/local/bin`。
新版安装器不会自动修改系统目录。先以普通用户运行 `./install.sh`，确认
`elfienest version` 正常后，再按安装器提示清理精确匹配的旧入口：

```bash
sudo rm -f -- /usr/local/bin/elfie /usr/local/bin/uninstall-elfie
```

安装后的 `elfienest` 会记录当前 checkout 的绝对路径。移动或删除仓库前，
先运行 `uninstall-elfienest`；移动完成后在新目录重新运行 `./install.sh`。

### 卸载

```bash
uninstall-elfienest
```

## 端口冲突处理

当端口被占用时：

```bash
# 方法 1: 强制重启
./elfienest.sh serve --force
# 或
elfienest serve --force

# 方法 2: 使用其他端口
./elfienest.sh serve --port 8001 --ws-port 8767
```

## 配置示例

### 配置大模型

```bash
elfienest> config
# 选择 "2. 配置大模型 (LLM)"
# 设置轻量模型: qwen3.5:0.8b
# 设置深度模型: qwen2.5:7b
# 选择服务商: ollama
```

### 配置引擎参数

```bash
elfienest> config
# 选择 "3. 配置引擎参数"
# 设置 Tick 间隔: 1.5 秒
# 启用/禁用 TTS
# 设置房间精灵上限: 10
```

## 常见问题

### Q: 本地运行 vs 用户安装，选哪个？

- **本地运行**：如果你在开发 ElfieNest，用 `./elfienest.sh`
- **用户安装**：如果你只是使用 ElfieNest，用 `./install.sh` 安装

### Q: 如何进入交互式命令行？

```bash
./elfienest.sh        # 本地运行
# 或
elfienest             # 安装后
```

### Q: 如何查看服务是否运行？

```bash
elfienest> status
# 或
./elfienest.sh status
```

### Q: 如何查看有多少精灵？

```bash
elfienest> stats
```

### Q: 端口被占用怎么办？

```bash
elfienest> serve --force
```

### Q: 如何备份数据？

```bash
elfienest> db backup
```

### Q: 如何查看日志？

```bash
elfienest> logs
```

## 环境变量配置

如需指定一个已经安装好的 CPython `3.9.25`，可以在安装时设置：

```bash
ELFIENEST_PYTHON=/path/to/python3.9 ./install.sh
```

模型服务密钥继续通过环境变量或已被 Git 忽略的本地配置提供：

```bash
# OpenAI
export OPENAI_API_KEY='<your-openai-api-key>'

# DeepSeek
export DEEPSEEK_API_KEY='<your-deepseek-api-key>'

# Gemini
export GEMINI_API_KEY='<your-gemini-api-key>'

# 通义千问
export QWEN_API_KEY='<your-qwen-api-key>'
```
