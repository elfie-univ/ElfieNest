"""Adapter delegating capability checks to the existing Runtime validator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, cast

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.validation.models import CheckResult
from ai_runtime.validation.tools import DirectToolValidationRunner
from app.features.configuration.capabilities import (
    CapabilitiesPortError,
    CapabilityKey,
    StoredValidationResult,
    ValidationStatus,
)


class ValidationRunner(Protocol):
    def verify_web_search(self) -> CheckResult: ...

    def verify_file_sandbox(self) -> CheckResult: ...


RunnerFactory = Callable[[LLMRuntimeConfig], ValidationRunner]


class DirectCapabilityValidationAdapter:
    """Translate the sole AI Runtime validator into the App-owned Port model."""

    def __init__(
        self,
        config_loader: Callable[[], LLMRuntimeConfig] = LLMRuntimeConfig.load,
        runner_factory: RunnerFactory = DirectToolValidationRunner,
    ) -> None:
        self._config_loader = config_loader
        self._runner_factory = runner_factory

    def verify(self, capability_key: CapabilityKey) -> StoredValidationResult:
        try:
            runner = self._runner_factory(self._config_loader())
            result = (
                runner.verify_web_search()
                if capability_key == "web_search"
                else runner.verify_file_sandbox()
            )
            return self._stored_result(result)
        except (OSError, RuntimeError, ValueError) as error:
            raise CapabilitiesPortError("系统能力验证不可用") from error

    @staticmethod
    def _stored_result(result: CheckResult) -> StoredValidationResult:
        status = result.status.value
        if status not in {"passed", "failed", "warning", "skipped"}:
            raise CapabilitiesPortError("系统能力验证返回未知状态")
        details: Mapping[str, object] = result.details
        raw_error_type = details.get("error_type")
        error_type = raw_error_type if isinstance(raw_error_type, str) else None
        return StoredValidationResult(
            check_id=result.check_id,
            status=cast(ValidationStatus, status),
            message=result.message,
            duration_ms=result.duration_ms,
            provider=result.provider,
            model=result.model,
            error_type=error_type,
        )


__all__ = ("DirectCapabilityValidationAdapter",)
