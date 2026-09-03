"""Brain-owned self/world orientation projection for one continuous Elfie."""

from __future__ import annotations

from typing import Iterable, Literal, Optional, Tuple

from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.reasoning.context_types import EffectiveCapabilities
from elfie.brain.state_lifecycle import (
    StateCandidate,
    StateCheckpoint,
    StateCommitReceipt,
    StateCommitStatus,
    StateRestoreError,
    VersionedState,
    VersionedStateStore,
)
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    EmbodiedScope,
    PerceptionStateUpdate,
    SourceDomain,
    TurnFrame,
)
from elfie.message_types import ActorRef, EventId, TurnId, UTCDateTime

_LOCATION_KEYS = frozenset({"location", "room", "scene", "place"})
_POSITION_KEYS = ("position_x", "position_y", "position_z")
_VELOCITY_KEYS = ("velocity_x", "velocity_y", "velocity_z")


class OrientationSystem:
    """Project current body, scene facts and active scope without inventing facts."""

    def __init__(self, *, initial_at: UTCDateTime) -> None:
        initial = OrientationSnapshot.unknown().model_copy(
            update={"captured_at": initial_at}
        )
        self._store = VersionedStateStore(
            VersionedState(
                revision=initial.revision,
                committed_at=initial.captured_at,
                source_event_ids=(),
                causation_id=None,
                value=initial,
            )
        )

    def snapshot(self) -> OrientationSnapshot:
        return self._store.snapshot().value

    def checkpoint(self) -> StateCheckpoint[OrientationSnapshot]:
        return self._store.checkpoint()

    def commit(
        self, candidate: StateCandidate[OrientationSnapshot]
    ) -> StateCommitReceipt:
        """Commit an explicit orientation candidate through its sole owner."""
        if candidate.owner != "orientation":
            return StateCommitReceipt(
                candidate_id=candidate.candidate_id,
                status=StateCommitStatus.REJECTED,
                revision=self._store.snapshot().revision,
                reason="candidate_owner_mismatch",
            )
        return self._store.commit(candidate)

    def restore(self, checkpoint: StateCheckpoint[OrientationSnapshot]) -> None:
        self.validate_checkpoint(checkpoint)
        self._store.restore(checkpoint)

    def validate_checkpoint(
        self, checkpoint: StateCheckpoint[OrientationSnapshot]
    ) -> None:
        """Reject a checkpoint that rewinds the owned orientation."""
        if checkpoint.revision < self._store.snapshot().revision:
            raise StateRestoreError("orientation checkpoint revision is older")

    def observe(
        self,
        *,
        frame: TurnFrame,
        capabilities: EffectiveCapabilities,
        turn_id: TurnId,
        captured_at: UTCDateTime,
        activity_id: Optional[str] = None,
    ) -> tuple[OrientationSnapshot, StateCommitReceipt]:
        """Explicitly observe one admitted frame and commit its orientation."""
        candidate = self.candidate(
            frame=frame,
            capabilities=capabilities,
            turn_id=turn_id,
            captured_at=captured_at,
            activity_id=activity_id,
        )
        receipt = self._store.commit(candidate)
        return self.snapshot(), receipt

    def candidate(
        self,
        *,
        frame: TurnFrame,
        capabilities: EffectiveCapabilities,
        turn_id: TurnId,
        captured_at: UTCDateTime,
        activity_id: Optional[str] = None,
    ) -> StateCandidate[OrientationSnapshot]:
        """Build an immutable candidate without mutating the current snapshot."""
        previous = self._store.snapshot()
        previous_snapshot = previous.value
        body = capabilities.current_body
        location, location_source, location_sources = _location_fact(
            frame.state_updates
        )
        reused_location = False
        if location is None and previous_snapshot.location is not None:
            location = previous_snapshot.location
            location_source = previous_snapshot.location_source
            location_sources = previous_snapshot.source_event_ids[-4:]
            reused_location = True
        position, heading_degrees, velocity, pose_sources = _pose_fact(
            frame.state_updates,
            previous_snapshot,
        )
        nearby_actors = _nearby_actors(frame)
        if frame.source_domain is not SourceDomain.EMBODIED:
            nearby_actors = previous_snapshot.nearby_actors
        active_channel_id, active_conversation_id = _active_conversation(frame)
        source_event_ids = _unique_event_ids(
            write.meta.event_id
            for write in frame.events + frame.state_updates + frame.media_samples
        )
        unknown_fields: list[str] = []
        if body is None:
            unknown_fields.append("body")
        if location is None:
            unknown_fields.append("location")
        elif reused_location:
            unknown_fields.append("location_freshness")
        if position is None:
            unknown_fields.append("position")
        elif not pose_sources and previous_snapshot.position is not None:
            unknown_fields.append("position_freshness")
        if heading_degrees is None:
            unknown_fields.append("heading")
        elif not pose_sources and previous_snapshot.heading_degrees is not None:
            unknown_fields.append("heading_freshness")
        if velocity is None:
            unknown_fields.append("velocity")
        if frame.source_domain is SourceDomain.EMBODIED and not nearby_actors:
            unknown_fields.append("nearby_actors")
        elif frame.source_domain is not SourceDomain.EMBODIED:
            unknown_fields.append("nearby_actors")
        if frame.source_domain is not SourceDomain.COMMUNICATION:
            unknown_fields.append("active_session")
        if activity_id is None:
            unknown_fields.append("activity")
        if body is None:
            unknown_fields.append("affordances")

        freshness: Literal["current", "stale", "unknown"] = (
            "stale" if reused_location else "current"
        )
        if isinstance(frame.interaction_scope, EmbodiedScope):
            if body is None or (
                body.body_id != frame.interaction_scope.body_id
                or body.body_generation != frame.interaction_scope.body_generation
            ):
                freshness = "stale"
                unknown_fields.append("embodied_scope")

        snapshot = OrientationSnapshot(
            revision=previous.revision + 1,
            captured_at=captured_at,
            current_turn_id=turn_id,
            body_id=body.body_id if body is not None else None,
            body_generation=body.body_generation if body is not None else None,
            location=location,
            location_source=location_source,
            position=position,
            heading_degrees=heading_degrees,
            velocity=velocity,
            active_channel_id=active_channel_id,
            active_conversation_id=active_conversation_id,
            nearby_actors=nearby_actors,
            activity_id=activity_id,
            affordances=body.actions if body is not None else (),
            source_event_ids=_unique_event_ids(
                source_event_ids + location_sources + pose_sources
            ),
            unknown_fields=tuple(dict.fromkeys(unknown_fields)),
            freshness=freshness,
        )
        return StateCandidate(
            candidate_id=EventId(f"orientation:{frame.frame_id}:{turn_id}"),
            owner="orientation",
            base_revision=previous.revision,
            source_event_ids=snapshot.source_event_ids,
            causation_id=frame.frame_id,
            created_at=captured_at,
            value=snapshot,
        )


