"""Provider 原始模型发现与批量验证。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal, Mapping
from urllib.parse import urlparse

from infrastructure.models.catalog import verify_provider
from infrastructure.models.inference.llm_api import call_llm_api
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.provider_errors import classify_provider_error
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.providers.dispatch import detect_api_mode_for_url
from infrastructure.models.providers.http import (
    open_provider_request,
    read_provider_response,
)
from infrastructure.models.providers.model_hints import configured_model_specs
from infrastructure.models.validation.validation_models import (
    CheckResult,
    CheckStatus,
    ValidationSuite,
)


@dataclass(frozen=True)
class DiscoveredModel:
    provider: str
    name: str
    source: str = "api"
    display_name: str = ""
    # ``True`` means the live ID is also present in the product-maintained
    # core list.  It is an inventory/display hint only; it does not assert
    # that the endpoint supports any capability.
    curated: bool = False

    @property
    def model_id(self) -> str:
        return f"{self.provider}/{self.name}"


DiscoverySource = Literal[
    "bundled_catalog",
    "ollama",
    "provider_models",
    "configured",
]


@dataclass(frozen=True)
class ModelDiscoveryResult:
    """One bounded discovery attempt and its authority/completeness facts."""

    provider: str
    models: tuple[DiscoveredModel, ...]
    source: DiscoverySource
    complete: bool
    authoritative: bool
    error: str | None = None
    error_code: str | None = None


ModelCaller = Callable[
    [ModelExecutionConfig, str, str, list[dict[str, Any]], float, int],
    str,
]


def discover_provider_models(
    provider_id: str,
    config: ModelExecutionConfig,
    *,
    timeout: float = 10.0,
    allow_configured_fallback: bool = True,
) -> list[DiscoveredModel]:
    result = discover_provider_models_result(
        provider_id,
        config,
        timeout=timeout,
        allow_configured_fallback=allow_configured_fallback,
    )
    if result.models:
        return list(result.models)
    if result.error:
        raise RuntimeError(result.error)
    return []


def discover_provider_models_result(
    provider_id: str,
    config: ModelExecutionConfig,
    *,
    timeout: float = 10.0,
    allow_configured_fallback: bool = True,
    max_models: int = 256,
) -> ModelDiscoveryResult:
    """Discover models using the product-declared strategy.

    ``catalog_only`` never makes a generic ``/models`` call.  The result
    carries completeness so callers can avoid treating partial data as an
    authoritative empty entitlement.
    """
    provider = config.providers.get(provider_id, {})
    profile = _provider_profile(config, provider_id, provider)
    strategy = str(provider.get("discovery_strategy") or "")
    if not strategy and profile is not None:
        strategy = profile.discovery_strategy

    if strategy == "catalog_only":
        bundled = _bundled_model_names(provider, profile)
        if len(bundled) > max_models:
            return ModelDiscoveryResult(
                provider_id,
                (),
                "bundled_catalog",
                complete=False,
                authoritative=False,
                error=f"内置模型清单超过上限 {max_models}",
            )
        return ModelDiscoveryResult(
            provider_id,
            tuple(
                DiscoveredModel(
                    provider_id,
                    model_id,
                    source="bundled_catalog",
                    display_name=model_id,
                )
                for model_id in bundled
            ),
            "bundled_catalog",
            complete=True,
            authoritative=True,
        )

    if strategy == "provider_adapter":
        catalog_id = str(provider.get("catalog_id") or provider_id)
        if catalog_id == "volcengine_coding_plan":
            return _discover_volcengine_coding_plan_models(
                provider_id,
                provider,
                profile,
                max_models=max_models,
            )
        configured = _configured_models(provider, config.provider_catalog)
        return ModelDiscoveryResult(
            provider_id,
            tuple(
                DiscoveredModel(
                    provider_id,
                    model_id,
                    source="configured",
                    display_name=display_name,
                )
                for model_id, display_name in configured
            ),
            "configured",
            complete=False,
            authoritative=False,
            error="Provider 专属发现 Adapter 尚未提供模型清单",
        )

    api_base = str(provider.get("api_base", "")).rstrip("/")
    api_key = str(provider.get("api_key", ""))
    api_mode = str(provider.get("api_mode", "")) or detect_api_mode_for_url(api_base)
    if not api_base:
        return ModelDiscoveryResult(
            provider_id,
            (),
            "configured",
            complete=False,
            authoritative=False,
            error=f"Provider '{provider_id}' is missing api_base",
        )

    if api_mode == "ollama":
        url = f"{api_base}/api/tags"
        headers: dict[str, str] = {}
    else:
        url = f"{api_base}/models"
        headers = {"Accept": "application/json"}
        if api_mode == "anthropic_messages":
            if api_key:
                headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        elif api_key:
            headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, headers=headers, method="GET")
    discovery_error: RuntimeError | None = None
    payload: Any = {}
    try:
        with open_provider_request(request, timeout=timeout) as response:
            payload = json.loads(
                read_provider_response(
                    response,
                    max_bytes=4 * 1024 * 1024,
                    deadline_seconds=timeout,
                ).decode("utf-8")
            )
    except urllib.error.HTTPError as exc:
        discovery_error = RuntimeError(
            f"Model discovery failed: HTTP {exc.code} {exc.reason}"
        )
    except urllib.error.URLError as exc:
        discovery_error = RuntimeError(
            f"Model discovery connection failed: {exc.reason}"
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TimeoutError):
        discovery_error = RuntimeError("Model discovery endpoint returned invalid JSON")

    if discovery_error is None and not _has_model_list(api_mode, payload):
        discovery_error = RuntimeError("模型清单响应结构无效")
    names = (
        _normalize_discovered_model_names(
            _extract_model_names(api_mode, payload), profile
        )
        if discovery_error is None
        else []
    )
    if discovery_error is None and len(names) > max_models:
        discovery_error = RuntimeError(f"模型清单超过上限 {max_models}")
        names = []
    if discovery_error is None and isinstance(payload, dict):
        if payload.get("has_more") is True or payload.get("next_cursor"):
            discovery_error = RuntimeError("模型清单分页未完整读取")
            names = []

    # Keep the complete live inventory, but mark the product-maintained core
    # IDs so the administration layer can show those by default and put the
    # rest in a collapsed "other discovered" section.  The raw /models list
    # is therefore useful without flooding the normal product UI or requiring
    # the user to type every non-core ID again.
    # An authenticated, complete empty response is an authoritative empty
    # entitlement.  Falling back to configured IDs here would falsely turn a
    # recommendation into an account-owned model.
    if discovery_error is not None and allow_configured_fallback:
        configured = _configured_models(provider, config.provider_catalog)
        if configured:
            return ModelDiscoveryResult(
                provider_id,
                tuple(
                    DiscoveredModel(
                        provider_id,
                        model_id,
                        source="configured",
                        display_name=display_name,
                    )
                    for model_id, display_name in configured
                ),
                "configured",
                complete=False,
                authoritative=False,
                error=str(discovery_error) if discovery_error else None,
            )
    if discovery_error is not None:
        return ModelDiscoveryResult(
            provider_id,
            (),
            "ollama" if api_mode == "ollama" else "provider_models",
            complete=False,
            authoritative=False,
            error=(
                f"{discovery_error}。该 Provider 可能不支持 /models，"
                "Please manually enter model ID in Provider configuration"
            ),
            error_code=None,
        )
    live_names = set(names)
    names = _augment_declared_free_models(names, profile)
    curated_ids = set(_bundled_model_names(provider, profile))
    return ModelDiscoveryResult(
        provider_id,
        tuple(
            DiscoveredModel(
                provider_id,
                name,
                source=(
                    "bundled_catalog"
                    if name not in live_names and api_mode != "ollama"
                    else "ollama"
                    if api_mode == "ollama"
                    else "provider_models"
                ),
                display_name=name,
                curated=name in curated_ids,
            )
            for name in sorted(set(names))
        ),
        "ollama" if api_mode == "ollama" else "provider_models",
        complete=True,
        authoritative=True,
    )


def _discover_volcengine_coding_plan_models(
    provider_id: str,
    provider: Mapping[str, Any],
    profile: Any,
    *,
    max_models: int,
) -> ModelDiscoveryResult:
    """Return the Coding Plan product allowlist without calling ``/models``.

    The Coding Plan endpoint exposes a broad platform inventory containing
    models that are not part of this product and generally cannot be used by
    the subscription.  The Provider-specific adapter therefore treats the
    versioned ``bundled_models`` list as its only model source.
    """
    api_base = str(provider.get("api_base", "")).rstrip("/")
    parsed_path = urlparse(api_base).path.rstrip("/")
    if "/api/coding/" not in f"{parsed_path}/":
        return ModelDiscoveryResult(
            provider_id,
            (),
            "bundled_catalog",
            complete=False,
            authoritative=False,
            error="火山引擎 Coding Plan 的 API Base 必须位于 /api/coding 网关",
        )
    bundled = _bundled_model_names(provider, profile)
    if not bundled:
        return ModelDiscoveryResult(
            provider_id,
            (),
            "bundled_catalog",
            complete=False,
            authoritative=False,
            error="火山引擎 Coding Plan 缺少核心 bundled_models 清单",
        )
    if len(bundled) > max_models:
        return ModelDiscoveryResult(
            provider_id,
            (),
            "bundled_catalog",
            complete=False,
            authoritative=False,
            error=f"核心模型清单超过上限 {max_models}",
        )
    return ModelDiscoveryResult(
        provider_id,
        tuple(
            DiscoveredModel(
                provider_id,
                name,
                source="bundled_catalog",
                display_name=name,
                curated=True,
            )
            for name in bundled
        ),
        "bundled_catalog",
        complete=True,
        authoritative=True,
    )


def _discover_models_endpoint(
    provider_id: str,
    provider: Mapping[str, Any],
    profile: Any,
    *,
    api_base: str,
    api_key: str,
    api_mode: str,
    timeout: float,
    allow_configured_fallback: bool,
    max_models: int,
    source_error_prefix: str = "Model discovery",
) -> ModelDiscoveryResult:
    """Read one bounded, complete OpenAI-compatible model inventory."""
    if not api_base:
        return _configured_discovery_fallback(
            provider_id,
            provider,
            profile,
            error=f"{source_error_prefix} 缺少 api_base",
            allow_configured_fallback=allow_configured_fallback,
        )
    url = f"{api_base}/models"
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_mode == "anthropic_messages":
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, headers=headers, method="GET")
    discovery_error: RuntimeError | None = None
    payload: Any = {}
    try:
        with open_provider_request(request, timeout=timeout) as response:
            payload = json.loads(
                read_provider_response(
                    response,
                    max_bytes=4 * 1024 * 1024,
                    deadline_seconds=timeout,
                ).decode("utf-8")
            )
    except urllib.error.HTTPError as exc:
        discovery_error = RuntimeError(
            f"{source_error_prefix}失败: HTTP {exc.code} {exc.reason}"
        )
    except urllib.error.URLError as exc:
        discovery_error = RuntimeError(f"{source_error_prefix}连接失败: {exc.reason}")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TimeoutError):
        discovery_error = RuntimeError(f"{source_error_prefix}返回无效 JSON")

    if discovery_error is None and not _has_model_list(api_mode, payload):
        discovery_error = RuntimeError(f"{source_error_prefix}响应结构无效")
    names = (
        _normalize_discovered_model_names(
            _extract_model_names(api_mode, payload), profile
        )
        if discovery_error is None
        else []
    )
    if discovery_error is None and len(names) > max_models:
        discovery_error = RuntimeError(f"{source_error_prefix}超过上限 {max_models}")
        names = []
    if discovery_error is None and isinstance(payload, dict):
        if payload.get("has_more") is True or payload.get("next_cursor"):
            discovery_error = RuntimeError(f"{source_error_prefix}分页未完整读取")
            names = []

    if discovery_error is not None:
        return _configured_discovery_fallback(
            provider_id,
            provider,
            profile,
            error=str(discovery_error),
            allow_configured_fallback=allow_configured_fallback,
        )
    live_names = set(names)
    names = _augment_declared_free_models(names, profile)
    curated_ids = set(_bundled_model_names(provider, profile))
    return ModelDiscoveryResult(
        provider_id,
        tuple(
            DiscoveredModel(
                provider_id,
                name,
                source=(
                    "bundled_catalog" if name not in live_names else "provider_models"
                ),
                display_name=name,
                curated=name in curated_ids,
            )
            for name in sorted(set(names))
        ),
        "provider_models",
        complete=True,
        authoritative=True,
    )


def _configured_discovery_fallback(
    provider_id: str,
    provider: Mapping[str, Any],
    profile: Any,
    *,
    error: str,
    allow_configured_fallback: bool,
) -> ModelDiscoveryResult:
    if allow_configured_fallback:
        try:
            configured = _configured_models(provider)
        except ValueError:
            configured = []
        if configured:
            return ModelDiscoveryResult(
                provider_id,
                tuple(
                    DiscoveredModel(
                        provider_id,
                        model_id,
                        source="configured",
                        display_name=display_name,
                    )
                    for model_id, display_name in configured
                ),
                "configured",
                complete=False,
                authoritative=False,
                error=error,
            )
    return ModelDiscoveryResult(
        provider_id,
        (),
        "provider_models",
        complete=False,
        authoritative=False,
        error=f"{error}。该 Provider 可能不支持受限 /models，请手工添加模型",
    )


def _provider_profile(
    config: ModelExecutionConfig,
    provider_id: str,
    provider: Mapping[str, Any],
) -> Any:
    catalog = config.provider_catalog
    if catalog is None:
        raise ValueError("Provider validation requires an injected provider catalog")
    catalog_id = str(provider.get("catalog_id") or provider_id)
    return catalog.products.get(catalog_id) or catalog.profiles.get(provider_id)


def _bundled_model_names(provider: Mapping[str, Any], profile: Any) -> list[str]:
    raw = provider.get("bundled_models")
    if not isinstance(raw, (list, tuple)) and profile is not None:
        raw = profile.bundled_models
    if not isinstance(raw, (list, tuple)):
        return []
    return list(dict.fromkeys(str(item).strip() for item in raw if str(item).strip()))


def _normalize_discovered_model_names(names: Iterable[str], profile: Any) -> list[str]:
    """Normalize only provider-specific wrappers around endpoint model IDs."""
    legacy_provider_id = "" if profile is None else str(profile.legacy_provider_id)
    normalized: list[str] = []
    for name in names:
        candidate = name.strip()
        if legacy_provider_id == "gemini" and candidate.startswith("models/"):
            candidate = candidate.removeprefix("models/")
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _augment_declared_free_models(names: Iterable[str], profile: Any) -> list[str]:
    """Include documented free endpoints omitted by the provider inventory.

    Zhipu's general ``/models`` response currently omits its two documented
    free Flash endpoints. Gemini is included for the same resilience when a
    compatible endpoint returns a restricted inventory. Other providers keep
    the live inventory as the sole entitlement authority because their free
    catalog snapshots can change independently.
    """
    result = list(dict.fromkeys(names))
    if profile is None or str(profile.legacy_provider_id) not in {"gemini", "zhipu"}:
        return result
    for model_id in profile.free_model_ids:
        if model_id not in result:
            result.append(model_id)
    return result


def _configured_models(
    provider: Mapping[str, Any], catalog: ProviderCatalog | None = None
) -> list[tuple[str, str]]:
    return [
        (item.model_id, item.display_name)
        for item in configured_model_specs(provider, catalog=catalog)
    ]


def _extract_model_names(api_mode: str, payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_models = (
        payload.get("models", []) if api_mode == "ollama" else payload.get("data", [])
    )
    if not isinstance(raw_models, list):
        return []
    names: list[str] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        raw_name = (
            item.get("name") or item.get("model")
            if api_mode == "ollama"
            else item.get("id")
        )
        if isinstance(raw_name, str) and raw_name.strip():
            names.append(raw_name.strip())
    return names


def _has_model_list(api_mode: str, payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    key = "models" if api_mode == "ollama" else "data"
    return isinstance(payload.get(key), list)


class ProviderValidationRunner:
    def __init__(
        self,
        config: ModelExecutionConfig,
        *,
        model_caller: ModelCaller = call_llm_api,
    ) -> None:
        self.config = config
        self.model_caller = model_caller

    def verify_provider(self, provider_id: str) -> CheckResult:
        started = time.perf_counter()
        result = verify_provider(
            provider_id,
            self.config,
            provider_catalog=self.config.provider_catalog,
        )
        duration_ms = (time.perf_counter() - started) * 1000
        active = result.get("status") == "active"
        measured_latency = float(result.get("latency_ms") or duration_ms)
        return CheckResult(
            check_id=f"provider.{provider_id}.health",
            status=CheckStatus.PASSED if active else CheckStatus.FAILED,
            message=(
                "Provider connectivity validation passed"
                if active
                else str(result.get("error") or "Provider 不可用")
            ),
            duration_ms=measured_latency,
            provider=provider_id,
            details={
                "provider_status": str(result.get("status", "unverified")),
                "latency_class": classify_latency(measured_latency),
            },
        )

    def verify_model(self, provider_id: str, model_name: str) -> CheckResult:
        started = time.perf_counter()
        try:
            response = self.model_caller(
                self.config,
                provider_id,
                model_name,
                [{"role": "user", "content": "Reply with OK."}],
                0.0,
                8,
            )
            duration_ms = (time.perf_counter() - started) * 1000
            if not str(response).strip():
                return CheckResult(
                    check_id=f"provider.{provider_id}.model.{model_name}",
                    status=CheckStatus.FAILED,
                    message="模型返回空响应",
                    duration_ms=duration_ms,
                    provider=provider_id,
                    model=model_name,
                    details={"latency_class": classify_latency(duration_ms)},
                )
            return CheckResult(
                check_id=f"provider.{provider_id}.model.{model_name}",
                status=CheckStatus.PASSED,
                message="Model smoke test passed",
                duration_ms=duration_ms,
                provider=provider_id,
                model=model_name,
                details={
                    "response_chars": len(str(response)),
                    "latency_class": classify_latency(duration_ms),
                },
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            classification = classify_provider_error(exc)
            return CheckResult(
                check_id=f"provider.{provider_id}.model.{model_name}",
                status=CheckStatus.FAILED,
                message=str(exc),
                duration_ms=duration_ms,
                provider=provider_id,
                model=model_name,
                details={
                    "error_type": type(exc).__name__,
                    "error_code": classification.code,
                    "error_scope": classification.scope,
                    "error_category": classification.category,
                    "latency_class": classify_latency(duration_ms),
                },
            )

    def verify_models(
        self,
        provider_id: str,
        model_names: Iterable[str] | None = None,
        *,
        max_models: int | None = None,
    ) -> ValidationSuite:
        selected = list(model_names or ())
        if not selected:
            try:
                selected = [
                    item.name
                    for item in discover_provider_models(provider_id, self.config)
                ]
            except Exception as exc:
                return ValidationSuite(
                    name=f"provider:{provider_id}",
                    results=(
                        CheckResult(
                            check_id=f"provider.{provider_id}.discover_models",
                            status=CheckStatus.FAILED,
                            message=str(exc),
                            provider=provider_id,
                            details={"error_type": type(exc).__name__},
                        ),
                    ),
                )
        if max_models is not None:
            selected = selected[: max(max_models, 0)]
        if not selected:
            return ValidationSuite(
                name=f"provider:{provider_id}",
                results=(
                    CheckResult(
                        check_id=f"provider.{provider_id}.discover_models",
                        status=CheckStatus.WARNING,
                        message="Provider 未返回任何可验证模型",
                        provider=provider_id,
                    ),
                ),
            )
        return ValidationSuite(
            name=f"provider:{provider_id}",
            results=tuple(
                self.verify_model(provider_id, model_name) for model_name in selected
            ),
        )


def classify_latency(duration_ms: float) -> str:
    if duration_ms <= 1_500:
        return "fast"
    if duration_ms <= 5_000:
        return "normal"
    return "slow"
