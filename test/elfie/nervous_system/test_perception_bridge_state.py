"""State update and body rebinding tests for the perception bridge."""

from __future__ import annotations

from elfie import Elfie
from elfie.body import HeadlessBody
from elfie.body.contracts import (
    BodyId,
    BodySensorEvent,
    EnvironmentSample,
    TactileImpact,
)
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.message_types import EventId, TurnId
from elfie.nervous_system import NervousSystem
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from test.elfie.nervous_system.perception_bridge_fixtures import (
    ELFIE_ID,
    NOW,
    OWNER,
    ROOM,
    body_event,
    claim_all,
)


def test_humidity_and_illuminance_changes_publish_without_temperature_change() -> None:
    # Given: an initial environment sample has already been committed.
    workspace = PerceptualWorkspace(ELFIE_ID)
    nervous_system = NervousSystem(perception_sink=workspace, elfie_id=ELFIE_ID)
    nervous_system.receive_body_event(
        body_event(
            "environment-initial",
            ROOM,
            EnvironmentSample(
                kind="environment_sample",
                temperature_celsius=24.0,
                humidity_ratio=0.40,
                illuminance_lux=100.0,
            ),
        )
    )
    initial = claim_all(workspace)
    workspace.commit(initial.frame_id, TurnId(f"turn-{initial.frame_id}"))

    # When: only humidity and illuminance change.
    nervous_system.receive_body_event(
        body_event(
            "environment-changed",
            ROOM,
            EnvironmentSample(
                kind="environment_sample",
                temperature_celsius=24.0,
                humidity_ratio=0.55,
                illuminance_lux=180.0,
            ),
        )
    )
    changed = claim_all(workspace)

    # Then: both independently changed state values are retained.
    assert {update.state_key for update in changed.state_updates} == {
        "body:body-nervous:environment:humidity_ratio",
        "body:body-nervous:environment:illuminance_lux",
    }


def test_elfie_body_switch_updates_the_reflex_execution_target() -> None:
    # Given: an Elfie binds one body and then switches to another.
    elfie = Elfie(
        character_profile=create_visual_profile(
            elfie_id="elfie-body-switch",
            display_name="换身精灵",
            species_id="fox",
            seed=2,
        ),
        memory_store=SQLiteMemoryStoreAdapter.in_memory(),
    )
    old_body = HeadlessBody(body_id="old-body")
    current_body = HeadlessBody(body_id="current-body")
    elfie.register_body(old_body, make_current=True)
    elfie.register_body(current_body)
    elfie.bind_body(current_body.body_id)
    impact = BodySensorEvent(
        event_id=EventId("switched-impact"),
        body_id=BodyId(current_body.body_id),
        source=OWNER,
        occurred_at=NOW,
        received_at=NOW,
        payload=TactileImpact(
            kind="tactile_impact",
            location="front",
            force_newtons=25.0,
        ),
    )

    # When: the current body reports a dangerous impact.
    elfie.nervous_system.receive_body_event(impact)

    # Then: only the newly bound body executes the emergency stop.
    assert current_body.snapshot_body(now=NOW).last_command_id is not None
    assert old_body.snapshot_body(now=NOW).last_command_id is None
