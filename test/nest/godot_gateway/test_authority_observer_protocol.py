from __future__ import annotations

import pytest
from pydantic import ValidationError

from nest.godot_gateway.observer import (
    ObserverDelta,
    ObserverInterest,
    ObserverProjectionStore,
    ObserverSemanticEntity,
    ObserverSnapshot,
    ObserverSubscription,
    ViewerPrincipal,
    WorldChangingIntent,
    parse_authority_hello,
    parse_observer_hello,
)
from nest.godot_gateway.observer_sessions import (
    ObserverAuthorizationError,
    ObserverSessionRegistry,
)


def test_authority_and_observer_hello_are_versioned_and_mutually_exclusive() -> None:
    # Given: valid, deliberately distinct v3 connection claims.
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

    # When: each claim is parsed at its own trust boundary.
    parsed_authority = parse_authority_hello(authority)
    parsed_observer = parse_observer_hello(observer)

    # Then: authority identity cannot be interpreted as an observer capability.
    assert parsed_authority.runtime_id == "authority-main"
    assert parsed_observer.subscription.kind == "room"
    with pytest.raises(ValidationError):
        parse_observer_hello(authority)
    with pytest.raises(ValidationError):
        parse_authority_hello(observer)


def test_observer_replay_of_authority_nonce_is_rejected() -> None:
    # Given: an Observer has copied an authority handshake frame.
    replayed_authority = {
        "protocol": 3,
        "role": "observer",
        "subscription": {"kind": "room", "room_id": "local-nest"},
        "nonce": "authority-only-nonce",
    }

    # When / Then: its forbidden authority credential is rejected at parsing.
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_observer_hello(replayed_authority)


@pytest.mark.parametrize(
    "forbidden_field",
    ["camera_token", "transform", "coordinates"],
)
def test_observer_rejects_camera_tokens_and_arbitrary_transform_writes(
    forbidden_field: str,
) -> None:
    # Given: an observer hello tries to cross the local-camera boundary.
    raw = {
        "protocol": 3,
        "role": "observer",
        "subscription": {"kind": "elfie", "elfie_id": "fox-1"},
        forbidden_field: "forbidden",
    }

    # When / Then: it cannot enter the authority or observer transport.
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_observer_hello(raw)


def test_world_changing_intent_requires_authenticated_owner_or_elfie_family() -> None:
    # Given: a registry with one family-owned Elfie and a semantic sink.
    submitted: list[WorldChangingIntent] = []
    registry = ObserverSessionRegistry(
        owns_elfie=lambda user_id, elfie_id: user_id == 7 and elfie_id == "fox-1",
        submit_intent=submitted.append,
    )
    family = ViewerPrincipal(user_id=7, role="user")
    stranger = ViewerPrincipal(user_id=9, role="user")
    capability = registry.open_session(
        family,
        "family-session",
        ObserverSubscription(kind="elfie", elfie_id="fox-1"),
        expires_at=100.0,
    )
    intent = WorldChangingIntent(
        kind="request_interaction",
        actor_id="fox-1",
        interaction="greet",
    )

    # When: the family member requests one semantic interaction.
    registry.submit_world_intent(family, "family-session", capability, intent, now=10.0)

    # Then: it reaches the sink, while an unrelated observer cannot mutate it.
    assert submitted == [intent]
    with pytest.raises(ObserverAuthorizationError):
        registry.submit_world_intent(
            stranger, "stranger-session", capability, intent, now=10.0
        )
    with pytest.raises(ValidationError):
        WorldChangingIntent.model_validate(
            {
                "kind": "request_interaction",
                "actor_id": "fox-1",
                "interaction": "greet",
                "position": [1, 2, 3],
            }
        )


