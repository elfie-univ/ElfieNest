"""Elfie construction Adapter used by Resident Admission."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Optional

from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie import Elfie, ElfieFactory
from elfie.body.port import BodyPort
from elfie.brain.activity.system import ActivityStorePort
from elfie.brain.journal import BrainJournalPort
from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.brain.reasoning.model_header import ReasoningConstitution
from elfie.factory import ElfieAssembly
from elfie.profile import ProfileStorePort

BodyFactory = Callable[[str, str], Optional[BodyPort]]
ProfileStoreFactory = Callable[[str], ProfileStorePort]
MemoryStoreFactory = Callable[[str], MemoryStorePort]
ActivityStoreFactory = Callable[[str], ActivityStorePort]
BrainJournalFactory = Callable[[str], BrainJournalPort]
BrainSeedFactory = Callable[[str], Mapping[str, object]]


class ElfieFactoryAdapter:
    def __init__(
        self,
        factory: ElfieFactory,
        body_factory: BodyFactory,
        profile_store_factory: ProfileStoreFactory,
        memory_store_factory: MemoryStoreFactory,
        activity_store_factory: ActivityStoreFactory | None = None,
        journal_store_factory: BrainJournalFactory | None = None,
        selfhood_seed_factory: BrainSeedFactory | None = None,
        energy_limits_factory: BrainSeedFactory | None = None,
        emotion_expression_config: Mapping[str, object] | None = None,
        emotion_dynamics_config: Mapping[str, object] | None = None,
        reasoning_constitution: ReasoningConstitution | None = None,
    ) -> None:
        self._factory = factory
        self._body_factory = body_factory
        self._profile_store_factory = profile_store_factory
        self._memory_store_factory = memory_store_factory
        self._activity_store_factory = activity_store_factory
        self._journal_store_factory = journal_store_factory
        self._selfhood_seed_factory = selfhood_seed_factory
        self._energy_limits_factory = energy_limits_factory
        self._emotion_expression_config = emotion_expression_config
        self._emotion_dynamics_config = emotion_dynamics_config
        self._reasoning_constitution = reasoning_constitution

    def restore(self, elfie_id: str, workspace: str) -> Elfie:
        try:
            profile_store = self._profile_store_factory(workspace)
            return self._factory.restore(
                ElfieAssembly(
                    profile=profile_store.load(),
                    selfhood_seed=(
                        None
                        if self._selfhood_seed_factory is None
                        else self._selfhood_seed_factory(workspace)
                    ),
                    reasoning_constitution=self._reasoning_constitution,
                    energy_limits=(
                        None
                        if self._energy_limits_factory is None
                        else self._energy_limits_factory(workspace)
                    ),
                    emotion_expression_config=self._emotion_expression_config,
                    emotion_dynamics_config=self._emotion_dynamics_config,
                    memory_store=self._memory_store_factory(workspace),
                    activity_store=(
                        None
                        if self._activity_store_factory is None
                        else self._activity_store_factory(workspace)
                    ),
                    journal_store=(
                        None
                        if self._journal_store_factory is None
                        else self._journal_store_factory(workspace)
                    ),
                    body=self._body_factory(elfie_id, workspace),
                )
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            raise ResidentAdmissionPortError(
                "unable to construct final Elfie"
            ) from error


__all__ = (
    "BodyFactory",
    "ActivityStoreFactory",
    "BrainJournalFactory",
    "BrainSeedFactory",
    "ElfieFactoryAdapter",
    "MemoryStoreFactory",
    "ProfileStoreFactory",
)
