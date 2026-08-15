"""基础工具的本地配置契约。

界面只编辑工具语义配置；密钥仅保存在所选数据根的 ``configs/auth.env``。
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Callable, Mapping, Optional

from pydantic import JsonValue

from infrastructure.persistence.configuration.bundled_defaults import load_tool_defaults

SAFE_TOOL_KEYS: tuple[str, ...] = (
    "web_search",
    "local_file",
)
# Compatibility name for callers that enumerate the phase-one safe registry.
TOOL_KEYS = SAFE_TOOL_KEYS
SecretResolver = Callable[[str], str]


def _environment_secret(name: str) -> str:
    """Return an explicitly injected-process secret without owning storage."""
    return os.environ.get(name, "")


def default_tool_configs() -> dict[str, dict[str, JsonValue]]:
    return load_tool_defaults()


def load_tool_configs(
    runtime_policy: Mapping[str, JsonValue] | None,
    *,
    secret_resolver: Optional[SecretResolver] = None,
) -> dict[str, dict[str, JsonValue]]:
    configs = default_tool_configs()
    raw_tools = (
        runtime_policy.get("tools", {}) if isinstance(runtime_policy, Mapping) else {}
    )
    if isinstance(raw_tools, Mapping):
        for tool_key in SAFE_TOOL_KEYS:
            raw = raw_tools.get(tool_key)
            if isinstance(raw, Mapping):
                configs[tool_key].update(dict(raw))
    search = configs["web_search"]
    secret_name = str(search.get("api_key_env") or "ELFIE_WEB_SEARCH_API_KEY")
    search["api_key_env"] = secret_name
    search["api_key"] = (secret_resolver or _environment_secret)(secret_name)
    return configs


def public_tool_configs(
    runtime_policy: Mapping[str, JsonValue] | None,
    *,
    secret_resolver: Optional[SecretResolver] = None,
) -> dict[str, dict[str, JsonValue]]:
    configs = deepcopy(
        load_tool_configs(runtime_policy, secret_resolver=secret_resolver)
    )
    for config in configs.values():
        api_key = str(config.pop("api_key", "") or "")
        config["has_api_key"] = bool(api_key)
    return configs


def enabled_tool_keys(
    runtime_policy: Mapping[str, JsonValue] | None,
    *,
    secret_resolver: Optional[SecretResolver] = None,
) -> tuple[str, ...]:
    return tuple(
        key
        for key, config in load_tool_configs(
            runtime_policy, secret_resolver=secret_resolver
        ).items()
        if config.get("enabled") is True
    )


def effective_tool_keys(
    runtime_policy: Mapping[str, JsonValue] | None,
    requested_tools: tuple[str, ...],
    *,
    secret_resolver: Optional[SecretResolver] = None,
) -> tuple[str, ...]:
    """Return the ordered, duplicate-free safe tool authorization intersection."""
    enabled = set(enabled_tool_keys(runtime_policy, secret_resolver=secret_resolver))
    result: list[str] = []
    for tool_key in requested_tools:
        if (
            tool_key in SAFE_TOOL_KEYS
            and tool_key in enabled
            and tool_key not in result
        ):
            result.append(tool_key)
    return tuple(result)
