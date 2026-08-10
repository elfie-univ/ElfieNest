"""基础 Agent 工具的本地配置与验证 API。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.storage.data_home import get_config_path
from ai_runtime.storage.secrets import set_tool_secret, tool_secret_name
from ai_runtime.tools.config import TOOL_KEYS, public_tool_configs
from ai_runtime.validation.models import ValidationSuite
from ai_runtime.validation.tools import DirectToolValidationRunner
from app.features.configuration.runtime_store import (
    read_runtime_config,
    write_runtime_config,
)
from app.interfaces.api.v1.auth import require_manager

router = APIRouter(prefix="/api/owner/runtime/tools", tags=["runtime-tools"])


def _read_policy() -> tuple[dict[str, Any], dict[str, Any]]:
    config = read_runtime_config(get_config_path())
    policy = config.get("runtime_policy", {})
    if not isinstance(policy, dict):
        policy = {}
    return config, policy


@router.get("/")
async def list_tools(
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    _config, policy = _read_policy()
    return {"tools": public_tool_configs(policy)}


@router.put("/{tool_key}")
async def update_tool(
    tool_key: str,
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    if tool_key not in TOOL_KEYS:
        raise HTTPException(status_code=404, detail="未知工具")
    config, policy = _read_policy()
    tools = policy.setdefault("tools", {})
    if not isinstance(tools, dict):
        tools = {}
        policy["tools"] = tools
    current = tools.get(tool_key, {})
    if not isinstance(current, dict):
        current = {}
    allowed_fields = {
        "web_search": {
            "enabled",
            "provider",
            "api_base",
            "max_results",
            "max_result_bytes",
        },
        "local_file": {"enabled", "max_read_bytes"},
    }[tool_key]
    current.update({key: body[key] for key in allowed_fields if key in body})
    if tool_key == "web_search":
        provider = str(current.get("provider") or "duckduckgo")
        if provider not in {"duckduckgo", "brave", "tavily"}:
            raise HTTPException(
                status_code=422, detail="搜索 Provider 必须是 duckduckgo/brave/tavily"
            )
        current["provider"] = provider
        current["max_results"] = max(1, min(int(current.get("max_results") or 3), 10))
        current["api_key_env"] = tool_secret_name(tool_key)
        if "api_key" in body:
            set_tool_secret(tool_key, str(body.get("api_key") or ""))
    tools[tool_key] = current
    config["runtime_policy"] = policy
    write_runtime_config(get_config_path(), config)
    return {"tool_key": tool_key, "config": public_tool_configs(policy)[tool_key]}


@router.post("/{tool_key}/verify")
async def verify_tool(
    tool_key: str,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    if tool_key not in TOOL_KEYS:
        raise HTTPException(status_code=404, detail="未知工具")
    config = LLMRuntimeConfig.load()
    runner = DirectToolValidationRunner(config)
    result = {
        "web_search": runner.verify_web_search,
        "local_file": runner.verify_file_sandbox,
    }[tool_key]()
    return ValidationSuite(f"tool:{tool_key}", (result,)).to_dict()
