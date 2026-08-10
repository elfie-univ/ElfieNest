"""Global capability configuration use cases."""

from __future__ import annotations

from collections import Counter
from collections.abc import Set
from typing import Optional

from app.features.accounts import AccountPrincipal

from .errors import (
    CapabilitiesForbidden,
    CapabilitiesUnavailable,
    CapabilitiesValidationError,
)
from .models import (
    CapabilitiesResult,
    CapabilityValidationResult,
    CapabilityValidationSuiteResult,
    CapabilityValidationSummary,
    ListCapabilitiesQuery,
    LocalFileCapabilityResult,
    UpdateLocalFileCapabilityCommand,
    UpdateWebSearchCapabilityCommand,
    VerifyCapabilityCommand,
    WebSearchCapabilityResult,
)
from .port_models import (
    StoredCapabilities,
    StoredLocalFileCapability,
    StoredWebSearchCapability,
)
from .ports import (
    CapabilitiesPortError,
    CapabilitiesStorePort,
    CapabilitySecretPort,
    CapabilityValidationPort,
)


class CapabilitiesService:
    def __init__(
        self,
        store: CapabilitiesStorePort,
        secrets: CapabilitySecretPort,
        validator: CapabilityValidationPort,
    ) -> None:
        self._store = store
        self._secrets = secrets
        self._validator = validator

    def list_capabilities(
        self,
        principal: AccountPrincipal,
        query: ListCapabilitiesQuery,
    ) -> CapabilitiesResult:
        _ = query
        self._require_manager(principal)
        try:
            return self._result(self._store.load_capabilities())
        except CapabilitiesPortError as error:
            raise CapabilitiesUnavailable from error

    def update_web_search(
        self,
        principal: AccountPrincipal,
        command: UpdateWebSearchCapabilityCommand,
    ) -> WebSearchCapabilityResult:
        self._require_manager(principal)
        if not command.fields and command.api_key is None:
            raise CapabilitiesValidationError("至少需要更新一个字段")
        try:
            current = self._store.load_capabilities().web_search
            provider = current.provider
            if "provider" in command.fields:
                if command.provider is None:
                    raise CapabilitiesValidationError("provider 不能为空")
                provider = command.provider
            enabled = self._updated_bool(
                "enabled", command.fields, command.enabled, current.enabled
            )
            api_base = self._updated_string(
                "api_base", command.fields, command.api_base, current.api_base
            )
            max_results = self._updated_integer(
                "max_results",
                command.fields,
                command.max_results,
                current.max_results,
            )
            max_results = max(1, min(max_results, 10))
            max_result_bytes = self._updated_integer(
                "max_result_bytes",
                command.fields,
                command.max_result_bytes,
                current.max_result_bytes,
            )
            updated = StoredWebSearchCapability(
                enabled=enabled,
                provider=provider,
                api_base=api_base,
                credential_ref=current.credential_ref,
                max_results=max_results,
                max_result_bytes=max_result_bytes,
                timeout_seconds=current.timeout_seconds,
                max_tool_calls=current.max_tool_calls,
                max_total_result_bytes=current.max_total_result_bytes,
            )
            if command.api_key is not None:
                credential_ref = self._secrets.set_web_search_secret(command.api_key)
                updated = StoredWebSearchCapability(
                    enabled=updated.enabled,
                    provider=updated.provider,
                    api_base=updated.api_base,
                    credential_ref=credential_ref,
                    max_results=updated.max_results,
                    max_result_bytes=updated.max_result_bytes,
                    timeout_seconds=updated.timeout_seconds,
                    max_tool_calls=updated.max_tool_calls,
                    max_total_result_bytes=updated.max_total_result_bytes,
                )
            saved = self._store.save_web_search(updated, command.fields)
            return self._web_search_result(saved.web_search)
        except CapabilitiesValidationError:
            raise
        except (CapabilitiesPortError, OSError, ValueError) as error:
            raise CapabilitiesUnavailable from error

    def update_local_file(
        self,
        principal: AccountPrincipal,
        command: UpdateLocalFileCapabilityCommand,
    ) -> LocalFileCapabilityResult:
        self._require_manager(principal)
        if not command.fields:
            raise CapabilitiesValidationError("至少需要更新一个字段")
        try:
            current = self._store.load_capabilities().local_file
            updated = StoredLocalFileCapability(
                enabled=self._updated_bool(
                    "enabled", command.fields, command.enabled, current.enabled
                ),
                root=current.root,
                root_policy=current.root_policy,
                max_read_bytes=self._updated_integer(
                    "max_read_bytes",
                    command.fields,
                    command.max_read_bytes,
                    current.max_read_bytes,
                ),
                max_items=current.max_items,
                max_result_bytes=current.max_result_bytes,
                max_tool_calls=current.max_tool_calls,
                max_total_result_bytes=current.max_total_result_bytes,
            )
            saved = self._store.save_local_file(updated, command.fields)
            return self._local_file_result(saved.local_file)
        except CapabilitiesValidationError:
            raise
        except (CapabilitiesPortError, OSError, ValueError) as error:
            raise CapabilitiesUnavailable from error

    def verify_capability(
        self,
        principal: AccountPrincipal,
        command: VerifyCapabilityCommand,
    ) -> CapabilityValidationSuiteResult:
        self._require_manager(principal)
        try:
            stored = self._validator.verify(command.capability_key)
        except CapabilitiesPortError as error:
            raise CapabilitiesUnavailable from error
        result = CapabilityValidationResult(
            check_id=stored.check_id,
            status=stored.status,
            message=stored.message,
            duration_ms=stored.duration_ms,
            provider=stored.provider,
            model=stored.model,
            error_type=stored.error_type,
        )
        counts: Counter[str] = Counter((stored.status,))
        return CapabilityValidationSuiteResult(
            name=f"tool:{command.capability_key}",
            passed=stored.status != "failed",
            summary=CapabilityValidationSummary(
                passed=counts["passed"],
                failed=counts["failed"],
                warning=counts["warning"],
                skipped=counts["skipped"],
            ),
            results=(result,),
        )

    @staticmethod
    def _require_manager(principal: AccountPrincipal) -> None:
        if principal.role not in {"owner", "admin"}:
            raise CapabilitiesForbidden("只有家庭管理员可以管理系统能力")

    def _result(self, stored: StoredCapabilities) -> CapabilitiesResult:
        return CapabilitiesResult(
            web_search=self._web_search_result(stored.web_search),
            local_file=self._local_file_result(stored.local_file),
        )

    def _web_search_result(
        self, stored: StoredWebSearchCapability
    ) -> WebSearchCapabilityResult:
        return WebSearchCapabilityResult(
            enabled=stored.enabled,
            provider=stored.provider,
            api_base=stored.api_base,
            max_results=stored.max_results,
            max_result_bytes=stored.max_result_bytes,
            timeout_seconds=stored.timeout_seconds,
            max_tool_calls=stored.max_tool_calls,
            max_total_result_bytes=stored.max_total_result_bytes,
            has_api_key=self._secrets.has_secret(stored.credential_ref),
        )

    @staticmethod
    def _local_file_result(
        stored: StoredLocalFileCapability,
    ) -> LocalFileCapabilityResult:
        return LocalFileCapabilityResult(
            enabled=stored.enabled,
            root=stored.root,
            root_policy=stored.root_policy,
            max_read_bytes=stored.max_read_bytes,
            max_items=stored.max_items,
            max_result_bytes=stored.max_result_bytes,
            max_tool_calls=stored.max_tool_calls,
            max_total_result_bytes=stored.max_total_result_bytes,
            has_api_key=False,
        )

    @staticmethod
    def _updated_bool(
        field: str,
        fields: Set[str],
        value: Optional[bool],
        current: bool,
    ) -> bool:
        if field not in fields:
            return current
        if value is None:
            raise CapabilitiesValidationError(f"{field} 不能为空")
        return value

    @staticmethod
    def _updated_integer(
        field: str,
        fields: Set[str],
        value: Optional[int],
        current: int,
    ) -> int:
        if field not in fields:
            return current
        if value is None:
            raise CapabilitiesValidationError(f"{field} 不能为空")
        return value

    @staticmethod
    def _updated_string(
        field: str,
        fields: Set[str],
        value: Optional[str],
        current: str,
    ) -> str:
        if field not in fields:
            return current
        if value is None:
            raise CapabilitiesValidationError(f"{field} 不能为空")
        return value


__all__ = ("CapabilitiesService",)
