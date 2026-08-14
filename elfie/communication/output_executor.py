"""Translate MessageIntent into a complete outbound communication envelope."""

from __future__ import annotations

from typing import Callable
from uuid import uuid4

from elfie.brain.reasoning.decision_types import (
    DecisionIntent,
    DecisionPlan,
    MessageIntent,
)
from elfie.brain.reasoning.execution_ports import EffectiveCapabilitiesSource
from elfie.brain.reasoning.execution_types import IntentExecutionResult
from elfie.communication.contracts import (
    CommunicationEnvelope,
    DeliveryStatus,
    MessageDirection,
    TextPart,
)
from elfie.communication.hub import CommunicationHub
from elfie.message_types import (
    ActorId,
    ActorRef,
    CorrelationId,
    ElfieId,
    ErrorInfo,
    EventId,
    IntentId,
    MessageMeta,
    TraceId,
    TurnId,
    UTCDateTime,
)


class CommunicationIntentExecutor:
    """Send one text intent through Communication without Body involvement."""

    def __init__(
        self,
        *,
        hub: CommunicationHub,
        elfie_id: ElfieId,
        capabilities: EffectiveCapabilitiesSource,
        clock: Callable[[], UTCDateTime],
    ) -> None:
        self._hub = hub
        self._elfie_id = elfie_id
        self._capabilities = capabilities
        self._clock = clock

    def execute(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> IntentExecutionResult:
        if not isinstance(intent, MessageIntent):
            return IntentExecutionResult.failed(
                ErrorInfo(code="wrong_executor", message="intent is not a message")
            )
        channel = next(
            (
                item
                for item in self._capabilities.current().connected_channels
                if item.channel_id == intent.channel_id
            ),
            None,
        )
        if channel is None:
            return IntentExecutionResult.failed(
                ErrorInfo(code="channel_unavailable", message="channel is unavailable")
            )
        envelope = self._envelope(plan, intent, channel.account_id)
        receipt = self._hub.send_envelope(envelope)
        if receipt.status in {
            DeliveryStatus.SENT,
            DeliveryStatus.DELIVERED,
            DeliveryStatus.READ,
        }:
            return IntentExecutionResult.completed()
        if receipt.status is DeliveryStatus.CANCELLED:
            return IntentExecutionResult.interrupted(
                receipt.error.message if receipt.error is not None else "cancelled"
            )
        return IntentExecutionResult.failed(
            receipt.error
            or ErrorInfo(code="delivery_incomplete", message=receipt.status.value)
        )

    def interrupt(self, turn_id: TurnId, intent_id: IntentId, reason: str) -> None:
        """Already-sent platform messages are not falsely reported as retracted."""
        del turn_id, intent_id, reason

    def _envelope(
        self,
        plan: DecisionPlan,
        intent: MessageIntent,
        account_id: str,
    ) -> CommunicationEnvelope:
        now = self._clock()
        sender = ActorRef(
            actor_id=ActorId(str(self._elfie_id)),
            source_kind="elfie",
        )
        return CommunicationEnvelope(
            meta=MessageMeta(
                event_id=EventId(f"outbound_{uuid4().hex}"),
                elfie_id=self._elfie_id,
                source=sender,
                occurred_at=now,
                received_at=now,
                trace_id=TraceId(f"output:{plan.turn_id}"),
                causation_id=intent.cause_event_ids[0],
                correlation_id=CorrelationId(str(plan.plan_id)),
            ),
            account_id=account_id,
            channel_id=intent.channel_id,
            conversation_id=intent.conversation_id,
            sender=sender,
            recipients=(
                ActorRef(
                    actor_id=ActorId(intent.conversation_id),
                    source_kind="conversation",
                ),
            ),
            direction=MessageDirection.OUTBOUND,
            reply_to=(
                str(intent.reply_to_event_id)
                if intent.reply_to_event_id is not None
                else None
            ),
            dedupe_key=f"{plan.plan_id}:{intent.intent_id}",
            sequence_id=intent.sequence_id,
            ordinal=intent.ordinal,
            parts=(TextPart(text=intent.content),),
        )


__all__ = ("CommunicationIntentExecutor",)
