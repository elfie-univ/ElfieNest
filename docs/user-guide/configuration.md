# Configure models & data

## Data boundary

Production configuration, databases, Elfie profiles and local keys all live
under:

```text
${ELFIE_HOME:-~/.elfienest}
```

For tests and experiments you can point at an isolated directory:

```bash
ELFIE_HOME=/tmp/elfienest-preview .venv/bin/python main.py
```

Do not copy day-to-day data into the repository, and do not delete the entire
user directory to debug an issue.

## Model entry points

Model configuration is decided jointly by local configuration and environment
variables. Common provider environment variables include:

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

Real keys may only live in environment variables or Git-ignored user
configuration. Never write real keys into public docs, source code or command
arguments.

### Sign in with a ChatGPT account

The Provider page displays one **OpenAI** company card. Enter a name and choose
either **ChatGPT account (subscription)** or **OpenAI API key (usage-based)**.
For account authorization, generate a one-time device code first, copy it, then
open the authorization page. Codex does not need to be installed on the computer.

ElfieNest stores the resulting refreshable credential under
`configs/credentials/oauth/`; `configs/providers.yaml` contains only an opaque
credential reference. This connection uses the ChatGPT Codex Responses
transport and the models allowed by the signed-in ChatGPT subscription. It is
not an OpenAI API key or API-billing connection. The host-managed external-token
path is still experimental upstream, so OpenAI may change its authorization or
transport requirements. The current model list is an experimental candidate
catalog, not a live account model list; ElfieNest verifies candidates against the
signed-in account. A future Codex App Server integration can use its `model/list`
capability instead.

## Without Ollama

The minimal example can use the built-in fallback runtime to validate the basic
pipeline. The fallback path confirms that the environment and system wiring are
correct; it does not mean different models are interchangeable in capability.
