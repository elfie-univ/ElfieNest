"""Build and deliver the existing typed owner message envelope to one Elfie."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from elfie.public import (
    ActorId,
    ActorRef,
    CommunicationEnvelope,
    Elfie,
    ElfieId,
    EventId,
    InboundDisposition,
    MessageDirection,
    MessageMeta,
    TextPart,
    TraceId,
)

logger = logging.getLogger("app.orchestration.message_delivery")


def deliver_owner_message(
    *,
    elfie: Elfie | None,
    elfie_id: str,
    message: str,
    elapsed_seconds: float,
    owner_id: str,
    conversation_id: str | None,
    external_message_id: str | None,
    account_id: str,
    channel_id: str,
) -> InboundDisposition | None:
    """Preserve the canonical envelope identity and admission semantics."""
    text = message.strip()
    if elfie is None or not text:
        return None
    now = datetime.fromtimestamp(elapsed_seconds, timezone.utc)
    external_id = external_message_id or f"owner-message-{uuid4().hex}"
    try:
        owner = ActorRef(actor_id=ActorId(owner_id), source_kind="owner")
        envelope = CommunicationEnvelope(
            meta=MessageMeta(
                event_id=EventId(f"owner:{external_id}"),
                elfie_id=ElfieId(elfie_id),
                source=owner,
                occurred_at=now,
                received_at=now,
                trace_id=TraceId(f"owner-message:{external_id}"),
            ),
            account_id=account_id,
            channel_id=channel_id,
            conversation_id=conversation_id or f"owner:{owner_id}",
            sender=owner,
            recipients=(ActorRef(actor_id=ActorId(elfie_id), source_kind="elfie"),),
            direction=MessageDirection.INBOUND,
            external_message_id=external_id,
            dedupe_key=external_id,
            parts=(TextPart(text=text),),
        )
    except ValidationError as error:
        logger.warning("owner 消息 envelope 校验失败: %s", error)
        return None
    return elfie.receive_communication_envelope(envelope)


__all__ = ("deliver_owner_message",)
