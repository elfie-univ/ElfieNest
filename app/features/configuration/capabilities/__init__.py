"""Public facade for global capability configuration."""

from .errors import (
    CapabilitiesError,
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
    CapabilityKey,
    LocalFileUpdateField,
    SearchProvider,
    StoredCapabilities,
    StoredLocalFileCapability,
    StoredValidationResult,
    StoredWebSearchCapability,
    ValidationStatus,
    WebSearchUpdateField,
)
from .ports import (
    CapabilitiesPortError,
    CapabilitiesStorePort,
    CapabilitySecretPort,
    CapabilityValidationPort,
)
from .service import CapabilitiesService

__all__ = (
    "CapabilitiesError",
    "CapabilitiesForbidden",
    "CapabilitiesPortError",
    "CapabilitiesResult",
    "CapabilitiesService",
    "CapabilitiesStorePort",
    "CapabilitiesUnavailable",
    "CapabilitiesValidationError",
    "CapabilityKey",
    "CapabilitySecretPort",
    "CapabilityValidationPort",
    "CapabilityValidationResult",
    "CapabilityValidationSuiteResult",
    "CapabilityValidationSummary",
    "ListCapabilitiesQuery",
    "LocalFileCapabilityResult",
    "LocalFileUpdateField",
    "SearchProvider",
    "StoredCapabilities",
    "StoredLocalFileCapability",
    "StoredValidationResult",
    "StoredWebSearchCapability",
    "UpdateLocalFileCapabilityCommand",
    "UpdateWebSearchCapabilityCommand",
    "ValidationStatus",
    "VerifyCapabilityCommand",
    "WebSearchCapabilityResult",
    "WebSearchUpdateField",
)