def test_owner_can_submit_validated_high_level_intent_for_any_elfie() -> None:
    # Given: an Owner is authenticated but does not own the selected Elfie.
    submitted: list[WorldChangingIntent] = []
    registry = ObserverSessionRegistry(
        owns_elfie=lambda _user_id, _elfie_id: False,
        submit_intent=submitted.append,
    )
    owner = ViewerPrincipal(user_id=1, role="owner")
    capability = registry.open_session(
        owner,
        "owner-session",
        ObserverSubscription(kind="room", room_id="local-nest"),
        expires_at=100.0,
    )
    intent = WorldChangingIntent(
        kind="request_interaction",
        actor_id="fox-2",
        interaction="rest",
    )

    # When: the Owner submits the allowed high-level intent.
    registry.submit_world_intent(owner, "owner-session", capability, intent, now=10.0)

    # Then: no coordinate, transform, or camera authority is needed.
    assert submitted == [intent]


def test_projection_snapshot_and_delta_carry_generation_sequence_and_entity_revision() -> (
    None
):
    # Given: an observer projection starts from a semantic entity state.
    projections = ObserverProjectionStore(generation=4)

    # When: it publishes an initial snapshot and a revisioned entity delta.
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

    # Then: consumers have an ordered, generation-scoped semantic stream.
    assert (snapshot.generation, snapshot.sequence) == (4, 1)
    assert snapshot.entity_revisions == {"fox-1": 1}
    assert (delta.generation, delta.sequence, delta.entity_revision) == (4, 2, 2)


def test_projection_generation_or_sequence_mismatch_requires_resync_without_mutation() -> (
    None
):
    # Given: an observer has accepted the first snapshot of generation four.
    projections = ObserverProjectionStore(generation=4)
    snapshot = projections.snapshot(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entities={"fox-1": {"posture": "awake"}},
        entity_revisions={"fox-1": 1},
    )
    observer = projections.new_consumer()
    assert observer.accept(snapshot).resync_required is False
    baseline = observer.entities

    # When: it receives the wrong generation and a skipped sequence.
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

    # Then: both frames demand resync and never mutate the local world view.
    assert observer.accept(stale_generation).resync_required is True
    assert observer.accept(skipped_sequence).resync_required is True
    assert observer.entities == baseline


def test_projection_rejects_non_monotonic_entity_revision_without_mutation() -> None:
    # Given: the observer has consumed entity revision two.
    projections = ObserverProjectionStore(generation=4)
    observer = projections.new_consumer()
    snapshot = projections.snapshot(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entities={"fox-1": {"posture": "awake"}},
        entity_revisions={"fox-1": 2},
    )
    assert observer.accept(snapshot).resync_required is False
    baseline = observer.entities

    # When: a correctly-sequenced but older entity revision arrives.
    stale_entity = projections.delta(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entity_id="fox-1",
        entity_revision=1,
        patch={"posture": "resting"},
    )

    # Then: it is rejected as a resync condition and leaves the view untouched.
    assert observer.accept(stale_entity).resync_required is True
    assert observer.entities == baseline


def test_projection_requires_snapshot_before_first_delta_without_mutation() -> None:
    # Given: a fresh Observer has not established a generation snapshot.
    projections = ObserverProjectionStore(generation=4)
    observer = projections.new_consumer()
    first_delta = projections.delta(
        scope=ObserverSubscription(kind="room", room_id="local-nest"),
        entity_id="fox-1",
        entity_revision=1,
        patch={"posture": "awake"},
    )

    # When: its first received frame is a delta rather than a snapshot.
    result = observer.accept(first_delta)

    # Then: it requests resync and does not materialize an entity state.
    assert result.resync_required is True
    assert observer.entities == {}


def test_capability_is_bound_to_one_session_and_expires_or_revokes() -> None:
    # Given: Alice gets a short-lived capability tied to one opaque session id.
    submitted: list[WorldChangingIntent] = []
    registry = ObserverSessionRegistry(
        owns_elfie=lambda user_id, elfie_id: user_id == 7 and elfie_id == "fox-1",
        submit_intent=submitted.append,
    )
    alice = ViewerPrincipal(user_id=7, role="user")
    intent = WorldChangingIntent(
        kind="request_interaction", actor_id="fox-1", interaction="greet"
    )
    capability = registry.open_session(
        alice,
        "hashed-session-a",
        ObserverSubscription(kind="elfie", elfie_id="fox-1"),
        expires_at=20.0,
    )

    # When: the same principal uses another session, expiry passes, or logout revokes.
    with pytest.raises(ObserverAuthorizationError):
        registry.submit_world_intent(
            alice, "hashed-session-b", capability, intent, now=10.0
        )
    with pytest.raises(ObserverAuthorizationError):
        registry.submit_world_intent(
            alice, "hashed-session-a", capability, intent, now=20.0
        )
    registry.revoke_session("hashed-session-a")
    with pytest.raises(ObserverAuthorizationError):
        registry.submit_world_intent(
            alice, "hashed-session-a", capability, intent, now=10.0
        )

    # Then: no unauthorized path ever reaches the world-intent sink.
    assert submitted == []


