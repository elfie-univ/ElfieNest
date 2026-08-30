"""Single-owner six-channel emotion state with signed event dynamics."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Final, Mapping, Optional, Tuple

from elfie.brain.emotion.contracts import (
    AffectDirection,
    AffectiveAppraisal,
    AppraisalRelevance,
    ChannelEffect,
    EmotionSnapshot,
    EmotionValue,
    TrustedAppraisalScope,
)
from elfie.brain.emotion.dynamics import (
    apply_signed_drive,
    calibrate_strength,
    noisy_or,
    passive_return,
)
from elfie.brain.emotion.emotion_types import (
    EMOTION_CONFIGS,
    EMOTION_NAMES,
    EmotionType,
)
from elfie.brain.emotion.personality import EmotionParameters, PersonalityModifier
from elfie.brain.emotion.stimulus import EmotionStimulusEvent
from elfie.message_types import EventId

if TYPE_CHECKING:
    from elfie.brain.emotion.expression_mapper import EmotionExpression

logger = logging.getLogger("elfie.brain.emotion.emotion_system")

_SOURCE_WEIGHTS: Final[Mapping[str, float]] = {
    "physical": 1.0,
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
class EmotionTurnSnapshot:
    """Process-local state anchor used for one atomic frame transaction."""

    revision: int
    last_updated_at: float
    emotions: Tuple[Tuple[str, float], ...]
    source_event_ids: Tuple[EventId, ...]
    lifecycle_epoch: int


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
        if dynamics_config is None:
            raw_config: Mapping[str, Any] = {
                "channels": EMOTION_CONFIGS,
                "source_weights": _SOURCE_WEIGHTS,
                "strength_knots": (0.0, 0.12, 0.28, 0.55, 0.85, 1.0),
                "presentation": {
                    "trend_threshold": 0.05,
                    "secondary_ratio": 0.35,
                },
                "personality": {},
            }
        else:
            raw_config = dynamics_config
        channel_config = raw_config.get("channels")
        if not isinstance(channel_config, Mapping):
            raise ValueError("emotion dynamics config requires channels")
        self._base_config: dict[str, Mapping[str, float]] = {}
        for name in EMOTION_NAMES:
            configured = channel_config.get(name)
            if not isinstance(configured, Mapping):
                raise ValueError(f"invalid emotion channel config: {name}")
            if not {
                "baseline",
                "positive_gain",
                "negative_gain",
                "half_life_seconds",
                "activation_threshold",
            }.issubset(configured):
                raise ValueError(f"incomplete emotion channel config: {name}")
            self._base_config[name] = dict(configured)
        configured_weights = raw_config.get("source_weights")
        if not isinstance(configured_weights, Mapping):
            raise ValueError("emotion dynamics config requires source_weights")
        self._source_weights = {
            str(source): self._bounded_weight(weight)
            for source, weight in configured_weights.items()
        }
        knots = raw_config.get("strength_knots")
        if not isinstance(knots, (list, tuple)) or not knots:
            raise ValueError("emotion dynamics config requires strength_knots")
        self._strength_knots = tuple(float(value) for value in knots)
        presentation = raw_config.get("presentation")
        if not isinstance(presentation, Mapping):
            raise ValueError("emotion dynamics config requires presentation")
        self._trend_threshold = float(presentation["trend_threshold"])
        self._secondary_ratio = float(presentation["secondary_ratio"])
        personality_overrides = raw_config.get("personality")
        if not isinstance(personality_overrides, Mapping):
            raise ValueError("emotion dynamics config requires personality")
        self.personality_modifier = PersonalityModifier(
            personality,
            config=personality_overrides,
        )
        self._parameters: dict[str, EmotionParameters] = {
            name: self.personality_modifier.parameters(name, self._base_config[name])
            for name in EMOTION_NAMES
        }
        self.last_updated_at = float(clock())
        self.revision = 0
        self.lifecycle_epoch = 0
        self._source_event_ids: deque[EventId] = deque(maxlen=32)
        self._cause_guidance: OrderedDict[str, dict[EmotionType, ChannelEffect]] = (
            OrderedDict()
        )
        self.emotions: dict[str, float] = {
            name: self._parameters[name].baseline for name in EMOTION_NAMES
        }
        self._trend_reference = dict(self.emotions)
        logger.info("emotion system initialized with six channels")

    @staticmethod
    def _bounded_weight(value: Any) -> float:
        number = float(value)
        if number < 0:
            raise ValueError("emotion source weight must be non-negative")
        return min(number, 4.0)

    def parameters(self, emotion: EmotionType | str) -> EmotionParameters:
        name = (
            EmotionType(emotion).value if isinstance(emotion, EmotionType) else emotion
        )
        return self._parameters[name]

    def capture_turn_state(self) -> EmotionTurnSnapshot:
        return EmotionTurnSnapshot(
            revision=self.revision,
            last_updated_at=self.last_updated_at,
            emotions=tuple((name, self.emotions[name]) for name in EMOTION_NAMES),
            source_event_ids=tuple(self._source_event_ids),
            lifecycle_epoch=self.lifecycle_epoch,
        )

    def candidate_from(
        self,
        anchor: EmotionTurnSnapshot,
        stimuli: tuple[EmotionStimulusEvent, ...],
        *,
        timestamp: float,
    ) -> EmotionTurnSnapshot:
        """Purely calculate one complete candidate without mutating the owner."""

        if timestamp < anchor.last_updated_at:
            raise EmotionTimeRegressionError(anchor.last_updated_at, timestamp)
        values = dict(anchor.emotions)
        revision = anchor.revision
        source_ids = deque(anchor.source_event_ids, maxlen=32)

        for stimulus in stimuli:
            by_channel: dict[str, dict[AffectDirection, list[float]]] = {
                name: {
                    AffectDirection.INCREASE: [],
                    AffectDirection.DECREASE: [],
                }
                for name in EMOTION_NAMES
            }
            for appraisal in stimulus.appraisals:
                scope_weight = appraisal.scope.relationship_weight
                for effect in appraisal.effects:
                    strength = calibrate_strength(
                        effect.strength,
                        knots=self._strength_knots,
                    )
                    strength *= max(0.0, min(1.0, effect.confidence))
                    strength *= self._source_weights[stimulus.source.value]
                    strength *= scope_weight
                    by_channel[effect.channel.value][effect.direction].append(strength)

            source_ids.append(stimulus.event_id)
            for name in EMOTION_NAMES:
                positives = noisy_or(by_channel[name][AffectDirection.INCREASE])
                negatives = noisy_or(by_channel[name][AffectDirection.DECREASE])
                if positives == 0.0 and negatives == 0.0:
                    continue
                old_value = values[name]
                params = self._parameters[name]
                current = apply_signed_drive(
                    current=old_value,
                    baseline=params.baseline,
                    positive_gain=params.positive_gain,
                    negative_gain=params.negative_gain,
                    positive_evidence=positives,
                    negative_evidence=negatives,
                    dose=stimulus.dose,
                )
                values[name] = current
                if current == old_value:
                    continue
                revision += 1

        if timestamp > anchor.last_updated_at:
            dt = timestamp - anchor.last_updated_at
            for name, value in values.items():
                params = self._parameters[name]
                values[name] = passive_return(
                    value,
                    params.baseline,
                    dt,
                    params.half_life_seconds,
                )
            revision += 1

        return EmotionTurnSnapshot(
            revision=revision,
            last_updated_at=timestamp,
            emotions=tuple((name, values[name]) for name in EMOTION_NAMES),
            source_event_ids=tuple(source_ids),
            lifecycle_epoch=anchor.lifecycle_epoch,
        )

    def commit_turn_state(self, candidate: EmotionTurnSnapshot) -> bool:
        """Atomically swap one already validated candidate."""

        if candidate.lifecycle_epoch != self.lifecycle_epoch:
            return False
        if candidate.last_updated_at < self.last_updated_at:
            raise EmotionTimeRegressionError(
                self.last_updated_at,
                candidate.last_updated_at,
            )
        self._trend_reference = dict(self.emotions)
        self.emotions = dict(candidate.emotions)
        self.last_updated_at = candidate.last_updated_at
        self.revision = max(self.revision + 1, candidate.revision)
        self._source_event_ids = deque(candidate.source_event_ids, maxlen=32)
        return True

    def apply_stimulus(
        self,
        stimulus: EmotionStimulusEvent,
    ) -> None:
        """Apply one distinct stimulus; input deduplication belongs to Workspace."""

        anchor = self.capture_turn_state()
        candidate = self.candidate_from(
            anchor,
            (stimulus,),
            timestamp=self.last_updated_at,
        )
        self.commit_turn_state(candidate)

    def guidance_appraisal(
        self,
        cause_key: str | None,
        *,
        event_id: EventId,
    ) -> AffectiveAppraisal | None:
        """Project a prior model correction only onto the same live cause."""

        if cause_key is None:
            return None
        effects = self._cause_guidance.get(cause_key)
        if not effects:
            return None
        self._cause_guidance.move_to_end(cause_key)
        return AffectiveAppraisal(
            scope=TrustedAppraisalScope(
                scope_id=f"guidance:{event_id}",
                cause_event_id=event_id,
                relevance=AppraisalRelevance.DIRECT,
            ),
            effects=tuple(
                effects[channel] for channel in EmotionType if channel in effects
            ),
            reason="host-retained correction for the same continuing cause",
        )

    def update_cause_guidance(
        self,
        cause_key: str,
        effects: tuple[ChannelEffect, ...],
    ) -> None:
        """Retain bounded decrease-only corrections for one exact cause."""

        current = dict(self._cause_guidance.get(cause_key, {}))
        for effect in effects:
            if effect.direction is AffectDirection.DECREASE:
                current[effect.channel] = effect
            else:
                current.pop(effect.channel, None)
        if current:
            self._cause_guidance[cause_key] = current
            self._cause_guidance.move_to_end(cause_key)
            while len(self._cause_guidance) > 32:
                self._cause_guidance.popitem(last=False)
        else:
            self._cause_guidance.pop(cause_key, None)

    def advance_to(self, timestamp: float) -> None:
        if timestamp < self.last_updated_at:
            raise EmotionTimeRegressionError(self.last_updated_at, timestamp)
        if timestamp == self.last_updated_at:
            return
        previous = dict(self.emotions)
        dt = timestamp - self.last_updated_at
        for name, value in self.emotions.items():
            params = self._parameters[name]
            self.emotions[name] = passive_return(
                value,
                params.baseline,
                dt,
                params.half_life_seconds,
            )
        self._trend_reference = previous
        self.last_updated_at = timestamp
        self.revision += 1

    def reset_to_baseline(self, timestamp: float) -> None:
        """Start a new affect lifecycle epoch for sleep or process reset."""

        self.advance_to(timestamp)
        self._trend_reference = dict(self.emotions)
        self.emotions = {
            name: self._parameters[name].baseline for name in EMOTION_NAMES
        }
        self.lifecycle_epoch += 1
        self.revision += 1
        self._source_event_ids.clear()
        self._cause_guidance.clear()

    def snapshot(self, at: float) -> EmotionSnapshot:
        self.advance_to(at)
        return self._snapshot_from_values(
            values=self.emotions,
            revision=self.revision,
            captured_at=at,
            source_event_ids=tuple(self._source_event_ids),
            reference=self._trend_reference,
        )

    def snapshot_from_turn_state(
        self,
        state: EmotionTurnSnapshot,
        *,
        reference: EmotionTurnSnapshot | None = None,
    ) -> EmotionSnapshot:
        return self._snapshot_from_values(
            values=dict(state.emotions),
            revision=state.revision,
            captured_at=state.last_updated_at,
            source_event_ids=state.source_event_ids,
            reference=(dict(reference.emotions) if reference is not None else None),
        )

    def _snapshot_from_values(
        self,
        *,
        values: Mapping[str, float],
        revision: int,
        captured_at: float,
        source_event_ids: tuple[EventId, ...],
        reference: Mapping[str, float] | None,
    ) -> EmotionSnapshot:
        eligible = sorted(
            (
                (name, value)
                for name, value in values.items()
                if value >= self._parameters[name].activation_threshold
            ),
            key=lambda item: (-item[1], EMOTION_NAMES.index(item[0])),
        )
        primary_name = eligible[0][0] if eligible else None
        secondary_name = None
        if (
            len(eligible) > 1
            and eligible[1][1] >= eligible[0][1] * self._secondary_ratio
        ):
            secondary_name = eligible[1][0]
        active = tuple(
            EmotionValue(name=EmotionType(name), intensity=value)
            for name, value in eligible[:3]
            if primary_name is None or value >= eligible[0][1] * self._secondary_ratio
        )
        trends = ()
        if reference is not None:
            trends = tuple(
                (
                    EmotionType(name),
                    "rising" if value > reference.get(name, value) else "falling",
                )
                for name, value in values.items()
                if abs(value - reference.get(name, value)) >= self._trend_threshold
            )
        return EmotionSnapshot(
            revision=revision,
            captured_at=datetime.fromtimestamp(captured_at, timezone.utc),
            values=tuple(
                EmotionValue(name=EmotionType(name), intensity=values[name])
                for name in EMOTION_NAMES
            ),
            active=active,
            primary=EmotionType(primary_name) if primary_name else None,
            secondary=EmotionType(secondary_name) if secondary_name else None,
            trends=trends,
            source_event_ids=source_event_ids,
        )

    def get_primary_emotion(self) -> str:
        primary = self.snapshot(self.last_updated_at).primary
        return primary.value if primary is not None else "calm"

    def get_emotion_value(self, name: str) -> float:
        return self.emotions.get(name, 0.0)

    def get_expression(self) -> EmotionExpression:
        return self._expression_mapper.get_expression_for_emotions(self.emotions)


__all__ = (
    "EmotionSystem",
    "EmotionTimeRegressionError",
    "EmotionTurnSnapshot",
)
