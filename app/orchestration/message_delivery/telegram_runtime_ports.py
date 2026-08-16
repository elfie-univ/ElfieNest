"""App-owned runtime boundaries for the Telegram long-polling adapter."""

from __future__ import annotations

from typing import Protocol, Tuple

from app.features.communication import (
    StoredTelegramAccount,
    TelegramPrivateUpdate,
    TelegramRuntimeAccount,
)
from elfie.public import CommunicationChannel

from .telegram import TelegramUpdateOutcome


class TelegramRuntimeAccountSource(Protocol):
    def runtime_accounts(self) -> Tuple[TelegramRuntimeAccount, ...]: ...

    def mark_runtime_health(
        self, elfie_id: str, *, healthy: bool, issue: str | None = None
    ) -> None: ...

    def save_next_update_id(self, elfie_id: str, next_update_id: int) -> None: ...


class TelegramRuntimeUpdateHandler(Protocol):
    def handle(
        self,
        account: StoredTelegramAccount,
        update: TelegramPrivateUpdate,
        *,
        pairing_code: str | None = None,
    ) -> TelegramUpdateOutcome: ...


class ElfieCommunicationChannelRegistry(Protocol):
    def attach_communication_channel(
        self, elfie_id: str, channel: CommunicationChannel
    ) -> bool: ...

    def detach_communication_channel(
        self, elfie_id: str, channel: CommunicationChannel
    ) -> None: ...


__all__ = (
    "ElfieCommunicationChannelRegistry",
    "TelegramRuntimeAccountSource",
    "TelegramRuntimeUpdateHandler",
)
