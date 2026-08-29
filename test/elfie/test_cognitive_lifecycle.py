"""Real single-Elfie lifecycle across perception, cognition, and output."""

from __future__ import annotations

import json
from datetime import datetime
from threading import Event
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue

from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.brain.journal import BrainJournalKind
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.brain.runtime import BrainRuntime
from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    DeliveryReceipt,
    DeliveryStatus,
    InboundDispositionStatus,
    MessageDirection,
    TextPart,
)
from elfie.factory import ElfieAssembly
from elfie.message_types import ActorRef, MessageMeta, TurnId
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


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
            "emotion_feedback": {
                "effects": [
                    {
                        "channel": channel,
                        "direction": (
                            "increase"
                            if channel == "happiness"
                            and request.response_mode.value == "direct_reply"
                            else "unchanged"
                        ),
                        "strength": (
                            80
                            if channel == "happiness"
                            and request.response_mode.value == "direct_reply"
                            else 0
                        ),
                        "confidence": 1.0,
                    }
                    for channel in (
                        "happiness",
                        "sadness",
                        "anger",
                        "fear",
                        "surprise",
                        "disgust",
                    )
                ]
            },
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


def _owner_message(
    at: datetime,
    *,
    event_id: str = "owner-message-1",
    conversation_id: str = "owner-chat",
    text: str = "hello elfie",
    elfie_id: str = "elfie-loop",
) -> CommunicationEnvelope:
    owner = ActorRef(actor_id="owner-1", source_kind="owner")
    return CommunicationEnvelope(
        meta=MessageMeta(
            event_id=event_id,
            elfie_id=elfie_id,
            source=owner,
            occurred_at=at,
            received_at=at,
            trace_id=f"trace-{event_id}",
        ),
        account_id="owner-account",
        channel_id="chat",
        conversation_id=conversation_id,
        sender=owner,
        recipients=(ActorRef(actor_id=elfie_id, source_kind="elfie"),),
        direction=MessageDirection.INBOUND,
        external_message_id=f"external-{event_id}",
        dedupe_key=f"external-{event_id}",
        parts=(TextPart(text=text),),
    )


def test_cognitive_lifecycle_runs_two_turns_without_blocking_clock() -> None:
    # Given: a real HeadlessBody, CommunicationHub, and blocked first model turn.
    body = HeadlessBody(body_id="body-loop")
    body.connect()
    hub = CommunicationHub("elfie-loop")
    channel = RecordingChannel()
    hub.register_channel(channel, connect=True)
    runtime = TwoTurnRuntime()
    elfie = _new_elfie(
        "elfie-loop",
        body=body,
        communication=hub,
        model_port=runtime,
    )
    elfie.start()
    elfie.receive_communication_envelope(_owner_message(elfie.cognitive_datetime))
    elfie.advance_clock(0.5)
    assert runtime.first_started.wait(1)

    # When: five physical ticks continue while the first cortical call is blocked.
    for _ in range(5):
        elfie.advance_clock(1.0)

    # Then: simulation time advances independently and replies stay in Communication.
    assert elfie.elapsed_time == 5.5
    runtime.release_first.set()
    elfie.wait_for_outcome_count(1, timeout=1)
    first = elfie.turn_outcomes()[0]
    elfie.wait_for_output(first.turn_id, timeout=1)
    decision = elfie.turn_decision(first.turn_id)
    assert decision is not None
    assert decision.plan.turn_id == first.turn_id
    assert len(decision.plan.intents) == 2
    assert elfie.turn_decision(TurnId("turn-unknown")) is None
    assert len(channel.sent) == 2
    assert body.snapshot_body(now=elfie.cognitive_datetime).last_status is None

    # When: receipt facts age into the next frame.
    elfie.advance_clock(5.0)

    # Then: the second turn sees execution receipts from the first turn.
    assert runtime.second_started.wait(1)
    elfie.wait_for_outcome_count(2, timeout=1)
    assert "execution:receipt" in runtime.requests[1].user_prompt
    second = elfie.turn_outcomes()[1]
    elfie.wait_for_output(second.turn_id, timeout=1)

    # When: the second turn deliberately completes with NoOp and time advances.
    elfie.advance_clock(5.0)

    # Then: recording that NoOp does not feed another receipt-only turn back
    # into cognition forever.
    with pytest.raises(TimeoutError):
        elfie.wait_for_outcome_count(3, timeout=0.2)
    assert len(runtime.requests) == 2
    journal_kinds = {entry.kind for entry in elfie.brain_journal()}
    assert BrainJournalKind.RUN_STARTED in journal_kinds
    assert BrainJournalKind.RUN_TERMINATED in journal_kinds
    assert BrainJournalKind.DIRECTIVE_ACCEPTED in journal_kinds
    assert BrainJournalKind.EXECUTION_RECEIPT in journal_kinds
    elfie.stop()
    elfie.join()


