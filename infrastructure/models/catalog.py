"""模型目录系统 — 管理所有可用模型的元数据和状态。

提供:
- ModelEntry: 单个模型的完整元数据
- parse_model_catalog(): 解析已加载的模型目录文档
- ModelCatalog: 模型目录管理类
- verify_provider(): Provider 连通性验证

参考:
- OpenClaw 的 ModelProviderConfig (types.models.ts)
- Hermes Agent 的 HermesOverlay dataclass 模式
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.providers.http import open_provider_request

MODEL_CATALOG_VERSION = 1
_MODEL_CATALOG_FIELDS = frozenset({"version", "models", "entries"})
_MODEL_ENTRY_FIELDS = frozenset(
    {
        "provider",
        "display_name",
        "capabilities",
        "context_window",
        "cost_tier",
        "visible",
        "active",
    }
)


class ModelCatalogError(RuntimeError):
    """The registered model catalog is missing or violates its schema."""


@dataclass
class ModelEntry:
    """模型目录条目。

    Attributes:
        model_id: 唯一标识，格式为 "provider/model" (e.g. "openai/gpt-4o")
        provider: 归属 provider (e.g. "openai")
        display_name: 显示名称 (e.g. "GPT-4o")
        capabilities: 能力标签 ["text", "vision", "audio", "code", "reasoning"]
        context_window: 上下文窗口大小（token 数）
        cost_tier: 费用等级 0=免费 1=极低 2=低 3=中 4=高
        visible: 是否对普通用户可见（Owner控制）
        active: 是否可用（有 API key 且连通）
    """

    model_id: str
    provider: str
    display_name: str
    capabilities: List[str] = field(default_factory=list)
    context_window: int = 4096
    cost_tier: int = 1
    visible: bool = True
    active: bool = False


def parse_model_catalog(
    document: Mapping[str, Any], source: Path
) -> Dict[str, ModelEntry]:
    """Parse an already-loaded model catalog without performing file I/O."""
    if document.get("version") != MODEL_CATALOG_VERSION:
        raise ModelCatalogError(f"不支持的模型目录版本: {source}")
    unknown_top_level = set(document) - _MODEL_CATALOG_FIELDS
    if unknown_top_level:
        raise ModelCatalogError(
            f"模型目录顶层包含未知字段: {sorted(unknown_top_level)}"
        )
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, Mapping) or not raw_entries:
        raise ModelCatalogError(f"模型目录缺少 entries: {source}")

    result: Dict[str, ModelEntry] = {}
    for model_id, raw_entry in raw_entries.items():
        if not isinstance(model_id, str) or "/" not in model_id:
            raise ModelCatalogError(f"模型 ID 无效: {model_id!r}: {source}")
        if not isinstance(raw_entry, Mapping):
            raise ModelCatalogError(f"模型记录必须是对象: {model_id}: {source}")
        unknown = set(raw_entry) - _MODEL_ENTRY_FIELDS
        if unknown:
            raise ModelCatalogError(
                f"模型记录包含未知字段: {model_id} {sorted(unknown)}: {source}"
            )
        provider = raw_entry.get("provider")
        display_name = raw_entry.get("display_name")
        capabilities = raw_entry.get("capabilities")
        context_window = raw_entry.get("context_window")
        cost_tier = raw_entry.get("cost_tier")
        visible = raw_entry.get("visible")
        active = raw_entry.get("active")
        if (
            not isinstance(provider, str)
            or not provider
            or not isinstance(display_name, str)
            or not display_name
            or not isinstance(capabilities, list)
            or not all(isinstance(item, str) and item for item in capabilities)
            or isinstance(context_window, bool)
            or not isinstance(context_window, int)
            or context_window <= 0
            or isinstance(cost_tier, bool)
            or not isinstance(cost_tier, int)
            or cost_tier < 0
            or cost_tier > 4
            or not isinstance(visible, bool)
            or not isinstance(active, bool)
            or model_id.split("/", 1)[0] != provider
        ):
            raise ModelCatalogError(f"模型记录无效: {model_id}: {source}")
        result[model_id] = ModelEntry(
            model_id=model_id,
            provider=provider,
            display_name=display_name,
            capabilities=list(capabilities),
            context_window=context_window,
            cost_tier=cost_tier,
            visible=visible,
            active=active,
        )
    return result


class ModelCatalog:
    """模型目录管理类。

    管理所有可用模型的元数据和状态，支持：
    - 按可见性/激活状态筛选
    - 按能力/服务商筛选
    - 更新模型状态
    """

    def __init__(
        self,
        config: Optional[Any] = None,
        *,
        catalog: Optional[Mapping[str, ModelEntry]] = None,
    ):
        """初始化模型目录。

        Args:
            config: ModelExecutionConfig 实例，用于确定 provider 状态
            catalog: 由 Bootstrap 或 Persistence 加载的模型目录
        """
        if catalog is None:
            raise ValueError("ModelCatalog requires an injected model catalog")
        self.config = config
        # 深拷贝已登记的内置目录，避免修改源数据。
        self._catalog: Dict[str, ModelEntry] = {
            model_id: ModelEntry(
                model_id=entry.model_id,
                provider=entry.provider,
                display_name=entry.display_name,
                capabilities=list(entry.capabilities),
                context_window=entry.context_window,
                cost_tier=entry.cost_tier,
                visible=entry.visible,
                active=entry.active,
            )
            for model_id, entry in catalog.items()
        }
        # 根据配置更新 active 状态
        if config:
            self.refresh_status()

    def get_visible_models(self) -> Dict[str, ModelEntry]:
        """获取所有可见模型。

        Returns:
            只包含 visible=True 的模型字典
        """
        return {
            model_id: entry
            for model_id, entry in self._catalog.items()
            if entry.visible
        }

    def get_active_models(self) -> Dict[str, ModelEntry]:
        """获取所有可用模型。

        Returns:
            只包含 active=True 的模型字典
        """
        return {
            model_id: entry for model_id, entry in self._catalog.items() if entry.active
        }

    def get_models_by_capability(self, capability: str) -> List[ModelEntry]:
        """按能力筛选模型。

        Args:
            capability: 能力标签 (text, vision, audio, code, reasoning)

        Returns:
            具有指定能力的模型列表
        """
        return [
            entry
            for entry in self._catalog.values()
            if capability in entry.capabilities
        ]

    def get_models_by_provider(self, provider: str) -> List[ModelEntry]:
        """按服务商筛选模型。

        Args:
            provider: 服务商标识符 (ollama, openai, anthropic, etc.)

        Returns:
            属于指定服务商的模型列表
        """
        return [entry for entry in self._catalog.values() if entry.provider == provider]

    def update_visibility(self, model_id: str, visible: bool) -> bool:
        """更新模型可见性。

        Args:
            model_id: 模型唯一标识
            visible: 新的可见状态

        Returns:
            更新是否成功（模型不存在时返回 False）
        """
        if model_id not in self._catalog:
            return False
        self._catalog[model_id].visible = visible
        return True

    def refresh_status(self) -> None:
        """刷新模型激活状态。

        根据配置中 provider 的 API key 存在情况更新 active 状态。
        Ollama 始终为 active。
        """
        if not self.config:
            return

        for entry in self._catalog.values():
            provider = entry.provider
            # Ollama 始终可用
            if provider == "ollama":
                entry.active = True
                continue

            # 其他 provider 根据 API key 判断
            provider_info = self.config.providers.get(provider, {})
            has_api_key = bool(provider_info.get("api_key"))
            entry.active = has_api_key

    def get_model(self, model_id: str) -> Optional[ModelEntry]:
        """获取单个模型信息。

        Args:
            model_id: 模型唯一标识

        Returns:
            ModelEntry 或 None（不存在时）
        """
        return self._catalog.get(model_id)

    def get_all_models(self) -> Dict[str, ModelEntry]:
        """获取所有模型。

        Returns:
            完整模型字典
        """
        return dict(self._catalog)


def _verify_custom_openai_provider(
    provider_info: Dict[str, str],
    api_base: str,
    api_key: str,
    *,
    fallback_model: str = "",
    provider_catalog: ProviderCatalog,
) -> Dict[str, Any]:
    import time

    from infrastructure.models.providers.model_hints import configured_model_names

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    models_url = f"{api_base.rstrip('/')}/models"
    start_time = time.time()
    try:
        request = urllib.request.Request(models_url, headers=headers, method="GET")
        with open_provider_request(request, timeout=5) as response:
            if response.status == 200:
                return {
                    "status": "active",
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "error": None,
                }
    except urllib.error.HTTPError:
        pass

    configured_models = configured_model_names(
        provider_info,
        catalog=provider_catalog,
    )
    configured_test_model = str(provider_info.get("test_model") or "").strip()
    test_model = (
        configured_test_model
        if configured_test_model
        else configured_models[0]
        if configured_models
        else fallback_model.strip()
    )
    if not test_model:
        return {
            "status": "unverified",
            "latency_ms": None,
            "error": "未配置可用于验证的测试模型",
        }
    chat_url = f"{api_base.rstrip('/')}/chat/completions"
    payload = json.dumps(
        {
            "model": test_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
        }
    ).encode("utf-8")

    try:
        request = urllib.request.Request(
            chat_url,
            data=payload,
            headers=headers,
            method="POST",
        )
        with open_provider_request(request, timeout=5) as response:
            if response.status == 200:
                return {
                    "status": "active",
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "error": None,
                }
            return {
                "status": "inactive",
                "latency_ms": None,
                "error": f"HTTP {response.status}",
            }
    except urllib.error.HTTPError as e:
        return {
            "status": "inactive",
            "latency_ms": None,
            "error": _custom_openai_error(e.code, e.reason, test_model),
        }
    except urllib.error.URLError as e:
        return {
            "status": "inactive",
            "latency_ms": None,
            "error": f"连接失败: {e.reason}",
        }
    except TimeoutError:
        return {
            "status": "inactive",
            "latency_ms": None,
            "error": "连接超时（5秒）",
        }


def _custom_openai_error(status_code: int, reason: str, test_model: str) -> str:
    return (
        f"HTTP {status_code}: {reason}。"
        "自定义 OpenAI 兼容接口验证失败："
        "Base URL 应该类似 https://host/v1，不要填 /chat/completions；"
        f"请确认 API Key 正确，测试模型 {test_model} 在该端点可用。"
    )


def _verify_openai_compatible_provider(
    api_base: str,
    api_key: str,
    test_model: str,
    *,
    probe_models: bool = True,
) -> Dict[str, Any]:
    """Check an OpenAI-compatible endpoint with an optional model-list probe."""
    import time

    headers: Dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    started = time.time()
    if probe_models:
        models_url = f"{api_base.rstrip('/')}/models"
        try:
            request = urllib.request.Request(models_url, headers=headers, method="GET")
            with open_provider_request(request, timeout=5) as response:
                if response.status == 200:
                    return {
                        "status": "active",
                        "latency_ms": round((time.time() - started) * 1000, 2),
                        "error": None,
                    }
                if response.status not in {404, 405, 501}:
                    return {
                        "status": "inactive",
                        "latency_ms": None,
                        "error": f"HTTP {response.status}",
                    }
        except urllib.error.HTTPError as exc:
            if exc.code not in {404, 405, 501}:
                return {
                    "status": "inactive",
                    "latency_ms": None,
                    "error": f"HTTP {exc.code}: {exc.reason}",
                }
        except urllib.error.URLError as exc:
            return {
                "status": "inactive",
                "latency_ms": None,
                "error": f"连接失败: {exc.reason}",
            }
        except TimeoutError:
            return {
                "status": "inactive",
                "latency_ms": None,
                "error": "连接超时（5秒）",
            }
        except Exception as exc:
            return {
                "status": "inactive",
                "latency_ms": None,
                "error": str(exc),
            }

    return _verify_openai_chat_endpoint(
        api_base,
        test_model,
        headers=headers,
        started=started,
        empty_model_error=(
            "模型列表不可用且未配置安全测试模型"
            if probe_models
            else "未配置安全测试模型"
        ),
    )


def _verify_openai_chat_endpoint(
    api_base: str,
    test_model: str,
    *,
    headers: Dict[str, str],
    started: float,
    empty_model_error: str,
) -> Dict[str, Any]:
    """Verify one named model without discovering a provider-wide model list."""
    import time

    normalized_test_model = test_model.strip()
    if not normalized_test_model:
        return {
            "status": "inactive",
            "latency_ms": None,
            "error": empty_model_error,
        }
    chat_url = f"{api_base.rstrip('/')}/chat/completions"
    payload = json.dumps(
        {
            "model": normalized_test_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
        }
    ).encode("utf-8")
    chat_headers = {**headers, "Content-Type": "application/json"}
    try:
        request = urllib.request.Request(
            chat_url,
            data=payload,
            headers=chat_headers,
            method="POST",
        )
        with open_provider_request(request, timeout=5) as response:
            if response.status == 200:
                return {
                    "status": "active",
                    "latency_ms": round((time.time() - started) * 1000, 2),
                    "error": None,
                }
            return {
                "status": "inactive",
                "latency_ms": None,
                "error": f"HTTP {response.status}（测试模型 {normalized_test_model}）",
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": "inactive",
            "latency_ms": None,
            "error": (
                f"HTTP {exc.code}: {exc.reason}；"
                f"测试模型 {normalized_test_model} 不可用"
            ),
        }
    except urllib.error.URLError as exc:
        return {
            "status": "inactive",
            "latency_ms": None,
            "error": f"连接失败: {exc.reason}",
        }
    except TimeoutError:
        return {
            "status": "inactive",
            "latency_ms": None,
            "error": "连接超时（5秒）",
        }
    except Exception as exc:
        return {
            "status": "inactive",
            "latency_ms": None,
            "error": str(exc),
        }


def verify_provider(
    provider_id: str,
    config: Any,
    *,
    provider_catalog: ProviderCatalog | None = None,
) -> Dict[str, Any]:
    """验证 Provider 连通性。

    通过 HTTP 请求检查 provider 是否可达和可用。

    Args:
        provider_id: 服务商标识符 (ollama, openai, anthropic, etc.)
        config: ModelExecutionConfig 实例

    Returns:
        {"status": "active"|"inactive"|"unverified", "latency_ms": float|None, "error": str|None}
    """
    import time

    result: Dict[str, Any] = {
        "status": "unverified",
        "latency_ms": None,
        "error": None,
    }

    # 获取 provider 配置
    provider_info = config.providers.get(provider_id, {})
    api_base = provider_info.get("api_base", "")
    api_key = provider_info.get("api_key", "")

    # 获取 profile 以确定 api_mode 和 auth_type
    resolved_catalog = provider_catalog or getattr(config, "provider_catalog", None)
    if resolved_catalog is None:
        raise ValueError("verify_provider requires an injected provider catalog")
    profile = resolved_catalog.profiles.get(provider_id)
    if profile is None and (provider_id not in config.providers or not api_base):
        result["error"] = f"未知 provider: {provider_id}"
        return result
    api_mode = (
        profile.api_mode
        if profile
        else str(provider_info.get("api_mode", "chat_completions"))
    )
    # 构建请求 URL 和 headers
    url = ""
    headers: Dict[str, str] = {}

    try:
        if api_mode == "ollama":
            # Ollama: GET {api_base}/api/tags
            url = f"{api_base.rstrip('/')}/api/tags"
        elif api_mode == "chat_completions":
            if provider_id == "custom_openai" or profile is None:
                return _verify_custom_openai_provider(
                    provider_info,
                    api_base,
                    api_key,
                    fallback_model=profile.test_model if profile else "",
                    provider_catalog=resolved_catalog,
                )
            return _verify_openai_compatible_provider(
                api_base,
                api_key,
                str(provider_info.get("test_model") or profile.test_model),
                # Product-specific adapters own their entitlement inventory.
                # Health probes the configured representative model; the
                # adapter separately discovers the restricted subscription
                # inventory. A generic /models probe would conflate platform
                # inventory with the subscription.
                probe_models=profile.discovery_strategy == "standard_models",
            )
        elif api_mode == "anthropic_messages":
            # Anthropic: GET {api_base}/models with x-api-key header
            url = f"{api_base.rstrip('/')}/models"
            if api_key:
                headers["x-api-key"] = api_key
                headers["anthropic-version"] = "2023-06-01"
        else:
            result["error"] = f"未知 api_mode: {api_mode}"
            return result

        # 发送请求（5 秒超时）
        request = urllib.request.Request(url, headers=headers, method="GET")
        start_time = time.time()

        with open_provider_request(request, timeout=5) as response:
            latency_ms = (time.time() - start_time) * 1000
            status_code = response.status

            if status_code == 200:
                result["status"] = "active"
                result["latency_ms"] = round(latency_ms, 2)
            else:
                result["status"] = "inactive"
                result["error"] = f"HTTP {status_code}"

    except urllib.error.HTTPError as e:
        result["status"] = "inactive"
        result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        result["status"] = "inactive"
        result["error"] = f"连接失败: {e.reason}"
    except TimeoutError:
        result["status"] = "inactive"
        result["error"] = "连接超时（5秒）"
    except Exception as e:
        result["status"] = "inactive"
        result["error"] = str(e)

    return result


def verify_provider_transport(provider_id: str, config: Any) -> Dict[str, Any]:
    """Check only a Provider HTTP endpoint; never send a model generation request."""
    provider_info = config.providers.get(provider_id, {})
    api_base = str(provider_info.get("api_base") or "").rstrip("/")
    api_key = str(provider_info.get("api_key") or "")
    api_mode = str(provider_info.get("api_mode") or "chat_completions")
    if not api_base:
        return {
            "status": "inactive",
            "error": "Provider 缺少 API Base",
            "error_code": "provider_base_missing",
            "error_scope": "connection",
            "error_category": "configuration",
        }
    url = f"{api_base}/api/tags" if api_mode == "ollama" else f"{api_base}/models"
    headers: Dict[str, str] = {"Accept": "application/json"}
    if api_mode == "anthropic_messages":
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    started = time.perf_counter()
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with open_provider_request(request, timeout=5) as response:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = int(response.status)
        if 200 <= status_code < 300:
            return {"status": "active", "latency_ms": latency_ms}
        if status_code in {404, 405, 501}:
            # The host is reachable but does not expose a discovery endpoint;
            # model entitlement remains unknown until an exact model call.
            return {
                "status": "active",
                "latency_ms": latency_ms,
                "transport_status": "reachable",
                "error_code": "reachability_endpoint_missing",
                "error_scope": "transport",
            }
        if status_code in {401, 403}:
            return {
                "status": "inactive",
                "error_code": "invalid_credential",
                "error_scope": "connection",
                "error_category": "authentication",
            }
        if status_code == 402:
            return {
                "status": "inactive",
                "error_code": "billing_blocked",
                "error_scope": "connection",
                "error_category": "billing",
            }
        if status_code == 429:
            return {
                "status": "inactive",
                "error_code": "quota_exhausted",
                "error_scope": "connection",
                "error_category": "quota",
            }
        return {
            "status": "inactive",
            "error_code": "provider_unreachable",
            "error_scope": "transport",
            "error_category": "server" if status_code >= 500 else "network",
        }
    except urllib.error.HTTPError as error:
        if error.code in {404, 405, 501}:
            return {
                "status": "active",
                "transport_status": "reachable",
                "error_code": "reachability_endpoint_missing",
                "error_scope": "transport",
            }
        if error.code in {401, 403}:
            code = "invalid_credential"
            category = "authentication"
            scope = "connection"
        elif error.code == 402:
            code = "billing_blocked"
            category = "billing"
            scope = "connection"
        elif error.code == 429:
            code = "quota_exhausted"
            category = "quota"
            scope = "connection"
        else:
            code = "provider_unreachable"
            category = "server" if error.code >= 500 else "network"
            scope = "transport"
        return {
            "status": "inactive",
            "error_code": code,
            "error_scope": scope,
            "error_category": category,
        }
    except urllib.error.URLError:
        return {
            "status": "inactive",
            "error_code": "network_error",
            "error_scope": "transport",
            "error_category": "network",
        }
    except TimeoutError:
        return {
            "status": "inactive",
            "error_code": "timeout",
            "error_scope": "transport",
            "error_category": "timeout",
        }
    except Exception:
        return {
            "status": "inactive",
            "error_code": "provider_unreachable",
            "error_scope": "transport",
            "error_category": "network",
        }
