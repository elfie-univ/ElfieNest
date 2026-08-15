"""Model-execution configuration assembled from existing fact sources."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Protocol, cast

from pydantic import JsonValue

from infrastructure.models.oauth_credentials import OAuthCredentialPort
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.persistence.configuration.bundled_defaults import (
    load_system_defaults,
)
from infrastructure.persistence.provider_catalog import load_provider_catalog


def _model_execution_default(name: str, fallback):
    values = load_system_defaults().get("model_execution", {})
    if not isinstance(values, Mapping):
        return fallback
    value = values.get(name, fallback)
    return value


def _default_ollama_host() -> str:
    return os.getenv(
        "OLLAMA_HOST",
        str(_model_execution_default("ollama_host", "http://localhost:11434")),
    )


def _default_energy_threshold() -> float:
    return float(_model_execution_default("energy_threshold_fast", 30.0))


def _default_complexity_threshold() -> int:
    return int(_model_execution_default("complexity_threshold_deep", 3))


def _default_temperature() -> float:
    return float(_model_execution_default("temperature", 0.7))


def _default_max_tokens() -> int:
    return int(_model_execution_default("max_tokens", 1500))


class ModelExecutionConfigSource(Protocol):
    """Storage-agnostic inputs required to build one execution projection."""

    def load_env(self, config_home: Optional[Path]) -> Mapping[str, str]: ...

    def load_settings(self, config_home: Optional[Path]) -> Mapping[str, JsonValue]: ...

    def load_connections(self) -> Mapping[str, Mapping[str, JsonValue]]: ...

    def resolve_secret(self, name: str, config_home: Optional[Path]) -> str: ...

    def provider_secret_name(self, provider_id: str) -> str: ...


class DefaultModelExecutionConfigSource:
    """Pure in-memory defaults used by isolated model code and tests."""

    def load_env(self, config_home: Optional[Path]) -> Mapping[str, str]:
        if config_home is not None:
            return {}
        return dict(os.environ)

    def load_settings(self, config_home: Optional[Path]) -> Mapping[str, JsonValue]:
        _ = config_home
        return {}

    def load_connections(self) -> Mapping[str, Mapping[str, JsonValue]]:
        return {}

    def resolve_secret(self, name: str, config_home: Optional[Path]) -> str:
        if config_home is not None:
            return ""
        return os.environ.get(name, "")

    def provider_secret_name(self, provider_id: str) -> str:
        normalized = "".join(
            character if character.isalnum() else "_"
            for character in provider_id.upper()
        ).strip("_")
        return f"{normalized or 'CUSTOM'}_API_KEY"


def _env_value(
    env_values: Mapping[str, str],
    key: str,
    default: str = "",
    *,
    include_process_env: bool = True,
) -> str:
    if include_process_env:
        return os.getenv(key, env_values.get(key, default))
    return env_values.get(key, default)


def _default_providers(
    catalog: ProviderCatalog,
    env_values: Mapping[str, str],
    provider_secret_name: Callable[[str], str],
    *,
    include_process_env: bool = True,
) -> Dict[str, Dict[str, JsonValue]]:
    providers: Dict[str, Dict[str, JsonValue]] = {}
    for provider_id, profile in catalog.profiles.items():
        api_key_env = profile.api_key_env_var or provider_secret_name(provider_id)
        providers[provider_id] = {
            "api_key": _env_value(
                env_values,
                api_key_env,
                include_process_env=include_process_env,
            ),
            "api_key_env": api_key_env,
            "api_base": _env_value(
                env_values,
                profile.base_url_env_var,
                profile.api_base,
                include_process_env=include_process_env,
            ),
            "api_mode": profile.api_mode,
            "auth_type": profile.auth_type,
        }
    providers["custom_openai"]["test_model"] = "custom-model"
    return providers


# ---------------------------------------------------------------------------
# 有限的 Provider 配置投影合并工具
# ---------------------------------------------------------------------------


def deep_update(
    base: Dict[str, JsonValue], updates: Mapping[str, JsonValue]
) -> Dict[str, JsonValue]:
    """递归合并 ``updates`` 到 ``base``（就地修改）。

    对于嵌套字典键，递归合并；否则直接覆盖。
    """
    for k, v in updates.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            deep_update(
                cast(Dict[str, JsonValue], base[k]),
                cast(Mapping[str, JsonValue], v),
            )
        else:
            base[k] = v
    return base


@dataclass
class ModelExecutionConfig:
    """Provider adapters and model-execution settings."""

    providers: Dict[str, Dict[str, JsonValue]] = field(default_factory=dict)
    provider_catalog: ProviderCatalog | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    ollama_host: str = field(default_factory=_default_ollama_host)

    energy_threshold_fast: float = field(default_factory=_default_energy_threshold)
    complexity_threshold_deep: int = field(
        default_factory=_default_complexity_threshold
    )

    temperature: float = field(default_factory=_default_temperature)
    max_tokens: int = field(default_factory=_default_max_tokens)

    system: Dict[str, JsonValue] = field(default_factory=load_system_defaults)
    runtime_policy: Mapping[str, JsonValue] = field(default_factory=dict)

    # 开发工具使用独立配置目录，避免误读正式环境的密钥和策略。
    config_home: str | None = None
    source: Optional[ModelExecutionConfigSource] = field(
        default=None,
        repr=False,
        compare=False,
    )
    oauth_credentials: OAuthCredentialPort | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        provider_catalog = self.provider_catalog or load_provider_catalog()
        self.provider_catalog = provider_catalog
        config_home = Path(self.config_home).expanduser() if self.config_home else None
        source: ModelExecutionConfigSource = (
            self.source or DefaultModelExecutionConfigSource()
        )
        defaults = _default_providers(
            provider_catalog,
            source.load_env(config_home),
            source.provider_secret_name,
            include_process_env=config_home is None,
        )
        if self.providers:
            deep_update(
                cast(Dict[str, JsonValue], defaults),
                cast(Mapping[str, JsonValue], self.providers),
            )
        self.providers = defaults

        if config_home is not None:
            # 开发配置不能继承正式进程的 Ollama 地址。
            api_base = self.providers["ollama"].get("api_base")
            if isinstance(api_base, str):
                self.ollama_host = api_base

        # The persistence source owns YAML parsing and path selection.
        saved_cfg = source.load_settings(config_home)

        # 合并配置到当前实例
        if saved_cfg is not None:
            try:
                # 递归更新 providers 字典以防止局部 key 缺失
                if "providers" in saved_cfg and isinstance(
                    saved_cfg["providers"], dict
                ):
                    for provider, info in saved_cfg["providers"].items():
                        if not isinstance(provider, str) or not isinstance(info, dict):
                            continue
                        if provider not in self.providers:
                            self.providers[provider] = {}
                        if "api_key" in info:
                            self.providers[provider]["api_key"] = info["api_key"]
                        if "api_base" in info:
                            self.providers[provider]["api_base"] = info["api_base"]
                        if "api_mode" in info:
                            self.providers[provider]["api_mode"] = info["api_mode"]
                        if "auth_type" in info:
                            self.providers[provider]["auth_type"] = info["auth_type"]
                        if "status" in info and info["status"] in (
                            "active",
                            "inactive",
                        ):
                            self.providers[provider]["status"] = info["status"]
                        if "test_model" in info:
                            self.providers[provider]["test_model"] = info["test_model"]
                        if "models" in info and isinstance(info["models"], list):
                            self.providers[provider]["models"] = info["models"]
                        if "display_name" in info:
                            self.providers[provider]["display_name"] = info[
                                "display_name"
                            ]
                        if "api_key_env" in info:
                            self.providers[provider]["api_key_env"] = info[
                                "api_key_env"
                            ]
                        if provider == "ollama" and isinstance(
                            info.get("installation"), dict
                        ):
                            self.providers[provider]["installation"] = copy.deepcopy(
                                info["installation"]
                            )

                # 更新其他字段属性（system 键深层合并，其余直接覆盖）
                explicit_defaults = {
                    "ollama_host": _default_ollama_host(),
                    "energy_threshold_fast": _default_energy_threshold(),
                    "complexity_threshold_deep": _default_complexity_threshold(),
                    "temperature": _default_temperature(),
                    "max_tokens": _default_max_tokens(),
                }
                for k, v in saved_cfg.items():
                    if k != "providers" and hasattr(self, k) and v is not None:
                        if (
                            k in explicit_defaults
                            and getattr(self, k) != explicit_defaults[k]
                        ):
                            continue
                        if k == "system" and isinstance(v, dict):
                            deep_update(
                                self.system,
                                cast(Mapping[str, JsonValue], v),
                            )
                        else:
                            setattr(self, k, v)
            except Exception:
                pass

        for provider_id, connection in source.load_connections().items():
            self.providers[provider_id] = dict(connection)

        # 确保 providers 字典中所有条目都有 api_mode 和 status
        for provider in self.providers:
            raw_secret_name = self.providers[provider].get("api_key_env")
            secret_name = (
                raw_secret_name
                if isinstance(raw_secret_name, str)
                else source.provider_secret_name(provider)
            )
            self.providers[provider]["api_key_env"] = secret_name
            local_secret = source.resolve_secret(secret_name, config_home)
            if local_secret:
                self.providers[provider]["api_key"] = local_secret
            # api_mode: 从已校验的 Provider catalog 获取，未知服务商使用协议安全默认值。
            if "api_mode" not in self.providers[provider]:
                profile = provider_catalog.profiles.get(provider)
                self.providers[provider]["api_mode"] = (
                    profile.api_mode if profile is not None else "chat_completions"
                )
            # status: 如果 saved_cfg 中显式设置了 status，则使用它；否则根据 api_key 计算
            saved_status = None
            if saved_cfg and "providers" in saved_cfg:
                saved_providers = cast(Mapping[str, JsonValue], saved_cfg["providers"])
                raw_saved_info = saved_providers.get(provider, {})
                saved_info = (
                    cast(Mapping[str, JsonValue], raw_saved_info)
                    if isinstance(raw_saved_info, dict)
                    else {}
                )
                if "status" in saved_info and saved_info["status"] in (
                    "active",
                    "inactive",
                ):
                    saved_status = saved_info["status"]
            if saved_status:
                self.providers[provider]["status"] = saved_status
            else:
                raw_api_key = self.providers[provider].get("api_key", "")
                api_key = raw_api_key if isinstance(raw_api_key, str) else ""
                self.providers[provider]["status"] = (
                    "active"
                    if api_key or self.providers[provider].get("api_mode") == "ollama"
                    else "inactive"
                )

        # 同步本地 ollama_host 的最新变更到 providers 字典中
        if self.ollama_host:
            self.providers["ollama"]["api_base"] = self.ollama_host

    @classmethod
    def load(cls, config_home: str | None = None) -> ModelExecutionConfig:
        """加载当前模型执行配置（每次调用重新读取）。"""
        return cls(config_home=config_home)

    def to_dict(self) -> Dict[str, JsonValue]:
        """将当前混配配置全量转化为字典格式以供持久化保存"""
        return cast(
            Dict[str, JsonValue],
            {
                "providers": self.providers,
                "ollama_host": self.ollama_host,
                "energy_threshold_fast": self.energy_threshold_fast,
                "complexity_threshold_deep": self.complexity_threshold_deep,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "system": self.system,
                "runtime_policy": self.runtime_policy,
            },
        )

    def to_safe_dict(self) -> Dict[str, JsonValue]:
        """返回可安全落盘的配置，不包含任何 Provider 明文密钥。"""
        payload = self.to_dict()
        payload["providers"] = cast(
            JsonValue,
            {
                provider_id: {
                    key: value for key, value in provider.items() if key != "api_key"
                }
                for provider_id, provider in self.providers.items()
            },
        )
        return payload
