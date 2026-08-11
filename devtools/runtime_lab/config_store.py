"""与正式运行环境隔离的 Runtime 开发配置存储。"""

import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ai_runtime.config import LLMRuntimeConfig
from infrastructure.models.providers.profiles import BUILTIN_PROFILES
from infrastructure.persistence.data_home import get_elfie_developer_home

SECRET_ENV_KEYS = {
    provider_id: profile.api_key_env_var
    for provider_id, profile in BUILTIN_PROFILES.items()
    if profile.api_key_env_var
}

PROVIDER_DEFAULTS: Dict[str, Dict[str, str]] = {
    name: {
        "display_name": profile.name,
        "api_base": profile.api_base,
        "api_mode": profile.api_mode,
        "test_model": profile.test_model,
        "vision_model": profile.test_model,
    }
    for name, profile in BUILTIN_PROFILES.items()
}
PROVIDER_DEFAULTS["custom_openai"] = {
    "display_name": "自定义 OpenAI 兼容服务",
    "api_base": "http://localhost:8000/v1",
    "api_mode": "chat_completions",
    "test_model": "custom-model",
}


class RuntimeLabConfigStore:
    """开发工具共享配置；不会读取或写入正式 ``~/.elfienest`` 配置。"""

    def __init__(self, root: Optional[str] = None):
        configured = root or os.getenv("ELFIE_LAB_RUNTIME_DIR")
        self.root = (
            Path(configured)
            if configured
            else get_elfie_developer_home() / "runtime_lab"
        )
        self.config_path = self.root / "config.yaml"
        self.env_path = self.root / ".env"

    def ensure_defaults(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._chmod(self.root, 0o700)
        if not self.config_path.exists():
            self._write_yaml(self.default_document())

    def default_document(self) -> Dict[str, Any]:
        providers = {name: dict(values) for name, values in PROVIDER_DEFAULTS.items()}
        return {
            "config_version": 1,
            "providers": providers,
            "cheap_provider": "ollama",
            "cheap_model": providers["ollama"]["test_model"],
            "deep_provider": "ollama",
            "deep_model": providers["ollama"]["test_model"],
            "multimodal_provider": "ollama",
            "multimodal_model": providers["ollama"]["vision_model"],
            "ollama_host": providers["ollama"]["api_base"],
            "ollama_model_fast": providers["ollama"]["test_model"],
            "ollama_model_vision": providers["ollama"]["vision_model"],
            "runtime_policy": {"elfie_lab_model_key": "local_fast"},
        }

    def load_runtime_config(self) -> LLMRuntimeConfig:
        self.ensure_defaults()
        return LLMRuntimeConfig(config_home=str(self.root))

    def read_document(self) -> Dict[str, Any]:
        self.ensure_defaults()
        with self.config_path.open(encoding="utf-8") as handle:
            document = yaml.safe_load(handle) or {}
        if not isinstance(document, dict):
            raise ValueError(f"Invalid Runtime dev config format: {self.config_path}")
        return document

    def configure_provider(
        self,
        provider: str,
        *,
        api_base: str,
        api_mode: str,
        model: str,
        model_key: str,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        provider = provider.strip().lower()
        if provider not in PROVIDER_DEFAULTS:
            raise ValueError(f"Unsupported provider: {provider}")
        if model_key not in {
            "local_fast",
            "remote_cheap",
            "remote_deep",
            "remote_multimodal",
        }:
            raise ValueError(f"Unsupported model slot: {model_key}")
        if model_key == "local_fast" and provider != "ollama":
            raise ValueError("local_fast slot can only be configured with Ollama")
        if not api_base.strip() or not model.strip():
            raise ValueError("API Base and model name cannot be empty")

        document = self.read_document()
        providers = document.setdefault("providers", {})
        provider_info = providers.setdefault(provider, {})
        provider_info.update(
            {
                "display_name": PROVIDER_DEFAULTS[provider]["display_name"],
                "api_base": api_base.strip().rstrip("/"),
                "api_mode": api_mode.strip(),
                "test_model": model.strip(),
            }
        )
        if model_key == "local_fast":
            document["ollama_host"] = api_base.strip().rstrip("/")
            document["ollama_model_fast"] = model.strip()
        elif model_key == "remote_cheap":
            document["cheap_provider"] = provider
            document["cheap_model"] = model.strip()
        elif model_key == "remote_deep":
            document["deep_provider"] = provider
            document["deep_model"] = model.strip()
        else:
            document["multimodal_provider"] = provider
            document["multimodal_model"] = model.strip()
        document.setdefault("runtime_policy", {})["elfie_lab_model_key"] = model_key
        self._write_yaml(document)

        if api_key is not None and provider in SECRET_ENV_KEYS:
            if "\n" in api_key or "\r" in api_key:
                raise ValueError("API Key 不能包含换行符")
            secrets = self._read_env()
            env_key = SECRET_ENV_KEYS[provider]
            if api_key.strip():
                secrets[env_key] = api_key.strip()
            else:
                secrets.pop(env_key, None)
            self._write_env(secrets)
        return self.status()

    def status(self) -> Dict[str, Any]:
        config = self.load_runtime_config()
        document = self.read_document()
        model_key = str(config.runtime_policy.get("elfie_lab_model_key", "local_fast"))
        provider, model = self._resolve_model(document, model_key)
        provider_info = config.providers.get(provider, {})
        credential_configured = provider == "ollama" or bool(
            provider_info.get("api_key")
        )
        return {
            "scope": "development",
            "config_dir": str(self.root),
            "config_path": str(self.config_path),
            "secrets_path": str(self.env_path),
            "model_key": model_key,
            "provider": provider,
            "provider_name": provider_info.get("display_name", provider),
            "model": model,
            "api_base": provider_info.get("api_base", ""),
            "credential_configured": credential_configured,
            "ready_for_attempt": credential_configured,
            "providers": {
                name: {
                    "display_name": info.get("display_name", name),
                    "api_base": info.get("api_base", ""),
                    "api_mode": info.get("api_mode", "chat_completions"),
                    "test_model": info.get("test_model", ""),
                    "credential_configured": name == "ollama"
                    or bool(info.get("api_key")),
                }
                for name, info in config.providers.items()
            },
            "setup_command": ".venv/bin/python -m devtools.runtime_lab configure",
            "test_command": ".venv/bin/python -m devtools.runtime_lab test",
        }

    @staticmethod
    def _resolve_model(document: Dict[str, Any], model_key: str) -> tuple[str, str]:
        mapping = {
            "local_fast": (
                "ollama",
                str(document.get("ollama_model_fast", "")),
            ),
            "remote_cheap": (
                str(document.get("cheap_provider", "")),
                str(document.get("cheap_model", "")),
            ),
            "remote_deep": (
                str(document.get("deep_provider", "")),
                str(document.get("deep_model", "")),
            ),
            "remote_multimodal": (
                str(document.get("multimodal_provider", "")),
                str(document.get("multimodal_model", "")),
            ),
        }
        return mapping.get(model_key, mapping["local_fast"])

    def _read_env(self) -> Dict[str, str]:
        values: Dict[str, str] = {}
        if not self.env_path.exists():
            return values
        with self.env_path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return values

    def _write_yaml(self, document: Dict[str, Any]) -> None:
        content = yaml.safe_dump(
            document,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
        self._atomic_write(self.config_path, content, 0o600)

    def _write_env(self, values: Dict[str, str]) -> None:
        content = "".join(f"{key}={value}\n" for key, value in sorted(values.items()))
        self._atomic_write(self.env_path, content, 0o600)

    def _atomic_write(self, path: Path, content: str, mode: int) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _chmod(path: Path, mode: int) -> None:
        try:
            current = stat.S_IMODE(path.stat().st_mode)
            if current != mode:
                path.chmod(mode)
        except OSError:
            pass
