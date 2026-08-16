"""Brain-owned mutable self-model anchored by one immutable Profile."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable, Optional

from elfie.brain.selfhood.contracts import (
    BigFiveTraits,
    SelfhoodDerivation,
    SelfhoodSnapshot,
    SelfhoodSpeechStyle,
)
from elfie.brain.state_lifecycle import (
    StateCandidate,
    StateCheckpoint,
    StateCommitReceipt,
    StateCommitStatus,
    StateRestoreError,
    VersionedState,
    VersionedStateStore,
)
from elfie.message_types import EventId, UTCDateTime

_BIG_FIVE_KEYS = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)
_MAX_TRAIT_DELTA_PER_COMMIT = 0.05
_MIN_SLOW_CHANGE_SOURCES = 3


class SelfhoodSystem:
    """Own the slow-changing self-model; Profile remains read-only input."""

    def __init__(
        self,
        *,
        initial_at: UTCDateTime,
        profile_revision: int = 1,
        initial: SelfhoodSnapshot | None = None,
    ) -> None:
        if profile_revision < 1:
            raise ValueError("profile_revision must be positive")
        snapshot = initial or SelfhoodSnapshot(
            revision=0,
            captured_at=initial_at,
            profile_revision=profile_revision,
            big_five=BigFiveTraits(),
        )
        if snapshot.profile_revision != profile_revision:
            raise ValueError(
                "Selfhood snapshot is anchored to another Profile revision"
            )
        self._profile_revision = profile_revision
        self._store = VersionedStateStore(
            VersionedState(
                revision=snapshot.revision,
                committed_at=snapshot.captured_at,
                source_event_ids=snapshot.source_event_ids,
                causation_id=None,
                value=snapshot,
            )
        )

    @classmethod
    def from_personality_data(
        cls,
        personality_data: Mapping[str, Any] | None,
        *,
        initial_at: UTCDateTime,
        profile_revision: int = 1,
    ) -> SelfhoodSystem:
        """Create the initial Brain seed without retaining Profile ownership."""
        data = dict(personality_data) if isinstance(personality_data, Mapping) else {}
        big_five_data = data.get("big_five")
        big_five = _big_five(
            big_five_data if isinstance(big_five_data, Mapping) else {}
        )
        metadata = data.get("metadata")
        metadata_map = metadata if isinstance(metadata, Mapping) else {}
        description = _optional_text(
            data.get("self_description") or metadata_map.get("description")
        )
        species_name = _optional_text(data.get("species_name"))
        speech_style_data = data.get("speech_style")
        speech_style_map = (
            speech_style_data if isinstance(speech_style_data, Mapping) else {}
        )
        greetings = _text_tuple(speech_style_map.get("greetings"))
        verbal_tick = _optional_text(
            speech_style_map.get("verbal_tick") or speech_style_map.get("verbal_ticks")
        )
        unknown_fields = []
        if not isinstance(big_five_data, Mapping):
            unknown_fields.append("personality.big_five")
        if description is None:
            unknown_fields.append("self_description")
        if species_name is None:
            unknown_fields.append("species_name")
        if not greetings and verbal_tick is None:
            unknown_fields.append("speech_style")
        identity_facts = _text_tuple(data.get("identity_facts"))
        behavior_anchors = _text_tuple(data.get("behavior_anchors"))
        sensory_biases = _text_tuple(data.get("sensory_biases"))
        species_knowledge = _text_tuple(data.get("species_knowledge"))
        knowledge_boundaries = _text_tuple(data.get("knowledge_boundaries"))
        norms = _text_tuple(data.get("norms"))
        if not identity_facts:
            unknown_fields.append("identity_facts")
        if not behavior_anchors:
            unknown_fields.append("behavior_anchors")
        if not sensory_biases:
            unknown_fields.append("sensory_biases")
        if not species_knowledge:
            unknown_fields.append("species_knowledge")
        if not knowledge_boundaries:
            unknown_fields.append("knowledge_boundaries")
        if not norms:
            unknown_fields.append("norms")
        derivation_data = data.get("derivation")
        derivation_map = derivation_data if isinstance(derivation_data, Mapping) else {}
        snapshot = SelfhoodSnapshot(
            revision=0,
            captured_at=initial_at,
            profile_revision=profile_revision,
            big_five=big_five,
            self_description=description,
            species_name=species_name,
            speech_style=SelfhoodSpeechStyle(
                greetings=greetings,
                verbal_tick=verbal_tick,
            ),
            derivation=SelfhoodDerivation(
                preset=_optional_text(derivation_map.get("preset")),
                matched_keywords=_text_tuple(derivation_map.get("matched_keywords")),
                provenance=_optional_text(derivation_map.get("provenance")),
                overridden_traits=_text_tuple(derivation_map.get("overridden_traits")),
                seed=(
                    int(derivation_map["seed"])
                    if isinstance(derivation_map.get("seed"), int)
                    and not isinstance(derivation_map.get("seed"), bool)
                    else None
                ),
            ),
            norms=norms,
            unknown_fields=tuple(unknown_fields),
            identity_facts=identity_facts,
            behavior_anchors=behavior_anchors,
            sensory_biases=sensory_biases,
            species_knowledge=species_knowledge,
            knowledge_boundaries=knowledge_boundaries,
            freshness="current" if data else "unknown",
        )
        return cls(
            initial_at=initial_at,
            profile_revision=profile_revision,
            initial=snapshot,
        )

    def snapshot(self) -> SelfhoodSnapshot:
        """Return the latest committed self-model."""
        return self._store.snapshot().value

    def checkpoint(self) -> StateCheckpoint[SelfhoodSnapshot]:
        """Return a persistence-neutral checkpoint."""
        return self._store.checkpoint()

    def restore(self, checkpoint: StateCheckpoint[SelfhoodSnapshot]) -> None:
        """Restore only a checkpoint anchored to this immutable Profile."""
        self.validate_checkpoint(checkpoint)
        self._store.restore(checkpoint)

    def validate_checkpoint(
        self, checkpoint: StateCheckpoint[SelfhoodSnapshot]
    ) -> None:
        """Reject foreign-Profile and backwards Selfhood checkpoints."""
        if checkpoint.value.profile_revision != self._profile_revision:
            raise ValueError("Selfhood checkpoint belongs to another Profile revision")
        if checkpoint.revision < self._store.snapshot().revision:
            raise StateRestoreError("selfhood checkpoint revision is older")

    def propose_update(
        self,
        *,
        candidate_id: EventId,
        created_at: UTCDateTime,
        big_five: BigFiveTraits | None = None,
        self_description: Optional[str] = None,
        speech_style: SelfhoodSpeechStyle | None = None,
        norms: tuple[str, ...] | None = None,
        source_event_ids: tuple[EventId, ...] = (),
        causation_id: EventId | None = None,
    ) -> StateCandidate[SelfhoodSnapshot]:
        """Build an explicit, reviewable Selfhood update candidate.

        A normal input Turn never calls this method implicitly. Callers that do
        use it must provide a stable candidate identity and commit through the
        same owner guard as every other Brain state.
        """
        current = self._store.snapshot()
        value = current.value.model_copy(
            update={
                "revision": current.revision + 1,
                "captured_at": created_at,
                "big_five": big_five or current.value.big_five,
                "self_description": (
                    current.value.self_description
                    if self_description is None
                    else self_description
                ),
                "speech_style": speech_style or current.value.speech_style,
                "norms": current.value.norms if norms is None else norms,
                "source_event_ids": _unique_event_ids(source_event_ids),
                "unknown_fields": (),
                "freshness": "current",
            }
        )
        return StateCandidate(
            candidate_id=candidate_id,
            owner="selfhood",
            base_revision=current.revision,
            source_event_ids=value.source_event_ids,
            causation_id=causation_id,
            created_at=created_at,
            value=value,
        )

    def validate(
        self, candidate: StateCandidate[SelfhoodSnapshot]
    ) -> StateCommitReceipt:
        """Validate without mutating the current Selfhood."""
        if candidate.owner != "selfhood":
            return StateCommitReceipt(
                candidate_id=candidate.candidate_id,
                status=StateCommitStatus.REJECTED,
                revision=self._store.snapshot().revision,
                reason="candidate_owner_mismatch",
            )
        return self._store.validate(candidate, validator=self._validate_value)

    def commit(
        self,
        candidate: StateCandidate[SelfhoodSnapshot],
    ) -> StateCommitReceipt:
        """Validate and commit one explicit Selfhood update."""
        if candidate.owner != "selfhood":
            return StateCommitReceipt(
                candidate_id=candidate.candidate_id,
                status=StateCommitStatus.REJECTED,
                revision=self._store.snapshot().revision,
                reason="candidate_owner_mismatch",
            )
        return self._store.commit(candidate, validator=self._validate_value)

    def big_five_dict(self) -> dict[str, float]:
        """Return a narrow legacy-shaped projection for existing algorithms."""
        return self.snapshot().big_five.model_dump()

    def seed_data(self, *, display_name: str | None = None) -> dict[str, Any]:
        """Return initialization data for existing Memory core generators."""
        snapshot = self.snapshot()
        return {
            "big_five": snapshot.big_five.model_dump(),
            "metadata": {
                "name": display_name or "Elfie",
                "description": snapshot.self_description or "",
            },
            "self_description": snapshot.self_description,
            "species_name": snapshot.species_name,
            "speech_style": {
                "greetings": list(snapshot.speech_style.greetings),
                "verbal_ticks": snapshot.speech_style.verbal_tick,
            },
            "derivation": snapshot.derivation.model_dump(),
            "norms": list(snapshot.norms),
            "identity_facts": list(snapshot.identity_facts),
            "behavior_anchors": list(snapshot.behavior_anchors),
            "sensory_biases": list(snapshot.sensory_biases),
            "species_knowledge": list(snapshot.species_knowledge),
            "knowledge_boundaries": list(snapshot.knowledge_boundaries),
        }

    def _validate_value(
        self,
        current: SelfhoodSnapshot,
        candidate: SelfhoodSnapshot,
    ) -> str | None:
        if candidate.profile_revision != self._profile_revision:
            return "profile_revision_mismatch"
        if candidate.revision <= current.revision:
            return "selfhood_revision_not_advanced"
        if any(
            (
                candidate.species_name != current.species_name,
                candidate.identity_facts != current.identity_facts,
                candidate.behavior_anchors != current.behavior_anchors,
                candidate.sensory_biases != current.sensory_biases,
                candidate.species_knowledge != current.species_knowledge,
                candidate.knowledge_boundaries != current.knowledge_boundaries,
            )
        ):
            return "selfhood_identity_anchors_immutable"
        changed_traits = tuple(
            key
            for key in _BIG_FIVE_KEYS
            if getattr(candidate.big_five, key) != getattr(current.big_five, key)
        )
        identity_changed = any(
            (
                changed_traits,
                candidate.self_description != current.self_description,
                candidate.speech_style != current.speech_style,
                candidate.norms != current.norms,
            )
        )
        if not identity_changed:
            return "selfhood_update_has_no_change"
        if len(candidate.source_event_ids) < _MIN_SLOW_CHANGE_SOURCES:
            return "selfhood_requires_multiple_sources"
        if any(
            abs(getattr(candidate.big_five, key) - getattr(current.big_five, key))
            > _MAX_TRAIT_DELTA_PER_COMMIT
            for key in changed_traits
        ):
            return "personality_change_exceeds_slow_limit"
        return None


def _big_five(raw: Mapping[str, Any]) -> BigFiveTraits:
    values: dict[str, float] = {}
    for key in _BIG_FIVE_KEYS:
        value = raw.get(key, 0.5)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            value = 0.5
        values[key] = max(0.0, min(1.0, float(value)))
    return BigFiveTraits(**values)


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _text_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )


def _unique_event_ids(event_ids: Iterable[EventId]) -> tuple[EventId, ...]:
    return tuple(dict.fromkeys(event_ids))


__all__ = ("SelfhoodSystem",)
