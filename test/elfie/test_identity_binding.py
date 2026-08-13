"""Identity rebinding keeps every perception producer on one Elfie ID."""

from datetime import datetime, timezone

from elfie import Elfie
from elfie.body import BodyId, BodySensorEvent, HeadlessBody, UtteranceFinal
from elfie.brain.workspace.contracts import TriggerReason
from elfie.diagnostics import ElfieDiagnostics
from elfie.message_types import ActorId, ActorRef, ElfieId, EventId, TurnId
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def test_identity_rebind_reassembles_workspace_and_nervous_perception() -> None:
    # Given: an Elfie assembled under a provisional identity.
    body = HeadlessBody(body_id="identity-body")
    elfie = Elfie(
        character_profile=create_visual_profile(
            elfie_id="provisional", display_name="临时精灵", species_id="fox", seed=4
        ),
        memory_store=SQLiteMemoryStoreAdapter.in_memory(),
        body=body,
    )
    old_workspace = ElfieDiagnostics(elfie).workspace
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
    ElfieDiagnostics(elfie).nervous_system.receive_body_event(event)
    frame_id = ElfieDiagnostics(elfie).workspace.seal(
        reason=TriggerReason.MANUAL,
        captured_at=now,
    )
    assert frame_id is not None
    frame = ElfieDiagnostics(elfie).workspace.claim(
        frame_id,
        TurnId("identity-turn"),
    )

    # Then: neither Workspace nor normalized event retains the provisional ID.
    assert ElfieDiagnostics(elfie).workspace is not old_workspace
    assert frame.elfie_id == ElfieId("resident-1")
    assert frame.events[0].meta.elfie_id == ElfieId("resident-1")
