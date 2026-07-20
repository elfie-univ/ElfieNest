"""Provider 原始模型发现与批量验证。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.gateway.llm_api import call_llm_api
from ai_runtime.models.catalog import verify_provider
from ai_runtime.providers.dispatch import detect_api_mode_for_url
from ai_runtime.providers.model_hints import configured_model_specs
from ai_runtime.validation.models import CheckResult, CheckStatus, ValidationSuite


@dataclass(frozen=True)
class DiscoveredModel:
    provider: str
    name: str
    source: str = "api"
    display_name: str = ""

    @property
    def model_id(self) -> str:
        return f"{self.provider}/{self.name}"


ModelCaller = Callable[
    [LLMRuntimeConfig, str, str, list[dict[str, Any]], float, int],
    str,
]


def discover_provider_models(
    provider_id: str,
    config: LLMRuntimeConfig,
    *,
    timeout: float = 10.0,
    allow_configured_fallback: bool = True,
) -> list[DiscoveredModel]:
    provider = config.providers.get(provider_id, {})
    api_base = str(provider.get("api_base", "")).rstrip("/")
    api_key = str(provider.get("api_key", ""))
    api_mode = str(provider.get("api_mode", "")) or detect_api_mode_for_url(api_base)
    if not api_base:
        raise ValueError(f"Provider '{provider_id}' 缺少 api_base")

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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        discovery_error = RuntimeError(
            f"模型发现失败：HTTP {exc.code} {exc.reason}"
        )
    except urllib.error.URLError as exc:
        discovery_error = RuntimeError(f"模型发现连接失败：{exc.reason}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        discovery_error = RuntimeError("模型发现接口返回了无效 JSON")

    names = _extract_model_names(api_mode, payload) if discovery_error is None else []
    if not names and allow_configured_fallback:
        specs = configured_model_specs(provider)
        if specs:
            return [
                DiscoveredModel(
                    provider_id,
                    item.model_id,
                    source="configured",
                    display_name=item.display_name,
                )
                for item in specs
            ]
    if discovery_error is not None:
        raise RuntimeError(
            f"{discovery_error}。该 Provider 可能不支持 /models，"
            "请在 Provider 配置中手工填写模型 ID"
        ) from discovery_error
    return [
        DiscoveredModel(provider_id, name, display_name=name)
        for name in sorted(set(names))
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


class ProviderValidationRunner:
    def __init__(
        self,
        config: LLMRuntimeConfig,
        *,
        model_caller: ModelCaller = call_llm_api,
    ) -> None:
        self.config = config
        self.model_caller = model_caller

    def verify_provider(self, provider_id: str) -> CheckResult:
        started = time.perf_counter()
        result = verify_provider(provider_id, self.config)
        duration_ms = (time.perf_counter() - started) * 1000
        active = result.get("status") == "active"
        measured_latency = float(result.get("latency_ms") or duration_ms)
        return CheckResult(
            check_id=f"provider.{provider_id}.health",
            status=CheckStatus.PASSED if active else CheckStatus.FAILED,
            message=(
                "Provider 连通性验证通过"
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
                message="模型冒烟调用通过",
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
            return CheckResult(
                check_id=f"provider.{provider_id}.model.{model_name}",
                status=CheckStatus.FAILED,
                message=str(exc),
                duration_ms=duration_ms,
                provider=provider_id,
                model=model_name,
                details={
                    "error_type": type(exc).__name__,
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