def test_stop_closes_communication_input_boundary() -> None:
    # Given: a running Elfie with a registered communication channel.
    body = HeadlessBody(body_id="body-stop")
    hub = CommunicationHub("elfie-loop")
    hub.register_channel(RecordingChannel(), connect=True)
    elfie = _new_elfie(
        "elfie-loop",
        body=body,
        communication=hub,
        model_port=TwoTurnRuntime(),
    )
    elfie.start()
    elfie.stop()
    elfie.join()

    # When: an owner message arrives after shutdown.
    disposition = elfie.receive_communication_envelope(
        _owner_message(elfie.cognitive_datetime)
    )

    # Then: it is rejected without being retained for a later turn.
    assert disposition.status is InboundDispositionStatus.REJECTED
    assert disposition.error is not None
    assert disposition.error.code == "communication_closed"
    assert hub.inbox.metrics().pending_count == 0
    assert elfie.is_running is False


def test_two_conversations_form_separate_turns_without_temporary_context_leak() -> None:
    hub = CommunicationHub("elfie-two-chats")
    hub.register_channel(RecordingChannel(), connect=True)
    runtime = TwoTurnRuntime()
    elfie = _new_elfie(
        "elfie-two-chats",
        body=HeadlessBody(body_id="body-two-chats"),
        communication=hub,
        model_port=runtime,
    )
    elfie.start()
    now = elfie.cognitive_datetime
    elfie.receive_communication_envelope(
        _owner_message(
            now,
            event_id="message-a",
            conversation_id="conversation-a",
            text="secret-from-a",
            elfie_id="elfie-two-chats",
        )
    )
    elfie.receive_communication_envelope(
        _owner_message(
            now,
            event_id="message-b",
            conversation_id="conversation-b",
            text="only-for-b",
            elfie_id="elfie-two-chats",
        )
    )
    elfie.advance_clock(2.1)
    assert runtime.first_started.wait(1)
    runtime.release_first.set()
    elfie.wait_for_outcome_count(1, timeout=1)
    elfie.advance_clock(0.1)
    assert runtime.second_started.wait(1)
    elfie.wait_for_outcome_count(2, timeout=1)

    assert runtime.requests[0].interaction_scope.conversation_id == "conversation-a"
    assert runtime.requests[1].interaction_scope.conversation_id == "conversation-b"
    second_context = runtime.requests[1].user_prompt
    assert "only-for-b" in second_context
    assert "secret-from-a" not in second_context
    elfie.stop()
    elfie.join()


def _new_elfie(elfie_id: str, **dependencies):
    return ElfieFactory().create(
        ElfieAssembly(
            profile=create_visual_profile(
                elfie_id=elfie_id,
                display_name=elfie_id,
                species_id="fox",
                seed=1,
            ),
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            **dependencies,
        )
    )


def test_cognitive_start_rolls_back_router_when_coordinator_start_fails() -> None:
    runtime = object.__new__(BrainRuntime)
    runtime._started = False
    runtime._journal_store = MagicMock()
    runtime._journal_store.load_checkpoint.return_value = None
    runtime._reconcile_interrupted_work = MagicMock(return_value=False)
    runtime.router = MagicMock()
    runtime.coordinator = MagicMock()
    runtime.coordinator.start.side_effect = RuntimeError("coordinator failed")

    with pytest.raises(RuntimeError, match="coordinator failed"):
        runtime.start()

    runtime.router.stop.assert_called_once_with()
    runtime.router.join.assert_called_once_with()
    runtime.coordinator.stop.assert_called_once_with()
    runtime.coordinator.join.assert_called_once_with()
    assert runtime._started is False
