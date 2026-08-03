"""模型目录系统 — 管理所有可用模型的元数据和状态。

提供:
- ModelEntry: 单个模型的完整元数据
- BUILTIN_MODEL_CATALOG: 内置模型目录（15+ 模型）
- ModelCatalog: 模型目录管理类
- verify_provider(): Provider 连通性验证

参考:
- OpenClaw 的 ModelProviderConfig (types.models.ts)
- Hermes Agent 的 HermesOverlay dataclass 模式
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai_runtime.providers.http import open_provider_request
from ai_runtime.providers.profiles import get_profile


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


# ---------------------------------------------------------------------------
# 内置模型目录（15+ 模型，来自 9 个 Provider）
# ---------------------------------------------------------------------------

BUILTIN_MODEL_CATALOG: Dict[str, ModelEntry] = {
    # Ollama 本地模型（免费）
    "ollama/qwen3.5:0.8b": ModelEntry(
        model_id="ollama/qwen3.5:0.8b",
        provider="ollama",
        display_name="Qwen3.5 0.8B",
        capabilities=["text", "code"],
        context_window=32000,
        cost_tier=0,
        visible=True,
        active=True,  # Ollama 始终 active
    ),
    "ollama/qwen2.5:0.5b": ModelEntry(
        model_id="ollama/qwen2.5:0.5b",
        provider="ollama",
        display_name="Qwen2.5 0.5B",
        capabilities=["text"],
        context_window=32000,
        cost_tier=0,
        visible=True,
        active=True,
    ),
    "ollama/llama3.2:1b": ModelEntry(
        model_id="ollama/llama3.2:1b",
        provider="ollama",
        display_name="Llama 3.2 1B",
        capabilities=["text"],
        context_window=128000,
        cost_tier=0,
        visible=True,
        active=True,
    ),
    "ollama/moondream": ModelEntry(
        model_id="ollama/moondream",
        provider="ollama",
        display_name="Moondream (Vision)",
        capabilities=["text", "vision"],
        context_window=4096,
        cost_tier=0,
        visible=True,
        active=True,
    ),
    "ollama/llava": ModelEntry(
        model_id="ollama/llava",
        provider="ollama",
        display_name="LLaVA (Vision)",
        capabilities=["text", "vision"],
        context_window=4096,
        cost_tier=0,
        visible=True,
        active=True,
    ),
    # OpenAI 模型
    "openai/gpt-4o": ModelEntry(
        model_id="openai/gpt-4o",
        provider="openai",
        display_name="GPT-4o",
        capabilities=["text", "vision", "audio", "code", "reasoning"],
        context_window=128000,
        cost_tier=4,
        visible=True,
        active=False,
    ),
    "openai/gpt-4o-mini": ModelEntry(
        model_id="openai/gpt-4o-mini",
        provider="openai",
        display_name="GPT-4o Mini",
        capabilities=["text", "vision", "code"],
        context_window=128000,
        cost_tier=2,
        visible=True,
        active=False,
    ),
    "openai/o1-mini": ModelEntry(
        model_id="openai/o1-mini",
        provider="openai",
        display_name="O1 Mini",
        capabilities=["text", "code", "reasoning"],
        context_window=128000,
        cost_tier=3,
        visible=True,
        active=False,
    ),
    # Anthropic 模型
    "anthropic/claude-3-opus-20240229": ModelEntry(
        model_id="anthropic/claude-3-opus-20240229",
        provider="anthropic",
        display_name="Claude 3 Opus",
        capabilities=["text", "vision", "code", "reasoning"],
        context_window=200000,
        cost_tier=4,
        visible=True,
        active=False,
    ),
    "anthropic/claude-3-sonnet-20240229": ModelEntry(
        model_id="anthropic/claude-3-sonnet-20240229",
        provider="anthropic",
        display_name="Claude 3 Sonnet",
        capabilities=["text", "vision", "code", "reasoning"],
        context_window=200000,
        cost_tier=3,
        visible=True,
        active=False,
    ),
    "anthropic/claude-3-haiku-20240307": ModelEntry(
        model_id="anthropic/claude-3-haiku-20240307",
        provider="anthropic",
        display_name="Claude 3 Haiku",
        capabilities=["text", "vision", "code"],
        context_window=200000,
        cost_tier=2,
        visible=True,
        active=False,
    ),
    # DeepSeek 模型
    "deepseek/deepseek-chat": ModelEntry(
        model_id="deepseek/deepseek-chat",
        provider="deepseek",
        display_name="DeepSeek Chat",
        capabilities=["text", "code"],
        context_window=64000,
        cost_tier=1,
        visible=True,
        active=False,
    ),
    "deepseek/deepseek-reasoner": ModelEntry(
        model_id="deepseek/deepseek-reasoner",
        provider="deepseek",
        display_name="DeepSeek Reasoner",
        capabilities=["text", "code", "reasoning"],
        context_window=64000,
        cost_tier=2,
        visible=True,
        active=False,
    ),
    # Google Gemini 模型
    "gemini/gemini-1.5-flash": ModelEntry(
        model_id="gemini/gemini-1.5-flash",
        provider="gemini",
        display_name="Gemini 1.5 Flash",
        capabilities=["text", "vision", "audio", "code"],
        context_window=1000000,
        cost_tier=1,
        visible=True,
        active=False,
    ),
    "gemini/gemini-1.5-pro": ModelEntry(
        model_id="gemini/gemini-1.5-pro",
        provider="gemini",
        display_name="Gemini 1.5 Pro",
        capabilities=["text", "vision", "audio", "code", "reasoning"],
        context_window=2000000,
        cost_tier=3,
        visible=True,
        active=False,
    ),
    # Ali Qwen 模型
    "qwen/qwen-turbo": ModelEntry(
        model_id="qwen/qwen-turbo",
        provider="qwen",
        display_name="Qwen Turbo",
        capabilities=["text", "code"],
        context_window=128000,
        cost_tier=1,
        visible=True,
        active=False,
    ),
    "qwen/qwen-max": ModelEntry(
        model_id="qwen/qwen-max",
        provider="qwen",
        display_name="Qwen Max",
        capabilities=["text", "code", "reasoning"],
        context_window=32000,
        cost_tier=3,
        visible=True,
        active=False,
    ),
    "qwen/qwen-vl-plus": ModelEntry(
        model_id="qwen/qwen-vl-plus",
        provider="qwen",
        display_name="Qwen VL Plus",
        capabilities=["text", "vision"],
        context_window=8000,
        cost_tier=2,
        visible=True,
        active=False,
    ),
    # xAI Grok 模型
    "xai/grok-beta": ModelEntry(
        model_id="xai/grok-beta",
        provider="xai",
        display_name="Grok Beta",
        capabilities=["text", "code"],
        context_window=128000,
        cost_tier=2,
        visible=True,
        active=False,
    ),
    "xai/grok-2-1212": ModelEntry(
        model_id="xai/grok-2-1212",
        provider="xai",
        display_name="Grok 2",
        capabilities=["text", "code", "reasoning"],
        context_window=128000,
        cost_tier=3,
        visible=True,
        active=False,
    ),
    # Mistral 模型
    "mistral/mistral-small-latest": ModelEntry(
        model_id="mistral/mistral-small-latest",
        provider="mistral",
        display_name="Mistral Small",
        capabilities=["text", "code"],
        context_window=32000,
        cost_tier=1,
        visible=True,
        active=False,
    ),
    "mistral/mistral-large-latest": ModelEntry(
        model_id="mistral/mistral-large-latest",
        provider="mistral",
        display_name="Mistral Large",
        capabilities=["text", "code", "reasoning"],
        context_window=128000,
        cost_tier=3,
        visible=True,
        active=False,
    ),
    "mistral/pixtral-12b-2409": ModelEntry(
        model_id="mistral/pixtral-12b-2409",
        provider="mistral",
        display_name="Pixtral 12B",
        capabilities=["text", "vision"],
        context_window=128000,
        cost_tier=2,
        visible=True,
        active=False,
    ),
    # Groq 模型
    "groq/llama-3.1-8b-instant": ModelEntry(
        model_id="groq/llama-3.1-8b-instant",
        provider="groq",
        display_name="Llama 3.1 8B (Groq)",
        capabilities=["text", "code"],
        context_window=128000,
        cost_tier=1,
        visible=True,
        active=False,
    ),
    "groq/llama-3.3-70b-versatile": ModelEntry(
        model_id="groq/llama-3.3-70b-versatile",
        provider="groq",
        display_name="Llama 3.3 70B (Groq)",
        capabilities=["text", "code", "reasoning"],
        context_window=128000,
        cost_tier=2,
        visible=True,
        active=False,
    ),
}


class ModelCatalog:
    """模型目录管理类。

    管理所有可用模型的元数据和状态，支持：
    - 按可见性/激活状态筛选
    - 按能力/服务商筛选
    - 更新模型状态
    """

    def __init__(self, config: Optional[Any] = None):
        """初始化模型目录。

        Args:
            config: LLMRuntimeConfig 实例，用于确定 provider 状态
        """
        self.config = config
        # 深拷贝内置目录，避免修改原数据
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
            for model_id, entry in BUILTIN_MODEL_CATALOG.items()
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
) -> Dict[str, Any]:
    import time

    from ai_runtime.providers.model_hints import configured_model_names

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

    configured_models = configured_model_names(provider_info)
    configured_test_model = str(provider_info.get("test_model") or "").strip()
    test_model = (
        configured_test_model
        if configured_test_model and configured_test_model != "custom-model"
        else configured_models[0]
        if configured_models
        else configured_test_model or "custom-model"
    )
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
) -> Dict[str, Any]:
    """Check a named OpenAI-compatible endpoint with a safe chat fallback."""
    import time

    headers: Dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    started = time.time()
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

    normalized_test_model = test_model.strip()
    if not normalized_test_model:
        return {
            "status": "inactive",
            "latency_ms": None,
            "error": "模型列表不可用且未配置安全测试模型",
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


def verify_provider(provider_id: str, config: Any) -> Dict[str, Any]:
    """验证 Provider 连通性。

    通过 HTTP 请求检查 provider 是否可达和可用。

    Args:
        provider_id: 服务商标识符 (ollama, openai, anthropic, etc.)
        config: LLMRuntimeConfig 实例

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
    profile = get_profile(provider_id)
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
                return _verify_custom_openai_provider(provider_info, api_base, api_key)
            return _verify_openai_compatible_provider(
                api_base,
                api_key,
                str(provider_info.get("test_model") or profile.test_model),
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
