# ElfieNest CLI 使用指南

## 两种使用方式

### 方式 1: 本地运行（开发模式）

直接运行 `elfie.sh`，无需安装：

```bash
# 进入交互式命令行
./elfie.sh

# 或直接使用命令
./elfie.sh serve --fallback   # 启动服务
./elfie.sh config             # 配置系统
./elfie.sh status             # 查看状态
./elfie.sh models             # 查看模型
```

### 方式 2: 用户安装（日常使用）

安装到系统，全局可用：

```bash
# 安装
./install.sh

# 使用
elfie                    # 进入交互式命令行
elfie serve --fallback   # 启动服务
elfie config             # 配置系统
elfie status             # 查看状态
```

## 交互式命令行

直接运行 `./elfie.sh` 会显示：

```
                                    ▄     
  █▀▀█ █▀▀█ █▀▀█ █▀▀▄ █▀▀▀ █▀▀█ █▀▀█ █▀▀█ 
  █  █ █  █ █▀▀▀ █  █ █    █  █ █  █ █▀▀▀ 
  ▀▀▀▀ █▀▀▀ ▀▀▀▀ ▀  ▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ 

  🦊 仿生生命体系统 v1.0.0

elfie> 
```

输入命令进行操作：

```
elfie> help              # 查看帮助
elfie> serve --fallback  # 启动服务
elfie> status            # 查看状态
elfie> config            # 配置系统
elfie> exit              # 退出
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
./elfie.sh

# 3. 启动服务
elfie> serve --fallback

# 4. 访问
# http://localhost:8000/static/login.html
# 默认账号: admin / adminchangeme
```

### 用户模式

```bash
# 1. 安装
./install.sh

# 2. 进入交互式命令行
elfie

# 3. 启动服务
elfie> serve --fallback
```

## 安装说明

### 用户安装（不需要 sudo）

```bash
./install.sh
```

安装到 `~/bin/elfie`，如果 `~/bin` 不在 PATH 中，会提示添加：

```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 系统安装（需要 sudo）

```bash
sudo ./install.sh
```

安装到 `/usr/local/bin/elfie`，所有用户都可以使用。

### 卸载

```bash
uninstall-elfie
```

## 端口冲突处理

当端口被占用时：

```bash
# 方法 1: 强制重启
./elfie.sh serve --force
# 或
elfie serve --force

# 方法 2: 使用其他端口
./elfie.sh serve --port 8001 --ws-port 8767
```

## 配置示例

### 配置大模型

```bash
elfie> config
# 选择 "2. 配置大模型 (LLM)"
# 设置轻量模型: qwen3.5:0.8b
# 设置深度模型: qwen2.5:7b
# 选择服务商: ollama
```

### 配置引擎参数

```bash
elfie> config
# 选择 "3. 配置引擎参数"
# 设置 Tick 间隔: 1.5 秒
# 启用/禁用 TTS
# 设置房间精灵上限: 10
```

## 常见问题

### Q: 本地运行 vs 用户安装，选哪个？

- **本地运行**：如果你在开发 ElfieNest，用 `./elfie.sh`
- **用户安装**：如果你只是使用 ElfieNest，用 `./install.sh` 安装

### Q: 如何进入交互式命令行？

```bash
./elfie.sh        # 本地运行
# 或
elfie             # 安装后
```

### Q: 如何查看服务是否运行？

```bash
elfie> status
# 或
./elfie.sh status
```

### Q: 如何查看有多少精灵？

```bash
elfie> stats
```

### Q: 端口被占用怎么办？

```bash
elfie> serve --force
```

### Q: 如何备份数据？

```bash
elfie> db backup
```

### Q: 如何查看日志？

```bash
elfie> logs
```

## 环境变量配置

```bash
# OpenAI
export OPENAI_API_KEY='sk-xxx'

# DeepSeek
export DEEPSEEK_API_KEY='sk-xxx'

# Gemini
export GEMINI_API_KEY='xxx'

# 通义千问
export QWEN_API_KEY='sk-xxx'
```
