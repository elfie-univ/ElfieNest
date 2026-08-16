"""Narrow local-secret adapter for per-Elfie Discord Bot Tokens."""

from __future__ import annotations

import re
from pathlib import Path

from infrastructure.persistence.configuration.secrets import (
    read_secrets,
    resolve_secret,
    write_secrets,
)

_ELFIE_ID = re.compile(r"^[0-9]{8}$")
_REFERENCE = re.compile(r"^ELFIE_DISCORD_[0-9]{8}_BOT_TOKEN$")


class DiscordTokenAdapter:
    """Keep Discord credentials only in the protected ``auth.env`` store."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    def credential_ref(self, elfie_id: str) -> str:
        if _ELFIE_ID.fullmatch(elfie_id) is None:
            raise ValueError("invalid Elfie ID for Discord credential")
        return f"ELFIE_DISCORD_{elfie_id}_BOT_TOKEN"

    def load(self, credential_ref: str) -> str:
        if _REFERENCE.fullmatch(credential_ref) is None:
            return ""
        return resolve_secret(credential_ref, self._path)

    def replace(self, elfie_id: str, token: str) -> str:
        reference = self.credential_ref(elfie_id)
        if not token or any(character in token for character in "\r\n"):
            raise ValueError("invalid Discord bot token")
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


__all__ = ("DiscordTokenAdapter",)
