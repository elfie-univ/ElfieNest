"""Narrow local-secret adapter for per-Elfie Telegram bot tokens."""

from __future__ import annotations

import re
from pathlib import Path

from infrastructure.persistence.configuration.secrets import (
    read_secrets,
    resolve_secret,
    write_secrets,
)

_ELFIE_ID = re.compile(r"^[0-9]{8}$")
_REFERENCE = re.compile(r"^ELFIE_TELEGRAM_[0-9]{8}_BOT_TOKEN$")


class TelegramTokenAdapter:
    """Keep Telegram credentials only in the protected ``auth.env`` store."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    def credential_ref(self, elfie_id: str) -> str:
        if _ELFIE_ID.fullmatch(elfie_id) is None:
            raise ValueError("invalid Elfie ID for Telegram credential")
        return f"ELFIE_TELEGRAM_{elfie_id}_BOT_TOKEN"

    def load(self, credential_ref: str) -> str:
        if _REFERENCE.fullmatch(credential_ref) is None:
            return ""
        return resolve_secret(credential_ref, self._path)

    def replace(self, elfie_id: str, token: str) -> str:
        reference = self.credential_ref(elfie_id)
        if not token or "\n" in token or "\r" in token:
            raise ValueError("invalid Telegram bot token")
        values = read_secrets(self._path)
        values[reference] = token
        write_secrets(values, self._path)
        return reference

    def delete(self, elfie_id: str) -> None:
        reference = self.credential_ref(elfie_id)
        values = read_secrets(self._path)
        if reference not in values:
            return
        values.pop(reference, None)
        write_secrets(values, self._path)


__all__ = ("TelegramTokenAdapter",)
