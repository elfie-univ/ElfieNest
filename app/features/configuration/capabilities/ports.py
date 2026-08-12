"""Outbound Ports consumed by capability administration."""

from __future__ import annotations

from typing import FrozenSet, Protocol

from .port_models import (
    CapabilityKey,
    LocalFileUpdateField,
    StoredCapabilities,
    StoredLocalFileCapability,
    StoredValidationResult,
    StoredWebSearchCapability,
    WebSearchUpdateField,
)


class CapabilitiesPortError(RuntimeError):
    """A capability technical boundary could not complete an operation."""


class CapabilitiesStorePort(Protocol):
    def load_capabilities(self) -> StoredCapabilities: ...

    def save_web_search(
        self,
        capability: StoredWebSearchCapability,
        fields: FrozenSet[WebSearchUpdateField],
    ) -> StoredCapabilities: ...

    def save_local_file(
        self,
        capability: StoredLocalFileCapability,
        fields: FrozenSet[LocalFileUpdateField],
    ) -> StoredCapabilities: ...


class CapabilitySecretPort(Protocol):
    def has_secret(self, credential_ref: str) -> bool: ...

    def set_web_search_secret(self, api_key: str) -> str: ...


class CapabilityValidationPort(Protocol):
    def verify(self, capability_key: CapabilityKey) -> StoredValidationResult: ...


__all__ = (
    "CapabilitiesPortError",
    "CapabilitiesStorePort",
    "CapabilitySecretPort",
    "CapabilityValidationPort",
)
