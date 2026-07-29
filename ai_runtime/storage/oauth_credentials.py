"""OAuth 凭据的本地结构化存储。"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ai_runtime.storage.data_home import ensure_elfie_home, get_oauth_credentials_dir

_CREDENTIAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_MAX_CREDENTIAL_BYTES = 1024 * 1024


@dataclass(frozen=True)
class InvalidOAuthCredentialIdError(ValueError):
    """凭据 ID 不能安全映射到文件名。"""

    credential_id: str

    def __str__(self) -> str:
        return f"OAuth 凭据 ID 不合法: {self.credential_id!r}"


class OAuthCredentialStoreError(RuntimeError):
    """OAuth 凭据文件缺失必要字段、损坏或无法安全读写。"""


@dataclass(frozen=True)
class OAuthCredential:
    """一个 Provider 的可刷新 OAuth 凭据。"""

    provider_id: str
    access_token: str = field(repr=False)
    refresh_token: str = field(default="", repr=False)
    expires_at: str | None = None
    scopes: tuple[str, ...] = ()
    account_id: str | None = None
    token_type: str = "Bearer"

    def __post_init__(self) -> None:
        _validate_credential_id(self.provider_id)
        if not self.access_token:
            raise ValueError("access_token 不能为空")
        object.__setattr__(
            self,
            "scopes",
            tuple(scope for scope in self.scopes if isinstance(scope, str) and scope),
        )

    def public_view(self) -> dict[str, Any]:
        """返回不含令牌明文的状态投影。"""
        return {
            "provider_id": self.provider_id,
            "expires_at": self.expires_at,
            "scopes": list(self.scopes),
            "account_id": self.account_id,
            "token_type": self.token_type,
            "has_access_token": bool(self.access_token),
            "has_refresh_token": bool(self.refresh_token),
        }

    def _storage_payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "provider_id": self.provider_id,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scopes": list(self.scopes),
            "account_id": self.account_id,
            "token_type": self.token_type,
        }

    @classmethod
    def _from_storage_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        expected_provider_id: str,
    ) -> OAuthCredential:
        provider_id = str(payload.get("provider_id") or "")
        access_token = str(payload.get("access_token") or "")
        if provider_id != expected_provider_id:
            raise ValueError("provider_id 与凭据文件名不一致")
        if not access_token:
            raise ValueError("access_token 不能为空")
        raw_scopes = payload.get("scopes", [])
        if not isinstance(raw_scopes, list):
            raise ValueError("scopes 必须是数组")
        return cls(
            provider_id=provider_id,
            access_token=access_token,
            refresh_token=str(payload.get("refresh_token") or ""),
            expires_at=(
                str(payload["expires_at"]) if payload.get("expires_at") else None
            ),
            scopes=tuple(str(scope) for scope in raw_scopes),
            account_id=(
                str(payload["account_id"]) if payload.get("account_id") else None
            ),
            token_type=str(payload.get("token_type") or "Bearer"),
        )


class OAuthCredentialStore:
    """按 Provider ID 原子保存 OAuth 凭据。"""

    def __init__(self, directory: Path | None = None) -> None:
        self._uses_default_directory = directory is None
        self.directory = directory or get_oauth_credentials_dir()

    def load(self, provider_id: str) -> OAuthCredential | None:
        path = self._path(provider_id)
        if not path.exists():
            return None
        try:
            if path.stat().st_size > _MAX_CREDENTIAL_BYTES:
                raise ValueError("凭据文件过大")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("凭据内容必须是对象")
            return OAuthCredential._from_storage_payload(
                payload,
                expected_provider_id=provider_id,
            )
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise OAuthCredentialStoreError(
                f"OAuth 凭据无法读取 ({provider_id}): {exc}"
            ) from exc

    def save(self, credential: OAuthCredential) -> Path:
        path = self._path(credential.provider_id)
        if self._uses_default_directory:
            ensure_elfie_home()
        self.directory.mkdir(parents=True, exist_ok=True)
        _secure_mode(self.directory, 0o700)
        content = json.dumps(
            credential._storage_payload(),
            ensure_ascii=False,
            indent=2,
        )
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(self.directory),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(content)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            _secure_mode(Path(temporary), 0o600)
            os.replace(temporary, path)
            _secure_mode(path, 0o600)
        except OSError as exc:
            raise OAuthCredentialStoreError(
                f"OAuth 凭据无法保存 ({credential.provider_id})"
            ) from exc
        finally:
            try:
                Path(temporary).unlink()
            except FileNotFoundError:
                pass
        return path

    def delete(self, provider_id: str) -> bool:
        path = self._path(provider_id)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise OAuthCredentialStoreError(
                f"OAuth 凭据无法删除 ({provider_id})"
            ) from exc
        return True

    def _path(self, provider_id: str) -> Path:
        _validate_credential_id(provider_id)
        return self.directory / f"{provider_id}.json"


def _validate_credential_id(credential_id: str) -> None:
    if _CREDENTIAL_ID_PATTERN.fullmatch(credential_id) is None:
        raise InvalidOAuthCredentialIdError(credential_id)


def _secure_mode(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(mode)
    except (OSError, NotImplementedError):
        pass
