"""Real single-Elfie lifecycle across perception, cognition, and output."""

from __future__ import annotations

import json
from datetime import datetime
from threading import Event

from pydantic import JsonValue

from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.brain.runtime_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    DeliveryReceipt,
    DeliveryStatus,
    MessageDirection,
    TextPart,
)
from elfie.message_types import ActorRef, MessageMeta


class RecordingChannel:
    channel_id = "chat"

    def __init__(self) -> None:
        self.connected = False
        self.sent: list[CommunicationEnvelope] = []

    @property
    def is_connected(self) -> bool:
        return self.connected

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        self.sent.append(envelope)
        return DeliveryReceipt.for_envelope(envelope, status=DeliveryStatus.SENT)


class TwoTurnRuntime:
    def __init__(self) -> None:
        self.first_started = Event()
        self.release_first = Event()
        self.second_started = Event()
        self.requests: list[ModelGenerationRequest] = []

    def capabilities(self) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider="fake",
            model_key="fake/schema",
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=1024,
        )

    def abandon(self, request: ModelGenerationRequest) -> None:
        del request

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        self.requests.append(request)
        if len(self.requests) == 1:
            self.first_started.set()
            self.release_first.wait()
            intents = self._first_intents(request)
        else:
            self.second_started.set()
            intents = [self._intent(request, "noop", reason="receipts observed")]
        plan = {
            "schema_version": 1,
            "plan_id": f"plan-{request.turn_id}",
            "turn_id": str(request.turn_id),
            "frame_id": str(request.frame_id),
            "context_revision": request.context_revision,
            "capability_revision": request.capability_revision,
            "created_at": request.created_at.isoformat(),
            "deadline": request.deadline.isoformat(),
            "cause_event_ids": list(request.cause_event_ids),
            "intents": intents,
        }
        return ModelGenerationResult(
            text=json.dumps(plan),
            selected_mode=StructuredOutputMode.JSON_SCHEMA,
            provider="fake",
            model_key="fake/schema",
        )

    def _first_intents(
        self,
        request: ModelGenerationRequest,
    ) -> list[dict[str, JsonValue]]:
        return [
            self._intent(request, "speech", text="hello room"),
            self._intent(request, "motion", motion="walk"),
            self._intent(request, "expression", expression="happy", intensity=0.8),
            self._intent(
                request,
                "message",
                channel_id="chat",
                conversation_id="owner-chat",
                content="reply one",
                sequence_id="reply-sequence",
                ordinal=0,
            ),
            self._intent(
                request,
                "message",
                channel_id="chat",
                conversation_id="owner-chat",
                content="reply two",
                sequence_id="reply-sequence",
                ordinal=1,
            ),
        ]

    @staticmethod
    def _intent(
        request: ModelGenerationRequest,
        intent_type: str,
        **payload: JsonValue,
    ) -> dict[str, JsonValue]:
        return {
            "type": intent_type,
            "intent_id": (
                f"{intent_type}-{payload.get('ordinal', 0)}-{request.turn_id}"
            ),
            "cause_event_ids": list(request.cause_event_ids),
            "dependency_ids": [],
            "deadline": request.deadline.isoformat(),
            "cancel_policy": "if_not_started",
            **payload,
        }


def _owner_message(at: datetime) -> CommunicationEnvelope:
    owner = ActorRef(actor_id="owner-1", source_kind="owner")
    return CommunicationEnvelope(
        meta=MessageMeta(
            event_id="owner-message-1",
            elfie_id="elfie-loop",
            source=owner,
            occurred_at=at,
            received_at=at,
            trace_id="trace-owner-message-1",
        ),
        account_id="owner-account",
        channel_id="chat",
        conversation_id="owner-chat",
        sender=owner,
        recipients=(ActorRef(actor_id="elfie-loop", source_kind="elfie"),),
        direction=MessageDirection.INBOUND,
        external_message_id="external-owner-message-1",
        dedupe_key="external-owner-message-1",
        parts=(TextPart(text="hello elfie"),),
    )


def test_cognitive_lifecycle_runs_two_turns_without_blocking_clock() -> None:
    # Given: a real HeadlessBody, CommunicationHub, and blocked first model turn.
    body = HeadlessBody(body_id="body-loop")
    body.connect()
    hub = CommunicationHub("elfie-loop")
    channel = RecordingChannel()
    hub.register_channel(channel, connect=True)
    runtime = TwoTurnRuntime()
    elfie = ElfieFactory().create(
        elfie_id="elfie-loop",
        memory_db_path=":memory:",
        body=body,
        communication=hub,
        cortical_runtime=runtime,
    )
    elfie.start()
    elfie.receive_communication_envelope(_owner_message(elfie.cognitive_datetime))
    elfie.advance_clock(0.5)
    assert runtime.first_started.wait(1)

    # When: five physical ticks continue while the first cortical call is blocked.
    for _ in range(5):
        elfie.advance_clock(1.0)

    # Then: simulation time advances independently and the first result fans out.
    assert elfie.elapsed_time == 5.5
    runtime.release_first.set()
    elfie.wait_for_outcome_count(1, timeout=1)
    first = elfie.turn_outcomes()[0]
    elfie.wait_for_output(first.turn_id, timeout=1)
    assert len(channel.sent) == 2

    # When: receipt facts age into the next frame.
    elfie.advance_clock(5.0)

    # Then: the second turn sees execution receipts from the first turn.
    assert runtime.second_started.wait(1)
    elfie.wait_for_outcome_count(2, timeout=1)
    assert "execution:receipt" in runtime.requests[1].user_prompt
    elfie.stop()
    elfie.join()
    assert elfie.is_running is False
