"""Engine scheduling tests for the asynchronous cognitive lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.orchestration.engine import ElfieNestEngine


def test_tick_once_only_advances_world_and_pumps_typed_inputs() -> None:
    # Given: one active Elfie whose cognitive worker may be independently blocked.
    with patch("app.orchestration.engine.GodotAPIServer"):
        engine = ElfieNestEngine(ws_port=18765, godot_origin_port=18000)
    elfie = MagicMock()
    elfie.identity.elfie_id = "elfie-1"
    engine.session.register_elfie("elfie-1", elfie)

    # When: five physical ticks run.
    for _ in range(5):
        engine.tick_once(1.0)

    # Then: no synchronous cognition method is called by the Engine.
    assert engine.nest.state.elapsed_seconds == 5.0
    assert elfie.advance_clock.call_count == 5
    assert elfie.pump_body_events.call_count == 5
    assert not hasattr(ElfieNestEngine, "respond_to_body_events")


def test_godot_owner_message_enters_communication_once() -> None:
    # Given: one registered Elfie and a stable external Godot message ID.
    with patch("app.orchestration.engine.GodotAPIServer"):
        engine = ElfieNestEngine(ws_port=18765, godot_origin_port=18000)
    elfie = MagicMock()
    elfie.identity.elfie_id = "elfie-1"
    engine.session.register_elfie("elfie-1", elfie)
    payload = {
        "elfie_id": "elfie-1",
        "owner_id": "owner-1",
        "conversation_id": "owner-chat",
        "message_id": "godot-message-1",
        "message": "hello",
    }

    # When: the same gateway delivery is replayed.
    engine._on_user_message(payload)
    engine._on_user_message(payload)

    # Then: the Communication boundary owns dedupe; Nest and Body get no copy.
    assert elfie.receive_communication_envelope.call_count == 2
    assert engine.nest.consume_user_message("elfie-1") == ""
    assert engine._collect_world_sensory_events("elfie-1") == []


def test_session_owner_message_bypasses_legacy_nest_buffer() -> None:
    # Given: the product session owns one Elfie with the new Communication boundary.
    with patch("app.orchestration.engine.GodotAPIServer"):
        engine = ElfieNestEngine(ws_port=18765, godot_origin_port=18000)
    elfie = MagicMock()
    elfie.identity.elfie_id = "elfie-1"
    engine.session.register_elfie("elfie-1", elfie)

    # When: a WebSocket or CLI owner message enters through NestSession.
    engine.session.send_user_message(
        "elfie-1",
        "hello",
        owner_id="owner-42",
        conversation_id="owner-chat",
        external_message_id="ws-message-1",
    )

    # Then: the message is delivered as a typed envelope, not staged in Nest.
    envelope = elfie.receive_communication_envelope.call_args.args[0]
    assert envelope.channel_id == "godot-owner"
    assert envelope.conversation_id == "owner-chat"
    assert envelope.external_message_id == "ws-message-1"
    assert envelope.parts[0].text == "hello"
    assert engine.nest.consume_user_message("elfie-1") == ""


def test_session_rejects_invalid_owner_identity_without_ws_exception() -> None:
    # Given: an overlong owner identity reaches the product boundary.
    with patch("app.orchestration.engine.GodotAPIServer"):
        engine = ElfieNestEngine(ws_port=18765, godot_origin_port=18000)
    elfie = MagicMock()
    elfie.identity.elfie_id = "elfie-1"
    engine.session.register_elfie("elfie-1", elfie)

    # When: the message cannot be parsed into the typed Communication contract.
    disposition = engine.session.send_user_message(
        "elfie-1",
        "hello",
        owner_id="x" * 200,
        external_message_id="ws-message-invalid-owner",
    )

    # Then: it is rejected at the boundary and does not call the Elfie runtime.
    assert disposition is None
    elfie.receive_communication_envelope.assert_not_called()
