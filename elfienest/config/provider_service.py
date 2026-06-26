from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from elfienest.config.user_config import EnvVars, UserConfig
from runtime.models.catalog import BUILTIN_MODEL_CATALOG
from runtime.providers.profiles import BUILTIN_PROFILES, ProviderProfile, get_profile


@dataclass(frozen=True)
class ProviderRow:
    provider_id: str
    name: str
    status: str
    api_mode: str


@dataclass(frozen=True)
class ModelRow:
    model_id: str
    capabilities_text: str
    cost_text: str
    status_text: str


@dataclass(frozen=True)
class ProviderSaveResult:
    config: UserConfig
    env_vars: EnvVars
    profile: ProviderProfile


@dataclass(frozen=True)
class ProviderRemoveResult:
    config: UserConfig
    env_vars: EnvVars
    profile: ProviderProfile
    removed_config: bool
    removed_env_key: bool


def get_known_profile(provider_id: str) -> Optional[ProviderProfile]:
    return get_profile(provider_id)


def list_provider_rows(config: UserConfig) -> List[ProviderRow]:
    providers_config = config.get("providers", {})
    rows: List[ProviderRow] = []
    for provider_id, profile in BUILTIN_PROFILES.items():
        provider_info = providers_config.get(provider_id, {})
        rows.append(
            ProviderRow(
                provider_id=provider_id,
                name=profile.name,
                status=provider_info.get("status", "inactive"),
                api_mode=profile.api_mode,
            )
        )
    return rows


def list_configured_provider_rows(config: UserConfig) -> List[ProviderRow]:
    providers_config = config.get("providers", {})
    rows: List[ProviderRow] = []
    for provider_id, info in providers_config.items():
        profile = get_profile(provider_id)
        rows.append(
            ProviderRow(
                provider_id=provider_id,
                name=profile.name if profile else provider_id,
                status=info.get("status", "inactive"),
                api_mode=profile.api_mode if profile else info.get("api_mode", ""),
            )
        )
    return rows


def save_provider_credentials(
    config: UserConfig,
    env_vars: EnvVars,
    provider_id: str,
    api_key: str,
    base_url: str,
) -> Optional[ProviderSaveResult]:
    profile = get_profile(provider_id)
    if profile is None:
        return None

    providers_config = config.setdefault("providers", {})
    providers_config[provider_id] = {
        "api_base": base_url,
        "api_mode": profile.api_mode,
        "status": "active",
    }

    if profile.api_key_env_var and api_key:
        env_vars[profile.api_key_env_var] = api_key
    if profile.base_url_env_var and base_url != profile.api_base:
        env_vars[profile.base_url_env_var] = base_url

    return ProviderSaveResult(config=config, env_vars=env_vars, profile=profile)


def remove_provider_credentials(
    config: UserConfig,
    env_vars: EnvVars,
    provider_id: str,
) -> Optional[ProviderRemoveResult]:
    profile = get_profile(provider_id)
    if profile is None:
        return None

    providers_config = config.get("providers", {})
    removed_config = provider_id in providers_config
    if removed_config:
        del providers_config[provider_id]

    removed_env_key = False
    if profile.api_key_env_var and profile.api_key_env_var in env_vars:
        del env_vars[profile.api_key_env_var]
        removed_env_key = True

    return ProviderRemoveResult(
        config=config,
        env_vars=env_vars,
        profile=profile,
        removed_config=removed_config,
        removed_env_key=removed_env_key,
    )


def list_model_rows(config: UserConfig) -> List[ModelRow]:
    providers_config = config.get("providers", {})
    rows: List[ModelRow] = []
    cost_tiers = ["免费", "极低", "低", "中", "高"]

    for model_id, entry in BUILTIN_MODEL_CATALOG.items():
        if not entry.visible:
            continue

        caps = ", ".join(entry.capabilities[:3])
        if len(entry.capabilities) > 3:
            caps += "..."

        cost_text = (
            cost_tiers[entry.cost_tier] if entry.cost_tier < len(cost_tiers) else "未知"
        )
        if entry.provider == "ollama":
            status_text = "✅ 可用"
        else:
            provider_info = providers_config.get(entry.provider, {})
            status_text = (
                "✅ 可用" if provider_info.get("status") == "active" else "⭕ 未配置"
            )

        rows.append(
            ModelRow(
                model_id=model_id,
                capabilities_text=caps,
                cost_text=cost_text,
                status_text=status_text,
            )
        )

    return rows