def _location_fact(
    updates: Iterable[PerceptionStateUpdate],
) -> tuple[
    Optional[str],
    Literal["runtime", "observation", "unknown"],
    Tuple[EventId, ...],
]:
    selected: Optional[PerceptionStateUpdate] = None
    for update in updates:
        suffix = update.state_key.rsplit(":", 1)[-1].lower()
        if (
            suffix in _LOCATION_KEYS
            and isinstance(update.value, str)
            and update.value.strip()
        ):
            selected = update
    if selected is None:
        return None, "unknown", ()
    assert isinstance(selected.value, str)
    return selected.value.strip(), "observation", (selected.meta.event_id,)


def _pose_fact(
    updates: Iterable[PerceptionStateUpdate],
    previous: OrientationSnapshot,
) -> tuple[
    Optional[Tuple[float, float, float]],
    Optional[float],
    Optional[Tuple[float, float, float]],
    Tuple[EventId, ...],
]:
    """Project the latest Body proprioception pose without inventing values."""
    positions: list[Optional[float]] = list(previous.position or (None, None, None))
    velocities: list[Optional[float]] = list(previous.velocity or (None, None, None))
    heading = previous.heading_degrees
    source_ids: list[EventId] = []
    position_indexes = {key: index for index, key in enumerate(_POSITION_KEYS)}
    velocity_indexes = {key: index for index, key in enumerate(_VELOCITY_KEYS)}
    for update in updates:
        suffix = update.state_key.rsplit(":", 1)[-1].lower()
        value = update.value
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        numeric_value = float(value)
        if suffix in position_indexes:
            positions[position_indexes[suffix]] = numeric_value
            source_ids.append(update.meta.event_id)
        elif suffix == "heading_degrees":
            heading = numeric_value
            source_ids.append(update.meta.event_id)
        elif suffix in velocity_indexes:
            velocities[velocity_indexes[suffix]] = numeric_value
            source_ids.append(update.meta.event_id)

    position = (
        (float(positions[0]), float(positions[1]), float(positions[2]))
        if all(value is not None for value in positions)
        else None
    )
    velocity = (
        (float(velocities[0]), float(velocities[1]), float(velocities[2]))
        if all(value is not None for value in velocities)
        else None
    )
    return (
        position,
        heading,
        velocity,
        _unique_event_ids(source_ids),
    )


def _nearby_actors(frame: TurnFrame) -> Tuple[ActorRef, ...]:
    if frame.source_domain is not SourceDomain.EMBODIED:
        return ()
    actors: list[ActorRef] = []
    seen: set[str] = set()
    for event in frame.events:
        actor = event.meta.source
        actor_id = str(actor.actor_id)
        if actor_id in seen:
            continue
        seen.add(actor_id)
        actors.append(actor)
    return tuple(actors)


def _active_conversation(
    frame: TurnFrame,
) -> tuple[Optional[str], Optional[str]]:
    scope = frame.interaction_scope
    if not isinstance(scope, CommunicationScope):
        return None, None
    return scope.channel_id, scope.conversation_id


def _unique_event_ids(event_ids: Iterable[EventId]) -> Tuple[EventId, ...]:
    return tuple(dict.fromkeys(event_ids))


__all__ = ("OrientationSystem",)
