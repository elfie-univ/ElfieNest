"""Single-owner six-channel emotion state with signed event dynamics."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Final, Mapping, Optional, Tuple
from uuid import uuid4

from elfie.brain.emotion.contracts import (
    AffectDirection,
    EmotionChange,
    EmotionEffectRecord,
    EmotionSnapshot,
    EmotionValue,
)
from elfie.brain.emotion.dynamics import (
    apply_signed_drive,
    calibrate_strength,
    noisy_or,
    passive_return,
)
from elfie.brain.emotion.emotion_input import EmotionInput
from elfie.brain.emotion.emotion_types import (
    EMOTION_CONFIGS,
    EMOTION_NAMES,
    EmotionType,
)
from elfie.brain.emotion.personality import EmotionParameters, PersonalityModifier
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.brain.state_lifecycle import StateRestoreError
from elfie.message_types import EventId, TurnId

if TYPE_CHECKING:
    from elfie.brain.emotion.expression_mapper import EmotionExpression

logger = logging.getLogger("elfie.brain.emotion.emotion_system")

_SOURCE_WEIGHTS: Final[Mapping[str, float]] = {
    "physical": 1.0,
    "text": 0.8,
    "social": 0.8,
    "execution": 1.0,
    "internal": 0.7,
    "model": 1.0,
}


class EmotionTimeRegressionError(Exception):
    """Raised when emotion state receives an older simulation timestamp."""

    def __init__(self, previous_timestamp: float, requested_timestamp: float) -> None:
        self.previous_timestamp = previous_timestamp
        self.requested_timestamp = requested_timestamp
        super().__init__(previous_timestamp, requested_timestamp)

    def __str__(self) -> str:
        return (
            "emotion simulation time cannot move backwards: "
            f"{self.previous_timestamp} -> {self.requested_timestamp}"
        )


@dataclass(frozen=True)
class EmotionOverride:
    """A bounded future appraisal hint, never an emotion stock mutation."""

    cause_key: str
    created_at: float
    expires_at: float
    confidence: float
    effect_count: int


@dataclass(frozen=True)
class EmotionCheckpoint:
    """Persistence-neutral checkpoint for the mutable affect owner."""

    revision: int
    last_updated_at: float
    emotions: Tuple[Tuple[str, float], ...]
    processed_events: Tuple[Tuple[str, str], ...]
    source_event_ids: Tuple[EventId, ...]
    effect_records: Tuple[EmotionEffectRecord, ...] = ()
    overrides: Tuple[EmotionOverride, ...] = ()


class EmotionSystem:
    """Own six short-term emotion stocks and their sole update path."""

    def __init__(
        self,
        personality: Optional[Mapping[str, float]] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        expression_config: Mapping[str, Any] | None = None,
        dynamics_config: Mapping[str, Any] | None = None,
    ) -> None:
        from elfie.brain.emotion.expression_mapper import ExpressionMapper

        self._clock = clock
        self._expression_mapper = ExpressionMapper(expression_config)
        raw_config = dynamics_config or {}
        channel_config = raw_config.get("channels", raw_config)
        self._base_config: dict[str, Mapping[str, float]] = {}
        for name in EMOTION_NAMES:
            configured = channel_config.get(name, EMOTION_CONFIGS[name])
            if not isinstance(configured, Mapping):
                raise ValueError(f"invalid emotion channel config: {name}")
            self._base_config[name] = dict(configured)
        self._source_weights = dict(_SOURCE_WEIGHTS)
        configured_weights = raw_config.get("source_weights", {})
        if isinstance(configured_weights, Mapping):
            for source, weight in configured_weights.items():
                self._source_weights[str(source)] = self._bounded_weight(weight)
        knots = raw_config.get("strength_knots")
        self._strength_knots = (
            tuple(float(value) for value in knots)
            if knots
            else (
                0.0,
                0.12,
                0.28,
                0.55,
                0.85,
                1.0,
            )
        )
        personality_overrides = raw_config.get("personality", {})
        self.personality_modifier = PersonalityModifier(
            personality,
            config=(
                personality_overrides
                if isinstance(personality_overrides, Mapping)
                else None
            ),
        )
        self._parameters: dict[str, EmotionParameters] = {
            name: self.personality_modifier.parameters(name, self._base_config[name])
            for name in EMOTION_NAMES
        }
        self.last_updated_at = float(clock())
        self.revision = 0
        self._source_event_ids: deque[EventId] = deque(maxlen=32)
        self._recent_changes: deque[EmotionChange] = deque(maxlen=128)
        self._effect_records: deque[EmotionEffectRecord] = deque(maxlen=64)
        self._processed_events: dict[str, str] = {}
        self._overrides: dict[str, EmotionOverride] = {}
        self.emotions: dict[str, float] = {
            name: self._parameters[name].baseline for name in EMOTION_NAMES
        }
        self._last_snapshot_values = dict(self.emotions)
        logger.info("emotion system initialized with six channels")

    @staticmethod
    def _bounded_weight(value: Any) -> float:
        number = float(value)
        if number < 0:
            raise ValueError("emotion source weight must be non-negative")
        return min(number, 4.0)

    def _simulation_time(self) -> float:
        return self.last_updated_at

    def parameters(self, emotion: EmotionType | str) -> EmotionParameters:
        return self._parameters[
            EmotionType(emotion).value if isinstance(emotion, EmotionType) else emotion
        ]

    def process_input(self, emotion_input: EmotionInput) -> Optional[EmotionChange]:
        """Apply a local positive diagnostic input through the typed path."""

        if not emotion_input.validate():
            return None
        try:
            emotion = EmotionType(emotion_input.emotion)
        except ValueError:
            return None
        stimulus = EmotionStimulusEvent(
            event_id=EventId(emotion_input.event_id),
            effects=(
                {
                    "channel": emotion,
                    "direction": AffectDirection.INCREASE,
                    "strength": round(emotion_input.intensity * 100),
                    "confidence": 1.0,
                },
            ),
            source=StimulusSource(emotion_input.source),
        )
        return self.apply_stimulus(stimulus)

    def update_emotion(self, name: str, delta: float) -> Optional[EmotionChange]:
        """Developer-only normalized adjustment routed through the event path.

        This remains available to diagnostics and focused experiments; product
        code must submit an identified ``EmotionStimulusEvent`` instead.
        Values are normalized stock deltas (a legacy 0..100-looking value is
        intentionally rejected rather than silently changing units).
        """

        if name not in EMOTION_NAMES or not -1.0 <= float(delta) <= 1.0:
            return None
        direction = AffectDirection.INCREASE if delta >= 0 else AffectDirection.DECREASE
        return self.apply_stimulus(
            EmotionStimulusEvent(
                event_id=EventId(f"diagnostic:{uuid4().hex}"),
                source=StimulusSource.INTERNAL,
                effects=(
                    {
                        "channel": EmotionType(name),
                        "direction": direction,
                        "strength": round(abs(float(delta)) * 100),
                        "confidence": 1.0,
                    },
                ),
            )
        )

    def apply_stimulus(
        self,
        stimulus: EmotionStimulusEvent,
        *,
        phase: str = "fast",
        status: str = "committed",
    ) -> Optional[EmotionChange]:
        """Apply every channel effect in one event; exact IDs are idempotent."""

        event_key = str(stimulus.event_id)
        fingerprint = stimulus.model_dump_json()
        previous_fingerprint = self._processed_events.get(event_key)
        if previous_fingerprint is not None:
            if previous_fingerprint != fingerprint:
                raise ValueError(f"emotion event id conflict: {event_key}")
            return None
        self._processed_events[event_key] = fingerprint
        self._source_event_ids.append(stimulus.event_id)
        by_channel: dict[str, dict[AffectDirection, list[float]]] = {
            name: {
                AffectDirection.INCREASE: [],
                AffectDirection.DECREASE: [],
            }
            for name in EMOTION_NAMES
        }
        for effect in stimulus.effects:
            if effect.direction is AffectDirection.UNCHANGED:
                continue
            name = effect.channel.value
            strength = calibrate_strength(effect.strength, knots=self._strength_knots)
            strength *= max(0.0, min(1.0, effect.confidence))
            strength *= self._source_weights.get(stimulus.source.value, 1.0)
            by_channel[name][effect.direction].append(strength)

        first_change: EmotionChange | None = None
        for name in EMOTION_NAMES:
            positives = noisy_or(by_channel[name][AffectDirection.INCREASE])
            negatives = noisy_or(by_channel[name][AffectDirection.DECREASE])
            if positives == 0.0 and negatives == 0.0:
                continue
            old_value = self.emotions[name]
            params = self._parameters[name]
            self.emotions[name] = apply_signed_drive(
                current=old_value,
                baseline=params.baseline,
                positive_gain=params.positive_gain,
                negative_gain=params.negative_gain,
                positive_evidence=positives,
                negative_evidence=negatives,
                dose=stimulus.dose,
            )
            if self.emotions[name] == old_value:
                continue
            self.revision += 1
            change = EmotionChange(
                revision=self.revision,
                occurred_at=datetime.fromtimestamp(self.last_updated_at, timezone.utc),
                event_id=stimulus.event_id,
                emotion=name,
                source=stimulus.source.value,
                previous_intensity=old_value,
                current_intensity=self.emotions[name],
            )
            self._recent_changes.append(change)
            first_change = first_change or change
        self._effect_records.append(
            EmotionEffectRecord(
                turn_id=stimulus.turn_id,
                event_id=stimulus.event_id,
                phase=phase if phase in {"fast", "slow"} else "fast",
                status=(
                    status
                    if status
                    in {"provisional", "replaced", "committed", "fast_unreviewed"}
                    else "committed"
                ),
                applied_at=datetime.fromtimestamp(self.last_updated_at, timezone.utc),
                source=stimulus.source.value,
                effect_count=len(stimulus.effects),
                cause_event_ids=(stimulus.event_id,),
            )
        )
        return first_change

    def recent_changes(self) -> Tuple[EmotionChange, ...]:
        return tuple(self._recent_changes)

    def effect_records(self) -> Tuple[EmotionEffectRecord, ...]:
        return tuple(self._effect_records)

    def mark_turn_unreviewed(self, turn_id: TurnId | str) -> None:
        key = str(turn_id)
        self._effect_records = deque(
            (
                record.model_copy(update={"status": "fast_unreviewed"})
                if str(record.turn_id) == key and record.phase == "fast"
                else record
                for record in self._effect_records
            ),
            maxlen=64,
        )

    def reconcile_turn(
        self,
        checkpoint: EmotionCheckpoint,
        *,
        turn_id: str,
        stimulus: EmotionStimulusEvent,
        timestamp: float,
    ) -> None:
        """Replace a provisional effect at its original turn time."""

        if timestamp < checkpoint.last_updated_at:
            raise EmotionTimeRegressionError(checkpoint.last_updated_at, timestamp)
        prior_records = tuple(
            record
            for record in self._effect_records
            if str(record.turn_id) == turn_id and record.phase == "fast"
        )
        self._restore_checkpoint_unchecked(checkpoint)
        self.apply_stimulus(
            stimulus.model_copy(
                update={
                    "event_id": EventId(f"emotion-feedback:{turn_id}"),
                    "turn_id": TurnId(turn_id),
                    "source": StimulusSource.MODEL,
                }
            ),
            phase="slow",
            status="replaced",
        )
        self.advance_to(timestamp)
        for record in prior_records:
            self._effect_records.append(
                record.model_copy(update={"status": "replaced"})
            )

    def register_override(
        self,
        *,
        cause_key: str,
        timestamp: float,
        ttl_seconds: float,
        confidence: float,
        effect_count: int,
    ) -> None:
        if not cause_key or ttl_seconds <= 0:
            return
        self._overrides[cause_key] = EmotionOverride(
            cause_key=cause_key,
            created_at=timestamp,
            expires_at=timestamp + min(ttl_seconds, 86_400.0),
            confidence=max(0.0, min(1.0, confidence)),
            effect_count=max(0, effect_count),
        )

    def has_active_override(
        self, cause_key: str, timestamp: float | None = None
    ) -> bool:
        now = self.last_updated_at if timestamp is None else timestamp
        override = self._overrides.get(cause_key)
        if override is None or override.expires_at <= now:
            self._overrides.pop(cause_key, None)
            return False
        return True

    def advance_to(self, timestamp: float) -> None:
        if timestamp < self.last_updated_at:
            raise EmotionTimeRegressionError(self.last_updated_at, timestamp)
        if timestamp == self.last_updated_at:
            return
        dt = timestamp - self.last_updated_at
        for name, value in self.emotions.items():
            params = self._parameters[name]
            self.emotions[name] = passive_return(
                value,
                params.baseline,
                dt,
                params.half_life_seconds,
            )
        self.last_updated_at = timestamp
        self.revision += 1

    def tick(self, dt: float) -> None:
        self.advance_to(self.last_updated_at + dt)

    def snapshot(self, at: float) -> EmotionSnapshot:
        self.advance_to(at)
        eligible = sorted(
            (
                (name, value)
                for name, value in self.emotions.items()
                if value >= self._parameters[name].activation_threshold
            ),
            key=lambda item: (-item[1], EMOTION_NAMES.index(item[0])),
        )
        primary = eligible[0][0] if eligible else None
        secondary = eligible[1][0] if len(eligible) > 1 else None
        total = sum(value for _name, value in eligible)
        values = tuple(
            EmotionValue(name=name, intensity=value)
            for name, value in self.emotions.items()
        )
        trends = tuple(
            (
                name,
                "rising"
                if value > self._last_snapshot_values.get(name, value) + 1e-6
                else "falling"
                if value < self._last_snapshot_values.get(name, value) - 1e-6
                else "steady",
            )
            for name, value in self.emotions.items()
        )
        self._last_snapshot_values = dict(self.emotions)
        return EmotionSnapshot(
            revision=self.revision,
            captured_at=datetime.fromtimestamp(at, timezone.utc),
            values=values,
            dominant=primary,
            primary=primary,
            secondary=secondary,
            primary_share=(eligible[0][1] / total if eligible and total else 0.0),
            secondary_share=(
                eligible[1][1] / total if len(eligible) > 1 and total else 0.0
            ),
            trends=trends,
            source_event_ids=tuple(self._source_event_ids),
        )

    def checkpoint(self) -> EmotionCheckpoint:
        return EmotionCheckpoint(
            revision=self.revision,
            last_updated_at=self.last_updated_at,
            emotions=tuple(sorted(self.emotions.items())),
            processed_events=tuple(sorted(self._processed_events.items())),
            source_event_ids=tuple(self._source_event_ids),
            effect_records=tuple(self._effect_records),
            overrides=tuple(self._overrides.values()),
        )

    def validate_checkpoint(self, checkpoint: EmotionCheckpoint) -> None:
        if checkpoint.revision < self.revision:
            raise StateRestoreError(
                "emotion checkpoint revision is older than current state"
            )
        if (
            checkpoint.revision == self.revision
            and checkpoint.last_updated_at < self.last_updated_at
        ):
            raise StateRestoreError(
                "emotion checkpoint simulation time is older than current state"
            )
        expected = set(EMOTION_NAMES)
        actual = {name for name, _value in checkpoint.emotions}
        if actual != expected:
            raise ValueError("emotion checkpoint contains an incompatible emotion set")
        for name, value in checkpoint.emotions:
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"emotion checkpoint value out of range: {name}")

    def restore(self, checkpoint: EmotionCheckpoint) -> None:
        self.validate_checkpoint(checkpoint)
        self._restore_checkpoint_unchecked(checkpoint)

    def _restore_checkpoint_unchecked(self, checkpoint: EmotionCheckpoint) -> None:
        self.emotions = dict(checkpoint.emotions)
        self.last_updated_at = checkpoint.last_updated_at
        self.revision = checkpoint.revision
        self._processed_events = dict(checkpoint.processed_events)
        self._source_event_ids = deque(checkpoint.source_event_ids, maxlen=32)
        self._effect_records = deque(checkpoint.effect_records, maxlen=64)
        self._overrides = {item.cause_key: item for item in checkpoint.overrides}
        self._last_snapshot_values = dict(self.emotions)

    def get_dominant_mood(self) -> str:
        return self.snapshot(self.last_updated_at).primary or "calm"

    def get_emotion_summary(self) -> str:
        return ", ".join(f"{name}:{value:.3f}" for name, value in self.emotions.items())

    def get_current_emotion_summary(self) -> str:
        return self.get_emotion_summary()

    def get_emotion_value(self, name: str) -> float:
        return self.emotions.get(name, 0.0)

    def get_expression(self) -> EmotionExpression:
        return self._expression_mapper.get_expression_for_emotions(self.emotions)


__all__ = (
    "EmotionCheckpoint",
    "EmotionOverride",
    "EmotionSystem",
    "EmotionTimeRegressionError",
)
