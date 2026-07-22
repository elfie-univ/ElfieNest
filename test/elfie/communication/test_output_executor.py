"""Integration tests for MessageIntent crossing CommunicationHub."""

from elfie.brain.output_types import IntentExecutionResult
from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    DeliveryReceipt,
    DeliveryStatus,
)
from elfie.communication.output_executor import CommunicationIntentExecutor
from test.elfie.brain.test_output_router import (
    ELFIE_ID,
    NOW,
    StaticCapabilities,
    _capabilities,
    _message,
    _plan,
)


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


def test_message_executor_preserves_sequence_and_decision_identity() -> None:
    # Given: a connected channel and one explicitly sequenced message intent.
    hub = CommunicationHub(str(ELFIE_ID))
    channel = RecordingChannel()
    hub.register_channel(channel, connect=True)
    executor = CommunicationIntentExecutor(
        hub=hub,
        elfie_id=ELFIE_ID,
        capabilities=StaticCapabilities(_capabilities()),
        clock=lambda: NOW,
    )
    intent = _message(2)
    plan = _plan((intent,))

    # When: Communication executes the platform-neutral intent.
    result = executor.execute(plan, intent)

    # Then: one outbound envelope keeps sequence, conversation, and causal identity.
    assert result == IntentExecutionResult.completed()
    assert len(channel.sent) == 1
    envelope = channel.sent[0]
    assert envelope.sequence_id == "reply-sequence"
    assert envelope.ordinal == 2
    assert envelope.conversation_id == "conversation-1"
    assert envelope.meta.causation_id == "cause-1"
    assert envelope.dedupe_key == "plan-router:message-2"
