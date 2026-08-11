"""Elfie construction Adapter used by Resident Admission."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie import Elfie, ElfieFactory
from elfie.body.port import BodyPort
from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.factory import ElfieAssembly
from elfie.profile import ProfileStorePort

BodyFactory = Callable[[str, str], Optional[BodyPort]]
ProfileStoreFactory = Callable[[str], ProfileStorePort]
MemoryStoreFactory = Callable[[str], MemoryStorePort]


class ElfieFactoryAdapter:
    def __init__(
        self,
        factory: ElfieFactory,
        body_factory: BodyFactory,
        profile_store_factory: ProfileStoreFactory,
        memory_store_factory: MemoryStoreFactory,
    ) -> None:
        self._factory = factory
        self._body_factory = body_factory
        self._profile_store_factory = profile_store_factory
        self._memory_store_factory = memory_store_factory

    def restore(self, elfie_id: str, workspace: str) -> Elfie:
        try:
            profile_store = self._profile_store_factory(workspace)
            return self._factory.restore(
                ElfieAssembly(
                    profile=profile_store.load(),
                    memory_store=self._memory_store_factory(workspace),
                    body=self._body_factory(elfie_id, workspace),
                )
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            raise ResidentAdmissionPortError(
                "unable to construct final Elfie"
            ) from error


__all__ = (
    "BodyFactory",
    "ElfieFactoryAdapter",
    "MemoryStoreFactory",
    "ProfileStoreFactory",
)
