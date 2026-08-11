"""Secret Adapter for web-search capability credentials."""

from __future__ import annotations

from pathlib import Path

from app.features.configuration.capabilities import CapabilitiesPortError
from infrastructure.persistence.secrets import resolve_secret, set_tool_secret


class ToolCapabilitySecretAdapter:
    def __init__(self, secret_path: Path | None = None) -> None:
        self._secret_path = secret_path

    def has_secret(self, credential_ref: str) -> bool:
        try:
            return bool(resolve_secret(credential_ref, self._secret_path))
        except OSError as error:
            raise CapabilitiesPortError("无法读取系统能力凭据") from error

    def set_web_search_secret(self, api_key: str) -> str:
        try:
            reference: object = set_tool_secret(
                "web_search", api_key, self._secret_path
            )
            if not isinstance(reference, str):
                raise CapabilitiesPortError("系统能力凭据引用无效")
            return reference
        except (OSError, ValueError) as error:
            raise CapabilitiesPortError("无法保存系统能力凭据") from error


__all__ = ("ToolCapabilitySecretAdapter",)
