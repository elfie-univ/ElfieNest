"""Pure typed conversion from Communication contracts to perception events."""

from __future__ import annotations

from dataclasses import dataclass
from functools import singledispatch
from typing import Final, FrozenSet, Mapping, Protocol, Tuple

from elfie.brain.perception_types import (
    ExecutionPayload,
    ExecutionStatus,
    IngestDisposition,
    PerceptionEvent,
    SocialPayload,
)
from elfie.communication.contracts import (
    AudioPart,
    CommunicationEnvelope,
    ContentPart,
    DeliveryReceipt,
    DeliveryStatus,
    FilePart,
    ImagePart,
    ReactionPart,
    SystemEventPart,
    TextPart,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    CorrelationId,
    EventId,
    IntentId,
    MediaRef,
    MessageMeta,
    PlanId,
)

_EXECUTION_STATUS: Final[Mapping[DeliveryStatus, ExecutionStatus]] = {
    DeliveryStatus.ACCEPTED: ExecutionStatus.ACCEPTED,
    DeliveryStatus.QUEUED: ExecutionStatus.ACCEPTED,
    DeliveryStatus.SENT: ExecutionStatus.COMPLETED,
    DeliveryStatus.DELIVERED: ExecutionStatus.COMPLETED,
    DeliveryStatus.READ: ExecutionStatus.COMPLETED,
    DeliveryStatus.FAILED: ExecutionStatus.FAILED,
    DeliveryStatus.RETRY_SCHEDULED: ExecutionStatus.STARTED,
    DeliveryStatus.CANCELLED: ExecutionStatus.INTERRUPTED,
}
_COMPLETING_DISPOSITIONS: Final[FrozenSet[IngestDisposition]] = frozenset(
    {IngestDisposition.ACCEPTED, IngestDisposition.DUPLICATE}
)


@dataclass(frozen=True, slots=True)
class PartPerception:
    """Text and media retained from one communication content part."""

    content: str
    media: Tuple[MediaRef, ...] = ()


@dataclass(frozen=True, slots=True)
class UnsupportedContentPartError(TypeError):
    """A new content variant lacks a perception conversion."""

    part_type: str

    def __str__(self) -> str:
        return f"unsupported communication content part: {self.part_type}"


class DeliveryCorrelation(Protocol):
    """Decision identity required to normalize one delivery receipt."""

    plan_id: PlanId
    intent_id: IntentId


@singledispatch
def _convert_part(part: ContentPart) -> PartPerception:
    raise UnsupportedContentPartError(part_type=type(part).__name__)


@_convert_part.register
def _convert_text(part: TextPart) -> PartPerception:
    return PartPerception(content=part.text)


@_convert_part.register
def _convert_image(part: ImagePart) -> PartPerception:
    content = part.caption or f"[image:{part.media.media_id}]"
    return PartPerception(content=content, media=(part.media,))


@_convert_part.register
def _convert_audio(part: AudioPart) -> PartPerception:
    content = part.transcript or f"[audio:{part.media.media_id}]"
    return PartPerception(content=content, media=(part.media,))


@_convert_part.register
def _convert_file(part: FilePart) -> PartPerception:
    return PartPerception(content=f"[file:{part.filename}]", media=(part.media,))


@_convert_part.register
def _convert_reaction(part: ReactionPart) -> PartPerception:
    return PartPerception(
        content=f"[reaction:{part.target_message_id}:{part.reaction}]"
    )


@_convert_part.register
def _convert_system_event(part: SystemEventPart) -> PartPerception:
    return PartPerception(
        content=part.description or f"[system_event:{part.event_name}]"
    )


def build_social_event(envelope: CommunicationEnvelope) -> PerceptionEvent:
    """Preserve one complete envelope as one social perception fact."""
    parts = tuple(_convert_part(part) for part in envelope.parts)
    return PerceptionEvent(
        meta=envelope.meta,
        payload=SocialPayload(
            type="social",
            channel_id=envelope.channel_id,
            conversation_id=envelope.conversation_id,
            sender=envelope.sender,
            content="\n".join(part.content for part in parts),
            reply_to_event_id=(
                None if envelope.reply_to is None else EventId(envelope.reply_to)
            ),
            media=tuple(media for part in parts for media in part.media),
        ),
    )


def build_execution_event(
    envelope: CommunicationEnvelope,
    receipt: DeliveryReceipt,
    correlation: DeliveryCorrelation,
) -> PerceptionEvent:
    """Normalize a platform receipt while retaining all correlation IDs."""
    external_id = envelope.external_message_id or envelope.dedupe_key
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=receipt.receipt_id,
            elfie_id=envelope.meta.elfie_id,
            source=ActorRef(
                actor_id=ActorId(str(envelope.meta.elfie_id)),
                source_kind="communication",
            ),
            occurred_at=envelope.meta.received_at,
            received_at=envelope.meta.received_at,
            trace_id=envelope.meta.trace_id,
            causation_id=envelope.message_id,
            correlation_id=CorrelationId(external_id),
            priority=envelope.meta.priority,
        ),
        payload=ExecutionPayload(
            type="execution",
            receipt_id=receipt.receipt_id,
            plan_id=correlation.plan_id,
            intent_id=correlation.intent_id,
            executor="communication",
            status=_EXECUTION_STATUS[receipt.status],
            error=receipt.error,
        ),
    )


def completes_cognitive_delivery(disposition: IngestDisposition) -> bool:
    """Only retained accepted or duplicate writes complete Hub delivery."""
    return disposition in _COMPLETING_DISPOSITIONS


__all__ = (
    "build_execution_event",
    "build_social_event",
    "completes_cognitive_delivery",
)
