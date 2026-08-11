"""Elfie Lab 对公共 Runtime 粮食目录的只读投影。"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Dict

from elfie.brain.food_port import FoodCatalog, FoodPort
from infrastructure.models.providers.ollama import OllamaManager
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.nest_db.store import init_db


def runtime_food_catalog_store(config_store: Any) -> FoodPort:
    """返回指定隔离 Runtime 根目录下的粮食数据库仓储。"""
    root = Path(config_store.root).expanduser().resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    db_path = root / "nest.db"
    init_db(str(db_path))
    return SQLiteFoodAdapter(db_path)


def runtime_lab_command(config_store: Any) -> str:
    """返回操作当前 Runtime 根目录的完整 Runtime Lab 命令。"""
    root_path = Path(config_store.root).expanduser().resolve()
    root = shlex.quote(str(root_path))
    return f"ELFIE_HOME={root} .venv/bin/python -m devtools.runtime_lab"


def load_runtime_food_catalog(
    config_store: Any,
    food_store: FoodPort | None = None,
) -> FoodCatalog:
    """加载 Lab Runtime 隔离数据库中的粮食目录。"""
    store = food_store or runtime_food_catalog_store(config_store)
    return store.load()


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
        return {"ready": False, "reason": "模型尚未配置", "command": configure_command}
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
        "command": "" if configured else configure_command,
    }


def _provider_from_model(model_ref: str) -> str:
    if not model_ref:
        return ""
    return model_ref.split("/", 1)[0] if "/" in model_ref else "ollama"


__all__ = (
    "list_installed_ollama_models",
    "load_runtime_food_catalog",
    "model_availability",
    "runtime_food_catalog_store",
    "runtime_lab_command",
)
