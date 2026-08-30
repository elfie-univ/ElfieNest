"""The single deterministic Retention v2 policy owned by Memory.

The policy keeps three persisted semantic values separate:

* ``importance`` (I) is changed by sourced semantic appraisal events;
* ``retention_days`` (D) is changed by qualified outcome/review events;
* ``confidence`` (C) is recomputed from unique, independent Evidence.

``freshness`` (F) and the composite Recall rank are derived values. This
module is intentionally persistence-, model- and clock-independent: callers
provide all timestamps and the adapter persists the returned result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Literal, Optional, Sequence, Tuple, Union

EvidenceStance = Literal["supports", "contradicts", "context"]
ImportanceDirection = Literal["raise", "lower"]

_Timestamp = Union[str, datetime]

FRESHNESS_EXPONENT = 2.6
FRESHNESS_SCALE = 9.0
FRESHNESS_ACTIVE_THRESHOLD = 0.10
FRESHNESS_COMPRESS_THRESHOLD = 0.40
FRESHNESS_DIGEST_THRESHOLD = 0.20
FRESHNESS_FORGET_THRESHOLD = 0.01
MAX_RETENTION_DAYS = 36_500.0
SECONDS_PER_DAY = 86_400.0
MAX_FUTURE_SKEW_SECONDS = 300.0
UTC = timezone.utc


@dataclass(frozen=True)
class ImportanceEvent:
    """A typed, source-linked semantic appraisal event."""

    event_id: str
    target_kind: str
    target_id: str
    direction: ImportanceDirection
    event_class: str
    occurred_at: _Timestamp
    source_episode_id: Optional[str] = None

    def __post_init__(self) -> None:
        for name, value in (
            ("event_id", self.event_id),
            ("target_kind", self.target_kind),
            ("target_id", self.target_id),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be blank")
        if self.direction not in {"raise", "lower"}:
            raise ValueError("unsupported importance direction")
        if not self.event_class.strip():
            raise ValueError("event_class must not be blank")
        if self.source_episode_id is not None and not self.source_episode_id.strip():
            raise ValueError("source_episode_id must not be blank when supplied")
        _as_utc(self.occurred_at)


@dataclass(frozen=True)
class ImportanceAggregate:
    """One accepted event after ClosedEpisode/window aggregation."""

    event_id: str
    target_kind: str
    target_id: str
    direction: ImportanceDirection
    event_class: str
    occurred_at: datetime


@dataclass(frozen=True)
class EvidenceContribution:
    """One immutable Evidence contribution to a Node or Assertion."""

    evidence_id: str
    independence_key: str
    stance: EvidenceStance
    weight: float

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.independence_key.strip():
            raise ValueError("evidence_id and independence_key must not be blank")
        if self.stance not in {"supports", "contradicts", "context"}:
            raise ValueError("unsupported evidence stance")
        _positive_finite(self.weight, "weight")


@dataclass(frozen=True)
class RetentionUpdate:
    """Materialized result of one accepted retention reinforcement."""

    retention_days: float
    last_reinforced_at: datetime
    freshness: float


@dataclass(frozen=True)
class SemanticScore:
    """The one final Recall score and its bounded components."""

    rank: float
    activity: float
    freshness: float
    importance: float
    confidence: Optional[float]


class MemoryScorePolicy:
    """The versioned, deterministic Memory Retention v2 policy."""

    version = "memory.v2"
    max_retention_days = MAX_RETENTION_DAYS
    max_future_skew_seconds = MAX_FUTURE_SKEW_SECONDS
    active_freshness_threshold = FRESHNESS_ACTIVE_THRESHOLD
    compress_freshness_threshold = FRESHNESS_COMPRESS_THRESHOLD
    digest_freshness_threshold = FRESHNESS_DIGEST_THRESHOLD
    forget_freshness_threshold = FRESHNESS_FORGET_THRESHOLD

    # Initial spans are policy classes, not free-form caller numbers.
    initial_retention_days = {
        "transient": 2.0,
        "ordinary": 7.0,
        "salient": 30.0,
        "genesis": 3650.0,
    }

    # The model may propose only one of these names. Values belong to code.
    _importance_targets = {
        "raise": {
            # Admission records the source-provided starting value.  It is an
            # audit event and intentionally has no update effect when replayed.
            "admission": (0.0, 0.0, -1),
            "routine": (0.35, 0.10, 0),
            "meaningful": (0.60, 0.20, 1),
            "major": (0.85, 0.35, 2),
            "core": (1.00, 0.50, 3),
        },
        "lower": {
            "ordinary-lower": (0.30, 0.25, 0),
            "major-lower": (0.10, 0.50, 1),
            "revoked": (0.00, 1.00, 2),
        },
    }

    # Runtime evidence never supplies an arbitrary numeric reliability.
    source_reliability_weights = {
        "owner_explicit": 1.0,
        "observed": 0.9,
        "told": 0.7,
        "inferred": 0.4,
        "felt": 0.4,
        "seed": 1.0,
    }

    @classmethod
    def initial_retention(cls, retention_class: str) -> float:
        """Return the policy-owned initial ``D`` for a typed admission class."""

        try:
            return cls.initial_retention_days[retention_class]
        except KeyError as exc:
            raise ValueError(f"unsupported retention class: {retention_class}") from exc

    @classmethod
    def admission_retention(
        cls,
        retention_class: str,
        *,
        emotion_intensity: float | None = None,
        sensory_present: bool = False,
        genesis: bool = False,
    ) -> float:
        """Resolve one bounded admission class to its initial ``D``.

        Strong sourced salience may promote an ordinary/transient admission to
        the 30-day class.  This is deliberately a retention-only decision:
        it does not alter ``importance`` or ``confidence``.  Genesis has a
        fixed ten-year starting span regardless of caller hints.
        """
        if genesis:
            return cls.initial_retention("genesis")
        base = cls.initial_retention(retention_class)
        if emotion_intensity is not None:
            intensity = _finite_ratio(emotion_intensity, "emotion_intensity")
            if intensity >= 0.7:
                base = max(base, cls.initial_retention("salient"))
        if sensory_present:
            base = max(base, cls.initial_retention("salient"))
        return min(cls.max_retention_days, base)

    @staticmethod
    def bounded(value: float, name: str = "value") -> float:
        """Validate and clamp a semantic ratio to ``[0, 1]``."""

        return _finite_ratio(value, name)

    @classmethod
    def freshness(
        cls,
        now: _Timestamp,
        last_reinforced_at: _Timestamp,
        retention_days: float,
    ) -> float:
        """Derive current memory clarity from time and the retained span."""

        days = _retention_days(retention_days)
        current = _as_utc(now)
        anchor = _as_utc(last_reinforced_at)
        elapsed_days = max(0.0, (current - anchor).total_seconds() / SECONDS_PER_DAY)
        ratio = elapsed_days / days
        if ratio == 0.0:
            return 1.0
        # Avoid overflowing pow for very old records; the limit is already
        # far below any lifecycle threshold.
        if ratio >= 1e120:
            return 0.0
        value = 1.0 / (1.0 + FRESHNESS_SCALE * math.pow(ratio, FRESHNESS_EXPONENT))
        return min(1.0, max(0.0, value))

    @classmethod
    def next_review_at(
        cls,
        last_reinforced_at: _Timestamp,
        retention_days: float,
        freshness_threshold: float,
    ) -> datetime:
        """Return the UTC crossing time for one lifecycle threshold."""

        threshold = _finite_ratio(freshness_threshold, "freshness_threshold")
        if threshold <= 0.0:
            raise ValueError("freshness_threshold must be greater than zero")
        days = _retention_days(retention_days)
        ratio = math.pow(
            ((1.0 / threshold) - 1.0) / FRESHNESS_SCALE,
            1.0 / FRESHNESS_EXPONENT,
        )
        return _as_utc(last_reinforced_at) + timedelta(days=days * ratio)

    @classmethod
    def reinforce(
        cls,
        *,
        retention_days: float,
        last_reinforced_at: _Timestamp,
        occurred_at: _Timestamp,
    ) -> Optional[RetentionUpdate]:
        """Apply one qualified event when its event-time ``F`` is still active.

        Callers replay receipts in event-time order. A late receipt is thus
        evaluated against the state that existed at its original occurrence,
        never against processing time. ``None`` means the event was already
        archival or arrived before the current replay anchor.
        """

        days = _retention_days(retention_days)
        anchor = _as_utc(last_reinforced_at)
        event_time = _as_utc(occurred_at)
        if event_time < anchor:
            return None
        event_freshness = cls.freshness(event_time, anchor, days)
        if event_freshness < cls.active_freshness_threshold:
            return None
        q = (1.0 - event_freshness) / (1.0 - cls.active_freshness_threshold)
        new_days = min(cls.max_retention_days, days * (1.0 + q * q))
        return RetentionUpdate(
            retention_days=new_days,
            last_reinforced_at=event_time,
            freshness=1.0,
        )

    @classmethod
    def validate_event_time(
        cls,
        *,
        now: _Timestamp,
        occurred_at: _Timestamp,
    ) -> datetime:
        """Reject a write event that is materially ahead of the adapter clock."""
        current = _as_utc(now)
        event_time = _as_utc(occurred_at)
        if event_time - current > timedelta(seconds=cls.max_future_skew_seconds):
            raise ValueError("event timestamp is too far in the future")
        return event_time

    @classmethod
    def importance_event_policy(
        cls,
        direction: ImportanceDirection,
        event_class: str,
    ) -> Tuple[float, float, int]:
        """Resolve a model-proposed class into target, eta and rank."""

        try:
            return cls._importance_targets[direction][event_class]
        except KeyError as exc:
            raise ValueError(
                f"unsupported {direction} importance event class: {event_class}"
            ) from exc

    @classmethod
    def apply_importance(
        cls,
        *,
        current: float,
        direction: ImportanceDirection,
        event_class: str,
    ) -> float:
        """Move importance toward the policy target in the requested direction."""

        value = _finite_ratio(current, "importance")
        target, eta, _ = cls.importance_event_policy(direction, event_class)
        if direction == "raise" and target <= value:
            return value
        if direction == "lower" and target >= value:
            return value
        return _finite_ratio(value + eta * (target - value), "importance")

    @classmethod
    def aggregate_importance_events(
        cls,
        events: Iterable[ImportanceEvent],
    ) -> Tuple[ImportanceAggregate, ...]:
        """Collapse duplicate ClosedEpisode signals and 24-hour event windows.

        Raise and lower directions use independent windows anchored by the
        first event in each chronological window. A selected event carries
        the timestamp of the highest class so opposite-direction reappraisals
        can still be folded in one deterministic event-time stream.
        """

        materialized = list(events)
        deduped: dict[
            tuple[str, str, ImportanceDirection, str, str], ImportanceEvent
        ] = {}
        for event in materialized:
            # A ClosedEpisode ID identifies repeated signals from one source
            # episode.  Events without that source identity are independent
            # submissions and must not collapse merely because they share a
            # direction and class.
            source_key = event.source_episode_id or f"event:{event.event_id}"
            importance_key = (
                event.target_kind,
                event.target_id,
                event.direction,
                source_key,
                event.event_class,
            )
            existing = deduped.get(importance_key)
            if existing is None or _event_sort_key(event) < _event_sort_key(existing):
                deduped[importance_key] = event

        grouped: dict[tuple[str, str, ImportanceDirection], list[ImportanceEvent]] = {}
        for event in deduped.values():
            # Validate the class even when it will later be superseded.
            cls.importance_event_policy(event.direction, event.event_class)
            window_key = (event.target_kind, event.target_id, event.direction)
            grouped.setdefault(window_key, []).append(event)

        accepted: List[ImportanceAggregate] = []
        window = timedelta(hours=24)

        def flush(
            bucket: Sequence[ImportanceEvent],
            target_kind: str,
            target_id: str,
            direction: ImportanceDirection,
        ) -> None:
            if not bucket:
                return
            selected = max(
                bucket,
                key=lambda item: (
                    cls.importance_event_policy(item.direction, item.event_class)[2],
                    _event_sort_key(item),
                ),
            )
            accepted.append(
                ImportanceAggregate(
                    event_id=selected.event_id,
                    target_kind=target_kind,
                    target_id=target_id,
                    direction=direction,
                    event_class=selected.event_class,
                    occurred_at=_as_utc(selected.occurred_at),
                )
            )

        for (target_kind, target_id, direction), group in grouped.items():
            ordered = sorted(group, key=_event_sort_key)
            start: Optional[datetime] = None
            bucket: List[ImportanceEvent] = []

            for event in ordered:
                event_time = _as_utc(event.occurred_at)
                if start is None or event_time < start + window:
                    if start is None:
                        start = event_time
                    bucket.append(event)
                    continue
                flush(bucket, target_kind, target_id, direction)
                bucket = [event]
                start = event_time
            flush(bucket, target_kind, target_id, direction)

        return tuple(
            sorted(
                accepted,
                key=lambda item: (
                    item.target_kind,
                    item.target_id,
                    item.occurred_at,
                    item.event_id,
                ),
            )
        )

    @classmethod
    def fold_importance(
        cls,
        *,
        initial: float,
        events: Iterable[ImportanceEvent],
        target_kind: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> float:
        """Replay accepted importance aggregates in event-time order."""

        value = _finite_ratio(initial, "importance")
        aggregates = [
            event
            for event in cls.aggregate_importance_events(events)
            if (target_kind is None or event.target_kind == target_kind)
            and (target_id is None or event.target_id == target_id)
        ]
        for event in sorted(
            aggregates, key=lambda item: (item.occurred_at, item.event_id)
        ):
            value = cls.apply_importance(
                current=value,
                direction=event.direction,
                event_class=event.event_class,
            )
        return value

    @classmethod
    def confidence_from_evidence(
        cls,
        *,
        initial_confidence: float,
        prior_weight: float,
        contributions: Sequence[EvidenceContribution],
    ) -> float:
        """Recompute C from unique evidence and independence groups."""

        initial = _finite_ratio(initial_confidence, "initial_confidence")
        prior = _positive_finite(prior_weight, "prior_weight")
        grouped: dict[tuple[str, EvidenceStance], EvidenceContribution] = {}
        for contribution in contributions:
            key = (contribution.independence_key, contribution.stance)
            existing = grouped.get(key)
            if existing is None or contribution.weight > existing.weight:
                grouped[key] = contribution
        support = sum(
            item.weight for item in grouped.values() if item.stance == "supports"
        )
        conflict = sum(
            item.weight for item in grouped.values() if item.stance == "contradicts"
        )
        denominator = prior + support + conflict
        if denominator <= 0.0:
            return initial
        return _finite_ratio((prior * initial + support) / denominator, "confidence")

    @classmethod
    def source_reliability_weight(cls, reliability_class: str) -> float:
        """Resolve a fixed source class to a deterministic Evidence weight."""

        try:
            return cls.source_reliability_weights[reliability_class]
        except KeyError as exc:
            raise ValueError(
                f"unsupported source reliability class: {reliability_class}"
            ) from exc

    @classmethod
    def recall_score(
        cls,
        *,
        relevance: float,
        freshness: float,
        importance: float,
        confidence: Optional[float],
    ) -> SemanticScore:
        """Calculate the one kind-aware composite score used after Recall R."""

        r = _finite_ratio(relevance, "relevance")
        f = _finite_ratio(freshness, "freshness")
        i = _finite_ratio(importance, "importance")
        c = None if confidence is None else _finite_ratio(confidence, "confidence")
        activity = _finite_ratio(0.65 * f + 0.35 * i, "activity")
        quality = 1.0 if c is None else 0.25 + 0.75 * c
        rank = _finite_ratio(r * activity * quality, "rank")
        return SemanticScore(
            rank=rank,
            activity=activity,
            freshness=f,
            importance=i,
            confidence=c,
        )

    @classmethod
    def can_logically_forget(
        cls,
        *,
        freshness: float,
        importance: float,
        archived_days: float,
        dependency_safe: bool,
    ) -> bool:
        """Check the complete v2 logical-forgetting predicate."""

        return (
            _finite_ratio(freshness, "freshness") <= cls.forget_freshness_threshold
            and _finite_ratio(importance, "importance") <= 0.10
            and float(archived_days) >= 90.0
            and bool(dependency_safe)
        )


def _as_utc(value: _Timestamp) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("timestamp must not be blank")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            # Episode contracts permit date-only or year-only precision.  Use
            # the start of that known interval for policy calculations; the
            # occurrence precision remains on the source record.
            if text.isdigit() and len(text) == 4:
                parsed = datetime(int(text), 1, 1)
            else:
                raise ValueError(f"invalid ISO timestamp: {value!r}") from exc
    else:
        raise TypeError("timestamp must be datetime or ISO string")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _event_sort_key(event: ImportanceEvent) -> Tuple[datetime, str]:
    return _as_utc(event.occurred_at), event.event_id


def _finite_ratio(value: float, name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    return min(1.0, max(0.0, numeric))


def _positive_finite(value: float, name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{name} must be finite and greater than zero")
    return numeric


def _retention_days(value: float) -> float:
    numeric = _positive_finite(value, "retention_days")
    if numeric > MAX_RETENTION_DAYS:
        raise ValueError("retention_days exceeds the v2 maximum")
    return numeric


__all__ = [
    "EvidenceContribution",
    "EvidenceStance",
    "ImportanceAggregate",
    "ImportanceDirection",
    "ImportanceEvent",
    "MAX_FUTURE_SKEW_SECONDS",
    "MemoryScorePolicy",
    "RetentionUpdate",
    "SemanticScore",
]
