from __future__ import annotations

from typing import FrozenSet

import pytest

from app.features.accounts import AccountPrincipal
from app.features.configuration.capabilities import (
    CapabilitiesForbidden,
    CapabilitiesPortError,
    CapabilitiesService,
    ListCapabilitiesQuery,
    LocalFileUpdateField,
    StoredCapabilities,
    StoredLocalFileCapability,
    StoredValidationResult,
    StoredWebSearchCapability,
    UpdateLocalFileCapabilityCommand,
    UpdateWebSearchCapabilityCommand,
    VerifyCapabilityCommand,
    WebSearchUpdateField,
)


def _stored() -> StoredCapabilities:
    return StoredCapabilities(
        web_search=StoredWebSearchCapability(
            enabled=True,
            provider="duckduckgo",
            api_base="",
            credential_ref="ELFIE_WEB_SEARCH_API_KEY",
            max_results=3,
            max_result_bytes=16000,
            timeout_seconds=5.0,
            max_tool_calls=3,
            max_total_result_bytes=48000,
        ),
        local_file=StoredLocalFileCapability(
            enabled=False,
            root="",
            root_policy="elfie_workspace",
            max_read_bytes=65536,
            max_items=200,
            max_result_bytes=16000,
            max_tool_calls=3,
            max_total_result_bytes=48000,
        ),
    )


class FakeStore:
    def __init__(self) -> None:
        self.value = _stored()
        self.loads = 0
        self.web_saves = 0
        self.local_saves = 0

    def load_capabilities(self) -> StoredCapabilities:
        self.loads += 1
        return self.value

    def save_web_search(
        self,
        capability: StoredWebSearchCapability,
        fields: FrozenSet[WebSearchUpdateField],
    ) -> StoredCapabilities:
        _ = fields
        self.web_saves += 1
        self.value = StoredCapabilities(capability, self.value.local_file)
        return self.value

    def save_local_file(
        self,
        capability: StoredLocalFileCapability,
        fields: FrozenSet[LocalFileUpdateField],
    ) -> StoredCapabilities:
        _ = fields
        self.local_saves += 1
        self.value = StoredCapabilities(self.value.web_search, capability)
        return self.value


class FakeSecrets:
    def __init__(self) -> None:
        self.value = ""
        self.writes: list[str] = []

    def has_secret(self, credential_ref: str) -> bool:
        _ = credential_ref
        return bool(self.value)

    def set_web_search_secret(self, api_key: str) -> str:
        self.value = api_key
        self.writes.append(api_key)
        return "ELFIE_WEB_SEARCH_API_KEY"


class FakeValidator:
    def verify(self, capability_key):
        return StoredValidationResult(
            check_id=f"tool.{capability_key}",
            status="passed",
            message="validation passed",
            duration_ms=1.5,
            provider=None,
            model=None,
            error_type=None,
        )


def _principal(role="owner") -> AccountPrincipal:
    return AccountPrincipal(1, "person", role, "chat")


def _service():
    store = FakeStore()
    secrets = FakeSecrets()
    return CapabilitiesService(store, secrets, FakeValidator()), store, secrets


def test_list_is_read_only_and_returns_only_the_two_current_capabilities():
    service, store, _secrets = _service()

    result = service.list_capabilities(_principal(), ListCapabilitiesQuery())

    assert result.web_search.provider == "duckduckgo"
    assert result.local_file.root_policy == "elfie_workspace"
    assert store.loads == 1
    assert store.web_saves == 0
    assert store.local_saves == 0


def test_member_cannot_read_or_mutate_global_capabilities():
    service, store, _secrets = _service()

    with pytest.raises(CapabilitiesForbidden):
        service.list_capabilities(_principal("member"), ListCapabilitiesQuery())

    assert store.loads == 0


def test_web_search_update_preserves_existing_fields_clamps_and_writes_secret():
    service, store, secrets = _service()

    result = service.update_web_search(
        _principal(),
        UpdateWebSearchCapabilityCommand(
            fields=frozenset({"provider", "max_results"}),
            provider="brave",
            max_results=99,
            api_key="local-only-key",
        ),
    )

    assert result.provider == "brave"
    assert result.max_results == 10
    assert result.max_result_bytes == 16000
    assert result.has_api_key is True
    assert secrets.writes == ["local-only-key"]
    assert store.web_saves == 1


def test_local_file_update_preserves_non_editable_sandbox_facts():
    service, store, _secrets = _service()

    result = service.update_local_file(
        _principal("admin"),
        UpdateLocalFileCapabilityCommand(
            fields=frozenset({"enabled", "max_read_bytes"}),
            enabled=True,
            max_read_bytes=32768,
        ),
    )

    assert result.enabled is True
    assert result.max_read_bytes == 32768
    assert result.root_policy == "elfie_workspace"
    assert result.max_items == 200
    assert store.local_saves == 1


def test_verify_maps_existing_validator_result_to_fixed_summary():
    service, _store, _secrets = _service()

    result = service.verify_capability(
        _principal(), VerifyCapabilityCommand("local_file")
    )

    assert result.name == "tool:local_file"
    assert result.passed is True
    assert result.summary.passed == 1
    assert result.summary.failed == 0
    assert result.results[0].check_id == "tool.local_file"


def test_port_failure_does_not_leak_technical_error():
    service, store, _secrets = _service()

    def fail():
        raise CapabilitiesPortError("path and secret details")

    store.load_capabilities = fail  # type: ignore[method-assign]

    from app.features.configuration.capabilities import CapabilitiesUnavailable

    with pytest.raises(CapabilitiesUnavailable) as raised:
        service.list_capabilities(_principal(), ListCapabilitiesQuery())

    assert "path and secret details" not in str(raised.value)
