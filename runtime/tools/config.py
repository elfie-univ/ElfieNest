"""基础工具的本地配置契约。

界面只编辑工具语义配置；密钥仅保存在 ``~/.elfienest/.env``。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from runtime.storage.data_home import get_local_files_dir
from runtime.storage.secrets import resolve_secret, tool_secret_name

TOOL_KEYS: tuple[str, ...] = (
    "web_search",
    "local_file",
    "code_sandbox",
    "skills_evolution",
)


def default_tool_configs() -> dict[str, dict[str, Any]]:
    return {
        "web_search": {
            "enabled": True,
            "provider": "duckduckgo",
            "api_base": "",
            "api_key_env": tool_secret_name("web_search"),
            "max_results": 3,
        },
        "local_file": {
            "enabled": True,
            "root": str(get_local_files_dir()),
        },
        "code_sandbox": {"enabled": True, "timeout_seconds": 5.0},
        "skills_evolution": {"enabled": True},
    }


def load_tool_configs(runtime_policy: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    configs = default_tool_configs()
    raw_tools = runtime_policy.get("tools", {}) if isinstance(runtime_policy, Mapping) else {}
    if isinstance(raw_tools, Mapping):
        for tool_key in TOOL_KEYS:
            raw = raw_tools.get(tool_key)
            if isinstance(raw, Mapping):
                configs[tool_key].update(dict(raw))
    search = configs["web_search"]
    secret_name = str(search.get("api_key_env") or tool_secret_name("web_search"))
    search["api_key_env"] = secret_name
    search["api_key"] = resolve_secret(secret_name)
    return configs


def public_tool_configs(runtime_policy: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    configs = deepcopy(load_tool_configs(runtime_policy))
    for config in configs.values():
        api_key = str(config.pop("api_key", "") or "")
        config["has_api_key"] = bool(api_key)
    return configs


def enabled_tool_keys(runtime_policy: Mapping[str, Any] | None) -> tuple[str, ...]:
    return tuple(
        key
        for key, config in load_tool_configs(runtime_policy).items()
        if config.get("enabled") is True
    )