def test_projection_sessions_filter_independent_room_and_family_views() -> None:
    # Given: two family users own different Elfies in separate semantic rooms.
    entities = {
        "fox-1": ObserverSemanticEntity(
            room_id="room-1", zone_id="dorm", posture="awake", active=True
        ),
        "owl-1": ObserverSemanticEntity(
            room_id="room-2", zone_id="kitchen", posture="resting", active=True
        ),
    }
    registry = ObserverSessionRegistry(
        owns_elfie=lambda user_id, elfie_id: (
            (user_id, elfie_id) in {(7, "fox-1"), (8, "owl-1")}
        ),
        submit_intent=lambda _intent: None,
        semantic_entities=lambda: entities,
    )
    alice = ViewerPrincipal(user_id=7, role="user")
    bob = ViewerPrincipal(user_id=8, role="user")
    alice_capability = registry.open_session(
        alice,
        "alice-session",
        ObserverSubscription(kind="room", room_id="room-1"),
        expires_at=100.0,
    )
    bob_capability = registry.open_session(
        bob,
        "bob-session",
        ObserverSubscription(kind="room", room_id="room-2"),
        expires_at=100.0,
    )

    # When: both viewers establish a concurrent first projection.
    alice_frame = registry.next_projection(
        alice,
        "alice-session",
        alice_capability,
        acknowledged_generation=None,
        acknowledged_sequence=None,
        now=10.0,
    )
    bob_frame = registry.next_projection(
        bob,
        "bob-session",
        bob_capability,
        acknowledged_generation=None,
        acknowledged_sequence=None,
        now=10.0,
    )

    # Then: each receives only the room entity they are authorized to observe.
    assert isinstance(alice_frame, ObserverSnapshot)
    assert isinstance(bob_frame, ObserverSnapshot)
    assert set(alice_frame.entities) == {"fox-1"}
    assert set(bob_frame.entities) == {"owl-1"}
    assert "coordinates" not in alice_frame.entities["fox-1"].model_dump()


def test_projection_missing_delta_or_interest_change_returns_fresh_snapshot() -> None:
    # Given: a viewer has consumed an initial room snapshot.
    entities = {
        "fox-1": ObserverSemanticEntity(
            room_id="room-1", zone_id="dorm", posture="awake", active=True
        )
    }
    registry = ObserverSessionRegistry(
        owns_elfie=lambda _user_id, _elfie_id: True,
        submit_intent=lambda _intent: None,
        semantic_entities=lambda: entities,
    )
    owner = ViewerPrincipal(user_id=1, role="owner")
    capability = registry.open_session(
        owner,
        "owner-session",
        ObserverSubscription(kind="room", room_id="room-1"),
        expires_at=100.0,
    )
    initial = registry.next_projection(
        owner,
        "owner-session",
        capability,
        acknowledged_generation=None,
        acknowledged_sequence=None,
        now=10.0,
    )
    assert isinstance(initial, ObserverSnapshot)
    entities["fox-1"] = ObserverSemanticEntity(
        room_id="room-1", zone_id="dorm", posture="resting", active=True
    )
    delta = registry.next_projection(
        owner,
        "owner-session",
        capability,
        acknowledged_generation=initial.generation,
        acknowledged_sequence=initial.sequence,
        now=10.0,
    )
    assert isinstance(delta, ObserverDelta)
    entities["fox-1"] = ObserverSemanticEntity(
        room_id="room-1", zone_id="dorm", posture="sleeping", active=True
    )

    # When: it polls with the stale snapshot cursor, then reduces visible entities.
    resync = registry.next_projection(
        owner,
        "owner-session",
        capability,
        acknowledged_generation=initial.generation,
        acknowledged_sequence=initial.sequence,
        now=10.0,
    )
    registry.update_interest(
        owner,
        "owner-session",
        capability,
        ObserverInterest(
            subscription=ObserverSubscription(kind="room", room_id="room-1"),
            visible_entity_ids=("fox-1",),
        ),
        now=10.0,
    )
    after_interest = registry.next_projection(
        owner,
        "owner-session",
        capability,
        acknowledged_generation=None,
        acknowledged_sequence=None,
        now=10.0,
    )

    # Then: neither a missing delta nor an interest reduction applies speculative state.
    assert isinstance(resync, ObserverSnapshot)
    assert resync.entities["fox-1"].posture == "sleeping"
    assert isinstance(after_interest, ObserverSnapshot)
    assert after_interest.scope.kind == "room"


