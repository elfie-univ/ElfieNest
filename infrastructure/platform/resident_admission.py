"""Elfie construction Adapter used by Resident Admission."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie import Elfie, ElfieFactory
from elfie.body.port import BodyPort
from elfie.profile import ProfileStorePort

BodyFactory = Callable[[str, str], Optional[BodyPort]]
ProfileStoreFactory = Callable[[str], ProfileStorePort]


class ElfieFactoryAdapter:
    def __init__(
        self,
        factory: ElfieFactory,
        body_factory: BodyFactory,
        profile_store_factory: ProfileStoreFactory,
    ) -> None:
        self._factory = factory
        self._body_factory = body_factory
        self._profile_store_factory = profile_store_factory

    def restore(self, elfie_id: str, workspace: str) -> Elfie:
        try:
            return self._factory.restore(
                workspace,
                elfie_id=elfie_id,
                body=self._body_factory(elfie_id, workspace),
                profile_store=self._profile_store_factory(workspace),
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            raise ResidentAdmissionPortError(
                "unable to construct final Elfie"
            ) from error


__all__ = ("BodyFactory", "ElfieFactoryAdapter", "ProfileStoreFactory")
