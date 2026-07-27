"""Semantic Observer projection coverage at the orchestration boundary."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.orchestration.engine import ElfieNestEngine
from elfie import Elfie
from nest.godot_gateway.messages import CommandName, RuntimeEventFrame
from nest.state.models import RuntimeResidentMirror


class _RuntimeGateway:
    """Small no-connection gateway sufficient for a NestSession fixture."""

    runtime_connection = None

    def mark_runtime_ready(
        self,
        _connection: object,
        *,
        world_revision: int,
    ) -> None:
        _ = world_revision

    def send_runtime_command(
        self,
        _name: CommandName,
        _payload: dict[str, object],
        *,
        world_revision: int,
        correlation_id: str | None = None,
    ) -> str | None:
        _ = world_revision, correlation_id
        return None

    def drain_runtime_events(self) -> tuple[RuntimeEventFrame, ...]:
        return ()


def test_observer_projection_contains_nest_semantics_without_geometry() -> None:
    # Given: one registered Elfie has received a Runtime semantic mirror.
    engine = ElfieNestEngine(api_server=_RuntimeGateway())
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.nest.apply_runtime_mirrors(
        (
            RuntimeResidentMirror(
                elfie_id="fox-1",
                current_zone_id="dorm",
                posture="resting",
                active_command_id="intent-7",
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
    }
