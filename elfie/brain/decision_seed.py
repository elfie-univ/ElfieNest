"""Host-owned envelope fields for one model decision decode."""

from typing import Tuple

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


__all__ = ("DecisionDecodeSeed",)
