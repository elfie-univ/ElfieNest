# 配置模型与数据

## 数据边界

生产配置、数据库、精灵档案和本地密钥统一位于：

```text
${ELFIE_HOME:-~/.elfienest}
```

测试和实验可以指定独立目录：

```bash
ELFIE_HOME=/tmp/elfienest-preview .venv/bin/python main.py
```

不要把日常数据复制进仓库，也不要删除整个用户目录来排查问题。

## 模型入口

模型配置由本地配置和环境变量共同决定。常见 Provider 环境变量包括：

```text
OLLAMA_HOST
OPENAI_API_KEY
DEEPSEEK_API_KEY
GEMINI_API_KEY
QWEN_API_KEY
ZHIPU_API_KEY
MOONSHOT_API_KEY
MINIMAX_API_KEY
```

真实密钥只能放在环境变量或被 Git 忽略的用户配置里。公开文档、源码和命令参数中不写
真实密钥。

### 使用 ChatGPT 账号登录

Provider 页面只显示一张 **OpenAI** 公司卡片。进入后先填写别名并选择连接方式：
**ChatGPT 账号授权（订阅）** 或 **OpenAI API Key（按量计费）**。选择账号授权后，
先生成一次性设备码，再复制代码并打开授权地址。用户电脑不需要安装 Codex。

ElfieNest 会把可刷新的授权凭据保存在 `configs/credentials/oauth/`；
`configs/providers.yaml` 只保存不透明的凭据引用。该连接使用 ChatGPT Codex Responses
通道以及当前 ChatGPT 订阅允许使用的模型，它不是 OpenAI API Key，也不走 API 计费。
当前模型清单是实验性的候选目录，不是从账号实时读取；ElfieNest 会针对当前账号逐个
验证候选模型。后续若引入官方 Codex App Server，可改为使用其 `model/list` 能力。
上游仍把宿主自行管理外部令牌的路径标记为实验能力，因此 OpenAI 后续可能调整授权或
传输要求。

## 没有 Ollama 时

最小示例可以使用内置回退运行时验证基础链路。回退路径用于确认环境和系统连接，不
代表不同模型之间的能力完全相同。
