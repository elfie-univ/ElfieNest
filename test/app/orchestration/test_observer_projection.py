"""Semantic Observer projection coverage at the orchestration boundary."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.orchestration.nest_session import ActorDescriptor, ElfieNestEngine
from elfie import Elfie
from nest.living_rules.models import (
    PersistentResidentState,
    ResidentPresence,
    RuntimeResidentMirror,
)
from nest.snapshot import NestSnapshot
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


def test_observer_projection_contains_nest_semantics_without_geometry() -> None:
    # Given: one registered Elfie has received a Runtime semantic mirror.
    engine = ElfieNestEngine(FakeWorldRuntime())
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.nest.apply_runtime_mirrors(
        (
            RuntimeResidentMirror(
                elfie_id="fox-1",
                current_zone_id="dorm",
                posture="resting",
                active_command_id="intent-7",
                runtime_id="runtime-a",
                runtime_generation=1,
                world_revision=1,
            ),
        )
    )

    # When: the application boundary requests the Observer projection.
    projected = engine.session.observer_semantic_entities()

    # Then: it exposes only semantic identity/state, never physics or transforms.
    assert projected["fox-1"].model_dump() == {
        "room_id": "local-nest",
        "zone_id": "dorm",
        "posture": "resting",
        "active": True,
        "active_command_id": "intent-7",
        "species_id": "fox",
        "appearance": {},
        "home_anchor_id": None,
    }


def test_observer_projection_includes_view_only_actor_semantics() -> None:
    # Given: one resident has a real actor descriptor and semantic home anchor.
    engine = ElfieNestEngine(FakeWorldRuntime())
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))

    # When: the Observer projection is assembled from existing profile/Nest facts.
    with (
        patch(
            "app.orchestration.nest_session.session.actor_catalog",
            return_value=(ActorDescriptor("fox-1", "fox", {"height_scale": 1.0}),),
        ),
        patch.object(engine.nest, "home_anchor_id", return_value="dorm-01/bed-01"),
    ):
        projected = engine.session.observer_semantic_entities()

    # Then: it carries semantic render inputs, never coordinates or transforms.
    assert projected["fox-1"].model_dump() == {
        "room_id": "local-nest",
        "zone_id": None,
        "posture": "standing",
        "active": True,
        "active_command_id": None,
        "species_id": "fox",
        "appearance": {"height_scale": 1.0},
        "home_anchor_id": "dorm-01/bed-01",
    }


def test_observer_projection_uses_persisted_home_when_runtime_is_not_connected() -> (
    None
):
    # Given: management has assigned a bed, but no authoritative Runtime catalog exists yet.
    state_store = MagicMock()
    state_store.load_snapshot.return_value = NestSnapshot(
        desired_bed_count=4,
        elapsed_seconds=0.0,
        catalog=None,
        residents=(
            PersistentResidentState(
                elfie_id="fox-1",
                presence=ResidentPresence.PENDING_RUNTIME,
                home_zone_id="dorm-01",
                home_anchor_id="dorm-01/bed-01",
            ),
        ),
    )
    engine = ElfieNestEngine(
        FakeWorldRuntime(),
        state_store=state_store,
    )
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))

    with patch(
        "app.orchestration.nest_session.session.actor_catalog",
        return_value=(ActorDescriptor("fox-1", "fox", {}),),
    ):
        projected = engine.session.observer_semantic_entities()

    assert projected["fox-1"].home_anchor_id == "dorm-01/bed-01"
