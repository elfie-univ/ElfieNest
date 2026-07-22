"""Identity rebinding keeps every perception producer on one Elfie ID."""

from datetime import datetime, timezone

from elfie import Elfie
from elfie.body import BodyId, BodySensorEvent, UtteranceFinal
from elfie.brain.perception_types import TriggerReason
from elfie.message_types import ActorId, ActorRef, ElfieId, EventId, TurnId


def test_identity_rebind_reassembles_workspace_and_nervous_perception() -> None:
    # Given: an Elfie assembled under a provisional identity.
    elfie = Elfie(elfie_id="provisional", memory_db_path=":memory:")
    old_workspace = elfie.perceptual_workspace
    elfie.bind_identity("resident-1")
    now = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)
    event = BodySensorEvent(
        event_id=EventId("identity-utterance"),
        body_id=BodyId("identity-body"),
        source=ActorRef(actor_id=ActorId("speaker"), source_kind="room"),
        occurred_at=now,
        received_at=now,
        payload=UtteranceFinal(kind="utterance_final", text="hello"),
    )

    # When: the NervousSystem publishes after the identity becomes final.
    elfie.nervous_system.receive_body_event(event)
    frame_id = elfie.perceptual_workspace.seal(
        reason=TriggerReason.MANUAL,
        captured_at=now,
    )
    assert frame_id is not None
    frame = elfie.perceptual_workspace.claim(
        frame_id,
        TurnId("identity-turn"),
    )

    # Then: neither Workspace nor normalized event retains the provisional ID.
    assert elfie.perceptual_workspace is not old_workspace
    assert frame.elfie_id == ElfieId("resident-1")
    assert frame.events[0].meta.elfie_id == ElfieId("resident-1")
