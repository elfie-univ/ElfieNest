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
```

Real keys may only live in environment variables or Git-ignored user
configuration. Never write real keys into public docs, source code or command
arguments.

## Without Ollama

The minimal example can use the built-in fallback runtime to validate the basic
pipeline. The fallback path confirms that the environment and system wiring are
correct; it does not mean different models are interchangeable in capability.
