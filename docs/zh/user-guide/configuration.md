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
```

真实密钥只能放在环境变量或被 Git 忽略的用户配置里。公开文档、源码和命令参数中不写
真实密钥。

## 没有 Ollama 时

最小示例可以使用内置回退运行时验证基础链路。回退路径用于确认环境和系统连接，不
代表不同模型之间的能力完全相同。
