from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from .providers.profiles import BUILTIN_PROFILES, get_default_api_mode, get_product
from .storage.config_store import ConfigStoreError, read_yaml_mapping
from .storage.data_home import get_env_path, get_provider_config_path
from .storage.provider_connections import ProviderConnectionStore
from .storage.runtime_config_bundle import read_runtime_config_bundle
from .storage.secrets import (
    connection_secret_name,
    provider_secret_name,
    read_secrets,
    resolve_secret,
)


def _load_env_file_values(env_path: Path | None = None) -> Dict[str, str]:
    return read_secrets(env_path or get_env_path())


def _env_value(
    env_values: Dict[str, str],
    key: str,
    default: str = "",
    *,
    include_process_env: bool = True,
) -> str:
    if include_process_env:
        return os.getenv(key, env_values.get(key, default))
    return env_values.get(key, default)


def _default_providers(
    env_path: Path | None = None,
    *,
    include_process_env: bool = True,
) -> Dict[str, Dict[str, Any]]:
    env_values = _load_env_file_values(env_path)
    providers: Dict[str, Dict[str, Any]] = {}
    for provider_id, profile in BUILTIN_PROFILES.items():
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


def _connection_providers() -> Dict[str, Dict[str, Any]]:
    """Project stable connection instances into the Runtime provider grid."""
    path = get_provider_config_path()
    if not path.exists():
        return {}
    document = ProviderConnectionStore(path).load()
    providers: Dict[str, Dict[str, Any]] = {}
    for connection_id, connection in document.connections.items():
        if not connection.enabled:
            continue
        profile = get_product(connection.catalog_id)
        if profile is None:
            continue
        secret_name = connection.credential_ref or connection_secret_name(connection_id)
        providers[connection_id] = {
            "catalog_id": connection.catalog_id,
            "display_name": connection.alias,
            "api_base": connection.api_base or profile.api_base,
            "api_mode": connection.api_mode or profile.api_mode,
            "auth_type": connection.auth_type or profile.auth_type,
            "api_key_env": secret_name,
            "api_key": resolve_secret(secret_name),
            "models": [
                {
                    "id": model.endpoint_model_id,
                    "display_name": model.display_name,
                }
                for model in connection.models
                if not model.hidden
            ],
        }
    return providers


# 开发工具仍使用旧字段名；值由同一 Provider 目录派生。
PROVIDER_RECOMMENDS: Dict[str, Dict[str, Any]] = {
    provider_id: {
        "name": profile.name,
        "api_base": profile.api_base,
        "cheap_models": list(profile.default_models["cheap"]),
        "deep_models": list(profile.default_models["deep"]),
        "multimodal_models": list(profile.default_models["multimodal"]),
    }
    for provider_id, profile in BUILTIN_PROFILES.items()
}


# ---------------------------------------------------------------------------
# 系统设置默认值 & 深层合并工具
# ---------------------------------------------------------------------------


def deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并 ``updates`` 到 ``base``（就地修改）。

    对于嵌套字典键，递归合并；否则直接覆盖。
    """
    for k, v in updates.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            deep_update(base[k], v)
        else:
            base[k] = v
    return base


DEFAULT_SYSTEM_SETTINGS: Dict[str, Dict[str, Any]] = {
    "llm": {
        "default_cheap_model": "qwen3.5:0.8b",
        "default_cheap_provider": "ollama",
        "default_deep_model": "qwen3.5:0.8b",
        "default_deep_provider": "ollama",
        "default_multimodal_model": "moondream",
        "default_multimodal_provider": "ollama",
        "temperature": 0.7,
        "max_tokens": 1500,
        "energy_threshold_fast": 30,
        "complexity_threshold_deep": 4,
    },
    "adoption": {
        "max_elfies_per_user": 3,
        "allowed_species_ids": ["dog", "fox"],
        "personality_presets_enabled": {
            "活泼好动": True,
            "安静温顺": True,
            "好奇探索": True,
            "胆小害羞": True,
            "傲娇独立": True,
            "完全随机": True,
        },
    },
    "engine": {
        "tick_interval_sec": 1.5,
        "max_elfies_per_room": None,
    },
    "security": {
        "session_ttl_days": 7,
        "rate_limit": {"max_attempts": 5, "window_seconds": 300},
    },
}


@dataclass
class LLMRuntimeConfig:
    """大模型运行时跨服务商混合算力网格配置"""

    # 1. 多订阅源字典：存储各个 Provider 的 API Key、Base 节点、API 模式与状态
    providers: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # 2. 算力分档路由映射 (模型名称 + 归属 Provider 绑定)
    cheap_model: str = "qwen3.5:0.8b"
    cheap_provider: str = "ollama"

    deep_model: str = "qwen3.5:0.8b"
    deep_provider: str = "ollama"

    multimodal_model: str = "moondream"
    multimodal_provider: str = "ollama"

    # 3. 本地 Ollama 参数 (向下兼容与心跳拉起)
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model_fast: str = os.getenv("OLLAMA_MODEL_FAST", "qwen3.5:0.8b")
    ollama_model_vision: str = os.getenv("OLLAMA_MODEL_VISION", "moondream")

    # 4. 路由与能耗控制阈值
    energy_threshold_fast: float = (
        30.0  # 物理精力低于 30% 强制降级使用 cheap 模型以省钱/省电
    )
    complexity_threshold_deep: int = 3  # 复杂度大于等于 3 使用 deep 深度模型

    # 5. 超参数
    temperature: float = 0.7
    max_tokens: int = 1500

    # 6. 系统设置（深层合并持久化文件中保存的部分）
    system: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_SYSTEM_SETTINGS)
    )
    runtime_policy: Dict[str, Any] = field(default_factory=dict)

    # 开发 Runtime Lab 使用独立配置目录，避免误读正式环境的密钥和策略。
    config_home: str | None = None

    def __post_init__(self):
        config_home = Path(self.config_home).expanduser() if self.config_home else None
        defaults = _default_providers(
            config_home / ".env" if config_home is not None else None,
            include_process_env=config_home is None,
        )
        if self.providers:
            deep_update(defaults, self.providers)
        self.providers = defaults

        if config_home is not None:
            # 开发配置不能继承正式进程的 Ollama 地址和模型选择。
            self.ollama_host = self.providers["ollama"]["api_base"]
            self.ollama_model_fast = "qwen3.5:0.8b"
            self.ollama_model_vision = "moondream"

        # 尝试自检测并热加载持久化的本地 YAML 配置文件
        saved_cfg = None
        # 生产配置由 configs/ 下三份 YAML 合并；开发 Lab 继续使用独立单文件。
        if config_home is None:
            try:
                saved_cfg = read_runtime_config_bundle()
            except ConfigStoreError:
                # 损坏的当前配置不会触发旧格式 fallback；继续使用内置默认值。
                saved_cfg = None
        else:
            yaml_path = config_home / "config.yaml"
            if yaml_path.exists():
                try:
                    saved_cfg = read_yaml_mapping(yaml_path)
                except ConfigStoreError:
                    saved_cfg = None

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
                    "cheap_model": "qwen3.5:0.8b",
                    "cheap_provider": "ollama",
                    "deep_model": "qwen3.5:0.8b",
                    "deep_provider": "ollama",
                    "multimodal_model": "moondream",
                    "multimodal_provider": "ollama",
                    "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                    "ollama_model_fast": os.getenv("OLLAMA_MODEL_FAST", "qwen3.5:0.8b"),
                    "ollama_model_vision": os.getenv(
                        "OLLAMA_MODEL_VISION", "moondream"
                    ),
                    "energy_threshold_fast": 30.0,
                    "complexity_threshold_deep": 3,
                    "temperature": 0.7,
                    "max_tokens": 1500,
                }
                for k, v in saved_cfg.items():
                    if k != "providers" and hasattr(self, k) and v is not None:
                        if (
                            k in explicit_defaults
                            and getattr(self, k) != explicit_defaults[k]
                        ):
                            continue
                        if k == "system" and isinstance(v, dict):
                            deep_update(self.system, v)
                        else:
                            setattr(self, k, v)
            except Exception:
                pass

        if config_home is None:
            self.providers.update(_connection_providers())

        # 确保 providers 字典中所有条目都有 api_mode 和 status
        for provider in self.providers:
            secret_name = self.providers[provider].get(
                "api_key_env"
            ) or provider_secret_name(provider)
            self.providers[provider]["api_key_env"] = secret_name
            secret_path = (
                config_home / ".env" if config_home is not None else get_env_path()
            )
            local_secret = (
                read_secrets(secret_path).get(secret_name, "")
                if config_home is not None
                else resolve_secret(secret_name, secret_path)
            )
            if local_secret:
                self.providers[provider]["api_key"] = local_secret
            # api_mode: 从 BUILTIN_PROFILES 获取，未知服务商默认 chat_completions
            if "api_mode" not in self.providers[provider]:
                self.providers[provider]["api_mode"] = get_default_api_mode(provider)
            # status: 如果 saved_cfg 中显式设置了 status，则使用它；否则根据 api_key 计算
            saved_status = None
            if saved_cfg and "providers" in saved_cfg:
                saved_info = saved_cfg["providers"].get(provider, {})
                if "status" in saved_info and saved_info["status"] in (
                    "active",
                    "inactive",
                ):
                    saved_status = saved_info["status"]
            if saved_status:
                self.providers[provider]["status"] = saved_status
            else:
                api_key = self.providers[provider].get("api_key", "")
                self.providers[provider]["status"] = (
                    "active"
                    if api_key
                    or self.providers[provider].get("api_mode") == "ollama"
                    else "inactive"
                )

        # 同步本地 ollama_host 的最新变更到 providers 字典中
        if self.ollama_host:
            self.providers["ollama"]["api_base"] = self.ollama_host

    @classmethod
    def load(cls, config_home: str | None = None) -> LLMRuntimeConfig:
        """加载当前运行时配置（每次调用重新读取）。"""
        return cls(config_home=config_home)

    def to_dict(self) -> Dict[str, Any]:
        """将当前混配配置全量转化为字典格式以供持久化保存"""
        return {
            "providers": self.providers,
            "cheap_model": self.cheap_model,
            "cheap_provider": self.cheap_provider,
            "deep_model": self.deep_model,
            "deep_provider": self.deep_provider,
            "multimodal_model": self.multimodal_model,
            "multimodal_provider": self.multimodal_provider,
            "ollama_host": self.ollama_host,
            "ollama_model_fast": self.ollama_model_fast,
            "ollama_model_vision": self.ollama_model_vision,
            "energy_threshold_fast": self.energy_threshold_fast,
            "complexity_threshold_deep": self.complexity_threshold_deep,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "system": self.system,
            "runtime_policy": self.runtime_policy,
        }

    def to_safe_dict(self) -> Dict[str, Any]:
        """返回可安全落盘的配置，不包含任何 Provider 明文密钥。"""
        payload = self.to_dict()
        payload["providers"] = {
            provider_id: {
                key: value for key, value in provider.items() if key != "api_key"
            }
            for provider_id, provider in self.providers.items()
        }
        return payload