def test_slow_or_expired_observer_resyncs_without_unbounded_queue() -> None:
    # Given: a bounded session has established its first snapshot.
    entities = {
        "fox-1": ObserverSemanticEntity(
            room_id="room-1", zone_id="dorm", posture="awake", active=True
        )
    }
    registry = ObserverSessionRegistry(
        owns_elfie=lambda _user_id, _elfie_id: True,
        submit_intent=lambda _intent: None,
        semantic_entities=lambda: entities,
        max_pending_frames=2,
    )
    owner = ViewerPrincipal(user_id=1, role="owner")
    capability = registry.open_session(
        owner,
        "owner-session",
        ObserverSubscription(kind="room", room_id="room-1"),
        expires_at=20.0,
    )
    initial = registry.next_projection(
        owner,
        "owner-session",
        capability,
        acknowledged_generation=None,
        acknowledged_sequence=None,
        now=10.0,
    )
    assert isinstance(initial, ObserverSnapshot)
    for posture in ("resting", "sleeping", "awake"):
        entities["fox-1"] = ObserverSemanticEntity(
            room_id="room-1", zone_id="dorm", posture=posture, active=True
        )
        registry.publish_semantic_entities(entities)

    # When: its bounded queue overflows, and later the authenticated session expires.
    resync = registry.next_projection(
        owner,
        "owner-session",
        capability,
        acknowledged_generation=initial.generation,
        acknowledged_sequence=initial.sequence,
        now=10.0,
    )

    # Then: it gets a snapshot instead of accumulating frames, and expiry stops reads.
    assert isinstance(resync, ObserverSnapshot)
    assert resync.entities["fox-1"].posture == "awake"
    with pytest.raises(ObserverAuthorizationError):
        registry.next_projection(
            owner,
            "owner-session",
            capability,
            acknowledged_generation=resync.generation,
            acknowledged_sequence=resync.sequence,
            now=20.0,
        )


def test_malicious_high_frequency_intent_does_not_mutate_authority_sink() -> None:
    # Given: a family observer is rate limited and owns only Fox.
    submitted: list[WorldChangingIntent] = []
    registry = ObserverSessionRegistry(
        owns_elfie=lambda user_id, elfie_id: user_id == 7 and elfie_id == "fox-1",
        submit_intent=submitted.append,
        max_intents_per_window=2,
    )
    family = ViewerPrincipal(user_id=7, role="user")
    capability = registry.open_session(
        family,
        "family-session",
        ObserverSubscription(kind="room", room_id="room-1"),
        expires_at=100.0,
    )
    malicious = WorldChangingIntent(
        kind="request_interaction", actor_id="owl-1", interaction="greet"
    )

    # When: a client floods unauthorized high-level intents in one rate window.
    errors = 0
    for _ in range(8):
        with pytest.raises(ObserverAuthorizationError):
            registry.submit_world_intent(
                family,
                "family-session",
                capability,
                malicious,
                now=10.0,
            )
        errors += 1

    # Then: every request is rejected before the semantic authority sink mutates.
    assert errors == 8
    assert submitted == []
