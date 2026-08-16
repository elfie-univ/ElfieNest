"""App-owned runtime boundaries for the Discord Gateway adapter."""

from __future__ import annotations

from typing import Protocol, Tuple

from app.features.communication import (
    DiscordPrivateUpdate,
    DiscordRuntimeAccount,
    StoredDiscordAccount,
)
from elfie.public import CommunicationChannel

from .discord import DiscordUpdateOutcome


class DiscordRuntimeAccountSource(Protocol):
    def runtime_accounts(self) -> Tuple[DiscordRuntimeAccount, ...]: ...

    def mark_runtime_health(
        self, elfie_id: str, *, healthy: bool, issue: str | None = None
    ) -> None: ...


class DiscordRuntimeUpdateHandler(Protocol):
    def handle(
        self,
        account: StoredDiscordAccount,
        update: DiscordPrivateUpdate,
        *,
        pairing_code: str | None = None,
    ) -> DiscordUpdateOutcome: ...


class DiscordChannelRegistry(Protocol):
    def attach_communication_channel(
        self, elfie_id: str, channel: CommunicationChannel
    ) -> bool: ...

    def detach_communication_channel(
        self, elfie_id: str, channel: CommunicationChannel
    ) -> None: ...


__all__ = (
    "DiscordChannelRegistry",
    "DiscordRuntimeAccountSource",
    "DiscordRuntimeUpdateHandler",
)
