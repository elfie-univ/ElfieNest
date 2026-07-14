"""基础 Agent 工具的本地配置与验证 API。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from elfienest.config.runtime_store import read_runtime_config, write_runtime_config
from runtime.config import LLMRuntimeConfig
from runtime.storage.data_home import get_config_path
from runtime.storage.secrets import set_tool_secret, tool_secret_name
from runtime.tools.config import TOOL_KEYS, public_tool_configs
from runtime.validation.models import ValidationSuite
from runtime.validation.tools import DirectToolValidationRunner

from .admin_routes import require_admin

router = APIRouter(prefix="/api/admin/runtime/tools", tags=["runtime-tools"])
_RUNTIME_CONFIG_PATH: Path = get_config_path()


def _read_policy() -> tuple[dict[str, Any], dict[str, Any]]:
    config = read_runtime_config(_RUNTIME_CONFIG_PATH)
    policy = config.get("runtime_policy", {})
    if not isinstance(policy, dict):
        policy = {}
    return config, policy


@router.get("/")
async def list_tools(
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    _ = admin
    _config, policy = _read_policy()
    return {"tools": public_tool_configs(policy)}


@router.put("/{tool_key}")
async def update_tool(
    tool_key: str,
    body: Dict[str, Any],
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    _ = admin
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
        "web_search": {"enabled", "provider", "api_base", "max_results"},
        "local_file": {"enabled", "root"},
        "code_sandbox": {"enabled", "timeout_seconds"},
        "skills_evolution": {"enabled"},
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
    elif tool_key == "code_sandbox":
        current["timeout_seconds"] = max(
            1.0, min(float(current.get("timeout_seconds") or 5.0), 60.0)
        )
    tools[tool_key] = current
    config["runtime_policy"] = policy
    write_runtime_config(_RUNTIME_CONFIG_PATH, config)
    return {"tool_key": tool_key, "config": public_tool_configs(policy)[tool_key]}


@router.post("/{tool_key}/verify")
async def verify_tool(
    tool_key: str,
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    _ = admin
    if tool_key not in TOOL_KEYS:
        raise HTTPException(status_code=404, detail="未知工具")
    config = LLMRuntimeConfig.load()
    runner = DirectToolValidationRunner(config)
    result = {
        "web_search": runner.verify_web_search,
        "local_file": runner.verify_file_sandbox,
        "code_sandbox": runner.verify_code_sandbox,
        "skills_evolution": runner.verify_skill_lifecycle,
    }[tool_key]()
    return ValidationSuite(f"tool:{tool_key}", (result,)).to_dict()
