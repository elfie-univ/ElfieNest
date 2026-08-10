from __future__ import annotations

import pytest
from pydantic import ValidationError

from nest.godot_gateway.observer import (
    ObserverProjectionStore,
    ObserverSubscription,
    parse_authority_hello,
    parse_observer_hello,
)


def test_authority_and_observer_hello_are_versioned_and_mutually_exclusive() -> None:
    authority = {
        "protocol": 3,
        "role": "authority",
        "runtime_id": "authority-main",
        "nonce": "one-time-nonce",
    }
    observer = {
        "protocol": 3,
        "role": "observer",
        "subscription": {"kind": "room", "room_id": "local-nest"},
    }

    parsed_authority = parse_authority_hello(authority)
    parsed_observer = parse_observer_hello(observer)

    assert parsed_authority.runtime_id == "authority-main"
    assert parsed_observer.subscription.kind == "room"
    with pytest.raises(ValidationError):
        parse_observer_hello(authority)
    with pytest.raises(ValidationError):
        parse_authority_hello(observer)


def test_observer_replay_of_authority_nonce_is_rejected() -> None:
    replayed_authority = {
        "protocol": 3,
        "role": "observer",
        "subscription": {"kind": "room", "room_id": "local-nest"},
        "nonce": "authority-only-nonce",
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_observer_hello(replayed_authority)


@pytest.mark.parametrize(
    "forbidden_field",
    ["camera_token", "transform", "coordinates"],
)
def test_observer_rejects_camera_tokens_and_arbitrary_transform_writes(
    forbidden_field: str,
) -> None:
    raw = {
        "protocol": 3,
        "role": "observer",
        "subscription": {"kind": "elfie", "elfie_id": "fox-1"},
        forbidden_field: "forbidden",
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_observer_hello(raw)


def test_projection_snapshot_and_delta_carry_generation_sequence_and_entity_revision() -> (
    None
):
    projections = ObserverProjectionStore(generation=4)

    snapshot = projections.snapshot(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entities={"fox-1": {"zone_id": "dorm-01", "posture": "awake"}},
        entity_revisions={"fox-1": 1},
    )
    delta = projections.delta(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entity_id="fox-1",
        entity_revision=2,
        patch={"posture": "resting"},
    )

    assert (snapshot.generation, snapshot.sequence) == (4, 1)
    assert snapshot.entity_revisions == {"fox-1": 1}
    assert (delta.generation, delta.sequence, delta.entity_revision) == (4, 2, 2)


def test_projection_generation_or_sequence_mismatch_requires_resync_without_mutation() -> (
    None
):
    projections = ObserverProjectionStore(generation=4)
    snapshot = projections.snapshot(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entities={"fox-1": {"posture": "awake"}},
        entity_revisions={"fox-1": 1},
    )
    observer = projections.new_consumer()
    assert observer.accept(snapshot).resync_required is False
    baseline = observer.entities

    stale_generation = projections.delta(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entity_id="fox-1",
        entity_revision=2,
        patch={"posture": "resting"},
        generation=3,
    )
    skipped_sequence = projections.delta(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entity_id="fox-1",
        entity_revision=3,
        patch={"posture": "sleeping"},
        sequence=9,
    )

    assert observer.accept(stale_generation).resync_required is True
    assert observer.accept(skipped_sequence).resync_required is True
    assert observer.entities == baseline


def test_projection_rejects_non_monotonic_entity_revision_without_mutation() -> None:
    projections = ObserverProjectionStore(generation=4)
    observer = projections.new_consumer()
    snapshot = projections.snapshot(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entities={"fox-1": {"posture": "awake"}},
        entity_revisions={"fox-1": 2},
    )
    assert observer.accept(snapshot).resync_required is False
    baseline = observer.entities
    stale_entity = projections.delta(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entity_id="fox-1",
        entity_revision=1,
        patch={"posture": "resting"},
    )

    assert observer.accept(stale_entity).resync_required is True
    assert observer.entities == baseline


def test_projection_requires_snapshot_before_first_delta_without_mutation() -> None:
    projections = ObserverProjectionStore(generation=4)
    observer = projections.new_consumer()
    first_delta = projections.delta(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entity_id="fox-1",
        entity_revision=1,
        patch={"posture": "awake"},
    )

    result = observer.accept(first_delta)

    assert result.resync_required is True
    assert observer.entities == {}
