from datetime import datetime, timezone

import pytest

from infrastructure.godot.gateway.messages import (
    CommandName,
    EventName,
    RuntimeEventFrame,
    SemanticLane,
)
from infrastructure.godot.gateway.session import (
    RuntimeAuthorityError,
    RuntimeQueueFullError,
    RuntimeSession,
    RuntimeSessionNotReadyError,
    StaleRuntimeEventError,
)


def _event(
    message_id: str,
    *,
    runtime_id: str = "runtime-main",
    generation: int = 1,
    revision: int = 1,
) -> RuntimeEventFrame:
    return RuntimeEventFrame(
        protocol=3,
        kind="event",
        lane=SemanticLane.NEST,
        name=EventName.WORLD_CONFIGURED,
        message_id=message_id,
        runtime_id=runtime_id,
        generation=generation,
        world_revision=revision,
        occurred_at=datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
        payload={"configured": True, "navigation_ready": True},
    )


def test_runtime_session_allows_one_authority_and_reconnects_after_disconnect() -> None:
    # Given
    session = RuntimeSession()

    # When
    first = session.acquire_authority("runtime-main")
    session.disconnect(first)
    second = session.acquire_authority("runtime-main")

    # Then
    assert first.generation == 1
    assert second.generation == 2


def test_runtime_session_rejects_second_live_runtime() -> None:
    # Given
    session = RuntimeSession()
    session.acquire_authority("runtime-main")

    # When / Then
    with pytest.raises(RuntimeAuthorityError, match="already owns authority"):
        session.acquire_authority("runtime-other")


def test_runtime_session_queues_events_until_explicit_drain_and_deduplicates() -> None:
    # Given
    session = RuntimeSession()
    connection = session.acquire_authority("runtime-main")
    event = _event("event-1", generation=connection.generation)

    # When
    session.enqueue_event(event)
    session.enqueue_event(event)
    drained = session.drain_events()

    # Then
    assert drained == (event,)
    assert session.drain_events() == ()
    assert session.duplicate_event_count == 1


def test_runtime_session_deduplicates_per_runtime_generation() -> None:
    # Given
    session = RuntimeSession()
    first = session.acquire_authority("runtime-main")
    session.enqueue_event(_event("event-1", generation=first.generation))
    session.disconnect(first)
    second = session.acquire_authority("runtime-main")

    # When
    event = _event("event-1", generation=second.generation)
    session.enqueue_event(event)
    drained = session.drain_events()

    # Then
    assert drained == (
        _event("event-1", generation=first.generation),
        event,
    )
    assert session.duplicate_event_count == 0


def test_runtime_session_rejects_stale_events_and_queue_overflow() -> None:
    # Given
    session = RuntimeSession(max_queue_size=1)
    connection = session.acquire_authority("runtime-main")
    session.enqueue_event(_event("event-1", generation=connection.generation))

    # When / Then
    with pytest.raises(RuntimeQueueFullError):
        session.enqueue_event(_event("event-2", generation=connection.generation))
    with pytest.raises(StaleRuntimeEventError):
        session.enqueue_event(_event("event-old", generation=connection.generation - 1))


def test_runtime_session_allows_retry_after_queue_overflow() -> None:
    session = RuntimeSession(max_queue_size=1)
    connection = session.acquire_authority("runtime-main")
    first = _event("event-1", generation=connection.generation)
    retry = _event("event-2", generation=connection.generation)
    session.enqueue_event(first)

    with pytest.raises(RuntimeQueueFullError):
        session.enqueue_event(retry)

    assert session.drain_events() == (first,)
    session.enqueue_event(retry)
    assert session.drain_events() == (retry,)
    assert session.duplicate_event_count == 0


def test_runtime_session_requires_ready_matching_revision_for_commands() -> None:
    # Given
    session = RuntimeSession()
    connection = session.acquire_authority("runtime-main")

    # When / Then
    with pytest.raises(RuntimeSessionNotReadyError):
        session.ensure_ready_for_command(world_revision=1)
    session.mark_world_configured(connection, world_revision=1)
    assert session.ensure_ready_for_command(world_revision=1) is None
    with pytest.raises(RuntimeSessionNotReadyError, match="world revision"):
        session.ensure_ready_for_command(world_revision=2)


def test_runtime_session_builds_config_before_ready_and_gates_actor_sync() -> None:
    session = RuntimeSession()
    connection = session.acquire_authority("runtime-main")

    configure = session.create_command(
        CommandName.CONFIGURE_WORLD,
        {"nest_id": "local-nest", "bed_count": 4, "world_revision": 1},
        world_revision=1,
    )

    assert configure.runtime_id == connection.runtime_id
    assert configure.generation == connection.generation
    with pytest.raises(RuntimeSessionNotReadyError):
        session.create_command(
            CommandName.SYNC_ACTORS,
            {"actors": []},
            world_revision=1,
        )
    session.mark_world_configured(connection, world_revision=1)
    sync = session.create_command(
        CommandName.SYNC_ACTORS,
        {"actors": []},
        world_revision=1,
    )
    assert sync.cause_id is None
    assert sync.lane is SemanticLane.NEST
    assert sync.message_id != configure.message_id
