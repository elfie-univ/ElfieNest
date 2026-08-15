"""Secret-safe normalization for Provider technology failures."""

from __future__ import annotations

import re
import urllib.error
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

_URL_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+@", re.IGNORECASE)

ErrorScope = Literal["request", "endpoint", "transport", "connection"]


@dataclass(frozen=True)
class ProviderErrorClassification:
    code: str
    scope: ErrorScope
    category: str


class ProviderCallError(RuntimeError, ValueError):
    """Typed transport failure that keeps health scope narrow."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        scope: ErrorScope,
        category: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.scope = scope
        self.category = category


def provider_error_from_http(
    error: urllib.error.HTTPError,
    message: str,
) -> ProviderCallError:
    code = int(error.code)
    if code == 401:
        classification = ProviderErrorClassification(
            "invalid_credential", "connection", "authentication"
        )
    elif code == 403:
        # A bare 403 does not prove an account-wide billing or credential
        # blocker.  Product adapters may promote a typed response, but the
        # generic transport classification stays endpoint-scoped.
        classification = ProviderErrorClassification(
            "access_denied", "endpoint", "authorization"
        )
    elif code == 402:
        classification = ProviderErrorClassification(
            "billing_blocked", "connection", "billing"
        )
    elif code == 404:
        classification = ProviderErrorClassification(
            "model_not_found", "endpoint", "not_found"
        )
    elif code in {400, 422}:
        classification = ProviderErrorClassification(
            "invalid_request", "request", "request"
        )
    elif code == 429:
        classification = ProviderErrorClassification(
            "rate_limited", "endpoint", "rate_limit"
        )
    elif 500 <= code <= 599:
        classification = ProviderErrorClassification(
            "server_error", "transport", "server"
        )
    else:
        classification = ProviderErrorClassification(
            "provider_error", "endpoint", "provider"
        )
    return ProviderCallError(
        message,
        code=classification.code,
        scope=classification.scope,
        category=classification.category,
    )


def provider_network_error(message: str) -> ProviderCallError:
    return ProviderCallError(
        message,
        code="network_error",
        scope="transport",
        category="network",
    )


def classify_provider_error(error: BaseException) -> ProviderErrorClassification:
    """Classify an exception chain without persisting its message."""
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, ProviderCallError):
            return ProviderErrorClassification(
                current.code,
                current.scope,
                current.category,
            )
        if isinstance(current, urllib.error.HTTPError):
            return _http_classification(int(current.code))
        current = current.__cause__ or current.__context__
    if isinstance(error, TimeoutError):
        return ProviderErrorClassification("timeout", "transport", "timeout")
    if error.__class__.__name__ == "OllamaNotReadyError":
        return ProviderErrorClassification(
            "ollama_unavailable", "transport", "network"
        )
    if isinstance(error, ValueError):
        return ProviderErrorClassification("invalid_request", "request", "request")
    return ProviderErrorClassification("provider_error", "endpoint", "provider")


def _http_classification(code: int) -> ProviderErrorClassification:
    if code == 401:
        return ProviderErrorClassification(
            "invalid_credential", "connection", "authentication"
        )
    if code == 403:
        return ProviderErrorClassification("access_denied", "endpoint", "authorization")
    if code == 402:
        return ProviderErrorClassification("billing_blocked", "connection", "billing")
    if code == 404:
        return ProviderErrorClassification("model_not_found", "endpoint", "not_found")
    if code in {400, 422}:
        return ProviderErrorClassification("invalid_request", "request", "request")
    if code == 429:
        return ProviderErrorClassification("rate_limited", "endpoint", "rate_limit")
    if 500 <= code <= 599:
        return ProviderErrorClassification("server_error", "transport", "server")
    return ProviderErrorClassification("provider_error", "endpoint", "provider")


def sanitize_error(error: str | None, *, secrets: Iterable[str]) -> str | None:
    if not error:
        return None
    result = _URL_CREDENTIALS.sub(r"\1[redacted]@", str(error))
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[redacted]")
    return " ".join(result.split())[:240]


__all__ = (
    "ErrorScope",
    "ProviderCallError",
    "ProviderErrorClassification",
    "classify_provider_error",
    "provider_error_from_http",
    "provider_network_error",
    "sanitize_error",
)
