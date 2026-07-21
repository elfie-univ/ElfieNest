"""Typed compatibility snapshot construction for CommunicationHub."""

from __future__ import annotations

from typing import List, TypedDict

from elfie.communication.inbox import CommunicationInbox
from elfie.communication.outbox import CommunicationOutbox
from elfie.communication.router import CommunicationRouter


class ChannelSnapshot(TypedDict):
    """Stable snapshot shape for one registered channel."""

    channel_id: str
    connected: bool


class HubSnapshot(TypedDict):
    """Stable compatibility snapshot shape for product callers."""

    elfie_id: str
    channels: List[ChannelSnapshot]
    pending_inbox: int
    outbox_count: int


def build_hub_snapshot(
    elfie_id: str,
    router: CommunicationRouter,
    inbox: CommunicationInbox,
    outbox: CommunicationOutbox,
) -> HubSnapshot:
    """Build a stable snapshot without adding presentation logic to Hub."""
    return {
        "elfie_id": elfie_id,
        "channels": [
            {"channel_id": channel.channel_id, "connected": channel.is_connected}
            for channel in router.list_channels()
        ],
        "pending_inbox": inbox.pending_count,
        "outbox_count": len(outbox.history),
    }


__all__ = ("ChannelSnapshot", "HubSnapshot", "build_hub_snapshot")
