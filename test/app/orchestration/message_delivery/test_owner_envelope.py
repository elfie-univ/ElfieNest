from __future__ import annotations

from unittest.mock import MagicMock

from app.orchestration.message_delivery import deliver_owner_message
from elfie import Elfie
from elfie.communication import InboundDisposition, InboundDispositionStatus
from elfie.message_types import EventId


def test_owner_envelope_preserves_external_identity_and_conversation() -> None:
    disposition = InboundDisposition(
        message_id=EventId("owner:external-1"),
        channel_id="godot-owner",
        status=InboundDispositionStatus.ACCEPTED,
    )
    elfie = MagicMock(spec=Elfie)
    elfie.receive_communication_envelope.return_value = disposition

    result = deliver_owner_message(
        elfie=elfie,
        elfie_id="00000001",
        message="  你好  ",
        elapsed_seconds=10.0,
        owner_id="7",
        conversation_id="owner:7",
        external_message_id="external-1",
        account_id="owner",
        channel_id="godot-owner",
    )

    assert result is disposition
    envelope = elfie.receive_communication_envelope.call_args.args[0]
    assert envelope.conversation_id == "owner:7"
    assert envelope.external_message_id == "external-1"
    assert envelope.parts[0].text == "你好"
