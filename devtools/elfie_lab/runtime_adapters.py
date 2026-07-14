"""真实与 Mock Runtime 的调试适配层。"""

import re
import time
from typing import Any, Dict, List

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{12,}", re.IGNORECASE),
)


def redact_text(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("<redacted>", result)
    return result


class MockRuntimeAgent:
    """可离线、可预期的开发者模式。"""

    class MockConfig:
        providers = {
            "ollama": {"api_key": "", "api_base": "mock://local"},
            "openai": {"api_key": "", "api_base": ""},
            "deepseek": {"api_key": "", "api_base": ""},
            "gemini": {"api_key": "", "api_base": ""},
            "qwen": {"api_key": "", "api_base": ""},
        }
        cheap_model = "elfie-mock"
        deep_model = "elfie-mock"

    config = MockConfig()

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        match = re.search(r"【主人发送的信息】:\s*(.+?)\n\n", prompt, re.DOTALL)
        message = match.group(1).strip() if match else "这件事"
        if len(message) > 28:
            message = message[:28] + "…"
        return f"我有好好听到你说“{message}”哒。[ACTION]nod_head[/ACTION]"


class TracingRuntimeAgent:
    """记录模型调用，同时保持 `ask` 协议兼容。"""

    def __init__(self, inner: Any, mode: str):
        self.inner = inner
        self.mode = mode
        self.config = inner.config
        self.calls: List[Dict[str, Any]] = []

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        started = time.perf_counter()
        call: Dict[str, Any] = {
            "mode": self.mode,
            "prompt": redact_text(prompt),
            "energy": energy,
            "task_complexity": task_complexity,
            "provider": self._provider_name(),
            "model": self._model_name(task_complexity),
        }
        try:
            response = self.inner.ask(prompt, energy, task_complexity)
            call["response"] = redact_text(str(response))
            return response
        except Exception as exc:
            call["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            call["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            self.calls.append(call)

    def _model_name(self, task_complexity: int) -> str:
        if self.mode == "mock":
            return "elfie-mock"
        if hasattr(self.inner, "selected_model"):
            return str(self.inner.selected_model)
        if task_complexity >= getattr(self.config, "complexity_threshold_deep", 3):
            return str(getattr(self.config, "deep_model", "runtime-selected"))
        return str(getattr(self.config, "cheap_model", "runtime-selected"))

    def _provider_name(self) -> str:
        if self.mode == "mock":
            return "mock"
        return str(getattr(self.inner, "selected_provider", "runtime_router"))


class ConfiguredRuntimeAgent:
    """让精灵实验固定使用开发配置选定的 Runtime 模型槽位。"""

    def __init__(self, runtime: Any, model_key: str, provider: str, model: str):
        self.runtime = runtime
        self.config = runtime.config
        self.model_key = model_key
        self.selected_provider = provider
        self.selected_model = model

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        return self.runtime.generate(
            model_key=self.model_key,
            messages=[{"role": "user", "content": prompt}],
            allowed_skills=[],
            max_loops=1,
        )


def create_runtime(mode: str, config_dir: str | None = None) -> TracingRuntimeAgent:
    normalized = mode.lower().strip()
    if normalized == "mock":
        return TracingRuntimeAgent(MockRuntimeAgent(), "mock")
    if normalized != "real":
        raise ValueError("运行模式只能是 mock 或 real")

    from devtools.runtime_lab import RuntimeLabConfigStore
    from runtime import RuntimeAgent

    store = RuntimeLabConfigStore(config_dir)
    config = store.load_runtime_config()
    status = store.status()
    if not status["ready_for_attempt"]:
        raise RuntimeError(
            f"开发 Runtime 尚未配置可用凭据；请运行 {status['setup_command']}"
        )
    configured = ConfiguredRuntimeAgent(
        RuntimeAgent(config),
        str(status["model_key"]),
        str(status["provider"]),
        str(status["model"]),
    )
    return TracingRuntimeAgent(configured, "real")
