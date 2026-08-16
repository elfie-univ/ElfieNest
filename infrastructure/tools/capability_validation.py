"""Adapter delegating capability checks to the existing Runtime validator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, cast

from pydantic import JsonValue

from app.features.configuration.capabilities import (
    CapabilitiesPortError,
    CapabilityKey,
    StoredValidationResult,
    ValidationStatus,
)
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.validation.validation_models import CheckResult


class ValidationRunner(Protocol):
    def verify_web_search(self) -> CheckResult: ...

    def verify_file_sandbox(self) -> CheckResult: ...


RunnerFactory = Callable[[ModelExecutionConfig], ValidationRunner]


class DirectCapabilityValidationAdapter:
    """Translate the sole safe-tool validator into the App-owned Port model."""

    def __init__(
        self,
        config_loader: Callable[[], ModelExecutionConfig],
        runner_factory: RunnerFactory,
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
        details: Mapping[str, JsonValue] = result.details
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
