"""The Brain observation surface stays zero-cost when no sink is injected."""

from __future__ import annotations

import pytest

from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.brain.observation import BrainObservation
from elfie.communication import CommunicationHub
from elfie.factory import ElfieAssembly
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from test.elfie.test_cognitive_lifecycle import (
    CONSTITUTION,
    RecordingChannel,
    TwoTurnRuntime,
    _owner_message,
    _selfhood_seed,
)


def test_brain_observation_envelope_is_never_constructed_without_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: constructing any BrainObservation envelope fails the test.
    def _forbid_construction(*args: object, **kwargs: object) -> None:
        raise AssertionError("BrainObservation constructed while no sink is wired")

    monkeypatch.setattr(BrainObservation, "__init__", _forbid_construction)

    # And: a production Elfie whose cognition was configured without a sink.
    body = HeadlessBody(body_id="body-zero-cost")
    body.connect()
    hub = CommunicationHub("elfie-zero-cost")
    channel = RecordingChannel()
    hub.register_channel(channel, connect=True)
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=create_visual_profile(
                elfie_id="elfie-zero-cost",
                display_name="elfie-zero-cost",
                species_id="fox",
                seed=1,
            ),
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            selfhood_seed=_selfhood_seed("elfie-zero-cost"),
            reasoning_constitution=CONSTITUTION,
            body=body,
            communication=hub,
            model_port=runtime,
        )
    )

    # When: one owner turn runs end to end, including a baseline Memory recall.
    elfie.start()
    elfie.receive_communication_envelope(
        _owner_message(
            elfie.cognitive_datetime,
            text="你还记得我们上次说好的事吗",
            elfie_id="elfie-zero-cost",
        )
    )
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(1, timeout=2)
    assert len(runtime.requests) == 1
    first = elfie.turn_outcomes()[0]

    # Then: the turn settles successfully without a single envelope construction.
    elfie.wait_for_output(first.turn_id, timeout=1)
    assert elfie.turn_decision(first.turn_id) is not None
    elfie.stop()
    elfie.join()
