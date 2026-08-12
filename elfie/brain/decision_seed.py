"""Host-owned envelope fields for one model decision decode."""

from typing import Optional, Tuple

from elfie.message_types import EventId, FrozenContractModel, TurnId, UTCDateTime


class DecisionDecodeSeed(FrozenContractModel):
    """Trusted plan envelope fields that model output cannot replace."""

    turn_id: TurnId
    frame_id: EventId
    context_revision: int
    capability_revision: int
    created_at: UTCDateTime
    deadline: UTCDateTime
    cause_event_ids: Tuple[EventId, ...]
    # A trusted inbound owner conversation may receive a safe text fallback.
    # These are host-derived targets, never taken from model output.
    reply_channel_id: Optional[str] = None
    reply_conversation_id: Optional[str] = None


__all__ = ("DecisionDecodeSeed",)
