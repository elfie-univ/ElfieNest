"""Model Catalog 管理 REST API — 模型目录的查看、更新、扫描。

所有端点通过 ``Depends(require_admin)`` 保护。
模型数据来自 BUILTIN_MODEL_CATALOG + runtime_config.json 的覆盖配置。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from elfienest.config.runtime_store import read_runtime_config, write_runtime_config
from runtime.config import LLMRuntimeConfig
from runtime.models.catalog import BUILTIN_MODEL_CATALOG, ModelCatalog, ModelEntry
from runtime.providers.profiles import get_profile

from .admin_routes import require_admin

logger = logging.getLogger("elfienest.api.model_admin_routes")

router = APIRouter(prefix="/api/admin/models", tags=["models"])

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_RUNTIME_CONFIG_PATH: Path = _PROJECT_ROOT / "runtime" / "runtime_config.json"


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _read_runtime_config() -> Dict[str, Any]:
    """读取 runtime_config.json，不存在时返回空 dict。"""
    return read_runtime_config(_RUNTIME_CONFIG_PATH)


def _write_runtime_config(config: Dict[str, Any]) -> None:
    """写入 runtime_config.json（先备份）。"""
    write_runtime_config(_RUNTIME_CONFIG_PATH, config)


def _build_model_response(entry: ModelEntry, overrides: Dict[str, Any]) -> Dict[str, Any]:
    """构建单个 model 的响应对象，合并覆盖配置。"""
    visible = overrides.get("visible", entry.visible)
    cost_tier = overrides.get("cost_tier", entry.cost_tier)

    return {
        "model_id": entry.model_id,
        "provider": entry.provider,
        "display_name": entry.display_name,
        "capabilities": entry.capabilities,
        "context_window": entry.context_window,
        "cost_tier": cost_tier,
        "visible": visible,
        "active": entry.active,
    }


def _get_model_overrides(config: Dict[str, Any], model_id: str) -> Dict[str, Any]:
    """获取模型在配置中的覆盖设置。"""
    models_config = config.get("models", {})
    return models_config.get(model_id, {})


# ===================================================================
# 路由：GET /api/admin/models
# ===================================================================


@router.get("/")
async def list_models(
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> List[Dict[str, Any]]:
    """列出完整模型目录（内置 + 配置覆盖）。

    返回每个模型的 visibility、capabilities、active 状态等元数据。
    """
    _ = admin

    config = _read_runtime_config()

    # 创建 ModelCatalog 实例（会自动刷新 active 状态）
    runtime_config = LLMRuntimeConfig()
    catalog = ModelCatalog(runtime_config)

    result = []
    for model_id, entry in catalog.get_all_models().items():
        overrides = _get_model_overrides(config, model_id)
        result.append(_build_model_response(entry, overrides))

    return result


# ===================================================================
# 路由：PUT /api/admin/models/{model_id}
# ===================================================================


@router.put("/{model_id:path}")
async def update_model(
    model_id: str,
    body: Dict[str, Any],
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    """更新模型可见性或费用等级。

    Body 可选字段: visible (bool), cost_tier (int 0-4)
    """
    _ = admin

    # 检查模型存在性
    if model_id not in BUILTIN_MODEL_CATALOG:
        raise HTTPException(status_code=404, detail=f"model '{model_id}' 不存在")

    config = _read_runtime_config()
    if "models" not in config:
        config["models"] = {}

    # 获取当前覆盖配置
    model_overrides = config["models"].get(model_id, {})

    # 更新字段
    if "visible" in body:
        if not isinstance(body["visible"], bool):
            raise HTTPException(status_code=422, detail="visible 必须为布尔值")
        model_overrides["visible"] = body["visible"]

    if "cost_tier" in body:
        cost_tier = body["cost_tier"]
        if not isinstance(cost_tier, int) or not (0 <= cost_tier <= 4):
            raise HTTPException(status_code=422, detail="cost_tier 必须为 0-4 的整数")
        model_overrides["cost_tier"] = cost_tier

    config["models"][model_id] = model_overrides
    _write_runtime_config(config)

    # 构建响应
    entry = BUILTIN_MODEL_CATALOG[model_id]
    logger.info("Model '%s' updated by admin: %s", model_id, model_overrides)

    return _build_model_response(entry, model_overrides)


# ===================================================================
# 路由：POST /api/admin/models/scan
# ===================================================================


@router.post("/scan")
async def scan_models(
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    """扫描新的可用模型（如发现 Ollama 本地模型）。

    当前仅支持 Ollama provider 的本地模型发现。
    返回: {"discovered": [...], "total": int}
    """
    _ = admin

    discovered: List[Dict[str, Any]] = []

    # 读取 Ollama 配置
    config = _read_runtime_config()
    providers = config.get("providers", {})
    ollama_config = providers.get("ollama", {})

    # 获取 Ollama API base
    profile = get_profile("ollama")
    api_base = ollama_config.get("api_base", profile.api_base if profile else "http://localhost:11434")

    # 尝试获取 Ollama 本地模型列表
    try:
        url = f"{api_base.rstrip('/')}/api/tags"
        request = urllib.request.Request(url, method="GET")

        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                models = data.get("models", [])

                # 过滤掉已在目录中的模型
                existing_ids = set(BUILTIN_MODEL_CATALOG.keys())

                for model in models:
                    model_name = model.get("name", "")
                    model_id = f"ollama/{model_name}"

                    if model_id not in existing_ids:
                        discovered.append({
                            "model_id": model_id,
                            "provider": "ollama",
                            "display_name": model_name,
                            "capabilities": ["text"],  # 默认能力
                            "context_window": 4096,  # 默认上下文
                            "cost_tier": 0,  # 免费本地模型
                        })

    except urllib.error.URLError as e:
        logger.warning("Ollama 扫描失败: %s", e)
    except Exception as e:
        logger.warning("模型扫描异常: %s", e)

    logger.info("模型扫描完成，发现 %d 个新模型", len(discovered))

    return {
        "discovered": discovered,
        "total": len(discovered),
    }
