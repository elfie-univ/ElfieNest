"""真实与 Mock Runtime 的调试适配层。"""

from __future__ import annotations

import re
import shlex
import time
from pathlib import Path
from typing import Any, Dict, List

from runtime.food.bootstrap import build_compatibility_food_catalog
from runtime.food.models import FoodRecipe
from runtime.food.store import FoodCatalog, FoodCatalogStore
from runtime.providers.ollama import OllamaManager
from runtime.storage.data_home import get_elfie_home

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
        return f"我有好好听到你说\u201c{message}\u201d哒。[ACTION]nod_head[/ACTION]"


class TracingRuntimeAgent:
    """记录模型调用，同时保持 `ask` 协议兼容。"""

    def __init__(self, inner: Any, food_key: str):
        self.inner = inner
        self.food_key = food_key
        self.config = inner.config
        self.calls: List[Dict[str, Any]] = []

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        started = time.perf_counter()
        call: Dict[str, Any] = {
            "food_key": self.food_key,
            "prompt": redact_text(prompt),
            "energy": energy,
            "task_complexity": task_complexity,
            "provider": self._provider_name(),
            "model": self._model_name(task_complexity),
        }
        try:
            response = self.inner.ask(prompt, energy, task_complexity)
            call["provider"] = self._provider_name()
            call["model"] = self._model_name(task_complexity)
            runtime_result = getattr(self.inner, "last_result", None)
            if runtime_result is not None:
                call.update(
                    {
                        "food_used": runtime_result.food_used,
                        "execution_stage": runtime_result.execution_stage,
                        "degraded": runtime_result.degraded,
                    }
                )
            call["response"] = redact_text(str(response))
            return response
        except Exception as exc:
            call["provider"] = self._provider_name()
            call["model"] = self._model_name(task_complexity)
            call["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            call["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            self.calls.append(call)

    def _model_name(self, task_complexity: int) -> str:
        if self.food_key == "mock":
            return "elfie-mock"
        if hasattr(self.inner, "selected_model"):
            return str(self.inner.selected_model)
        if task_complexity >= getattr(self.config, "complexity_threshold_deep", 3):
            return str(getattr(self.config, "deep_model", "runtime-selected"))
        return str(getattr(self.config, "cheap_model", "runtime-selected"))

    def _provider_name(self) -> str:
        if self.food_key == "mock":
            return "mock"
        return str(getattr(self.inner, "selected_provider", "runtime_router"))


class FoodRuntimeAgent:
    """让精灵实验通过粮食语义调用 Runtime。"""

    def __init__(self, runtime: Any, food_key: str, recipe: FoodRecipe):
        self.runtime = runtime
        self.config = runtime.config
        self.food_key = food_key
        self.selected_model = recipe.primary.model
        self.selected_provider = _provider_from_model(self.selected_model)
        self.last_result = None

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        result = self.runtime.run_with_food(
            prompt=prompt,
            food_key=self.food_key,
            energy=energy,
            task_complexity=task_complexity,
            allowed_skills=[],
        )
        self.last_result = result
        self.selected_model = str(result.actual_model or result.model_key)
        self.selected_provider = _provider_from_model(self.selected_model)
        return result.text


def create_runtime(food_key: str, config_dir: str | None = None) -> TracingRuntimeAgent:
    normalized = food_key.lower().strip()
    if normalized == "mock":
        return TracingRuntimeAgent(MockRuntimeAgent(), "mock")

    from devtools.runtime_lab import RuntimeLabConfigStore
    from runtime import RuntimeAgent

    store = RuntimeLabConfigStore(config_dir or str(get_elfie_home()))
    config = store.load_runtime_config()
    food_store = runtime_food_catalog_store(store)
    catalog = load_runtime_food_catalog(store, food_store)
    recipe = catalog.recipes.get(normalized)
    if recipe is None:
        raise ValueError(f"Runtime 粮食目录中不存在粮食: {normalized}")

    agent = RuntimeAgent(config)
    agent.food_catalog_store = food_store
    food_agent = FoodRuntimeAgent(agent, normalized, recipe)
    return TracingRuntimeAgent(food_agent, normalized)


def runtime_food_catalog_store(config_store: Any) -> FoodCatalogStore:
    """返回指定 Runtime 根目录下的粮食存储。"""
    return FoodCatalogStore(
        Path(config_store.root) / "foods.yaml",
        Path(config_store.root) / "food_history",
    )


def runtime_lab_command(config_store: Any) -> str:
    """返回操作当前 Runtime 根目录的完整 Runtime Lab 命令。"""
    root_path = Path(config_store.root).expanduser().resolve()
    if root_path == get_elfie_home().expanduser().resolve():
        return ".venv/bin/python -m runtime.lab"
    root = shlex.quote(str(root_path))
    return f"ELFIE_HOME={root} .venv/bin/python -m runtime.lab"


def load_runtime_food_catalog(
    config_store: Any,
    food_store: FoodCatalogStore | None = None,
) -> FoodCatalog:
    """加载 Runtime 粮食目录；尚未生成时按当前配置构造兼容配方。"""
    store = food_store or runtime_food_catalog_store(config_store)
    catalog = store.load()
    if catalog.recipes:
        return catalog
    return build_compatibility_food_catalog(config_store.load_runtime_config())


def list_installed_ollama_models(config: Any) -> tuple[str, ...] | None:
    """返回本机模型；服务不可达时返回 ``None``。"""
    try:
        return OllamaManager(config).list_installed_models()
    except Exception:
        return None


def model_availability(
    model_ref: str,
    config: Any,
    installed_ollama_models: tuple[str, ...] | None,
    configure_command: str,
) -> Dict[str, Any]:
    if not model_ref:
        return {
            "ready": False,
            "reason": "模型尚未配置",
            "command": configure_command,
        }
    provider = _provider_from_model(model_ref)
    model = model_ref.split("/", 1)[1] if "/" in model_ref else model_ref
    if provider == "ollama":
        if installed_ollama_models is None:
            return {
                "ready": False,
                "reason": "Ollama 服务不可用",
                "command": "ollama serve",
            }
        installed = any(
            candidate == model
            or (":" not in model and candidate.split(":", 1)[0] == model)
            for candidate in installed_ollama_models
        )
        return {
            "ready": installed,
            "reason": "" if installed else f"本地模型 {model} 尚未安装",
            "command": "" if installed else f"ollama pull {model}",
        }

    configured = bool(config.providers.get(provider, {}).get("api_key"))
    return {
        "ready": configured,
        "reason": "" if configured else f"Provider {provider} 尚未配置凭据",
        "command": (
            ""
            if configured
            else configure_command
        ),
    }


def _provider_from_model(model_ref: str) -> str:
    if not model_ref:
        return ""
    return model_ref.split("/", 1)[0] if "/" in model_ref else "ollama"
