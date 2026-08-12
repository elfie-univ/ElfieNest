"""Secret Adapter for web-search capability credentials."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Optional

from app.features.configuration.capabilities import CapabilitiesPortError

SecretResolver = Callable[[str, Optional[Path]], str]
ToolSecretWriter = Callable[[str, str, Optional[Path]], str]


class ToolCapabilitySecretAdapter:
    def __init__(
        self,
        secret_path: Optional[Path] = None,
        *,
        resolve: SecretResolver,
        write: ToolSecretWriter,
    ) -> None:
        self._secret_path = secret_path
        self._resolve = resolve
        self._write = write

    def has_secret(self, credential_ref: str) -> bool:
        try:
            return bool(self._resolve(credential_ref, self._secret_path))
        except OSError as error:
            raise CapabilitiesPortError("无法读取系统能力凭据") from error

    def set_web_search_secret(self, api_key: str) -> str:
        try:
            reference: object = self._write("web_search", api_key, self._secret_path)
            if not isinstance(reference, str):
                raise CapabilitiesPortError("系统能力凭据引用无效")
            return reference
        except (OSError, ValueError) as error:
            raise CapabilitiesPortError("无法保存系统能力凭据") from error


__all__ = ("ToolCapabilitySecretAdapter",)
