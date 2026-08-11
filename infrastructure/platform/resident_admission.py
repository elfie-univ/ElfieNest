"""Elfie construction Adapter used by Resident Admission."""

from __future__ import annotations

from collections.abc import Callable

from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie import Elfie, ElfieFactory
from elfie.profile import ProfileStorePort

ProfileStoreFactory = Callable[[str], ProfileStorePort]


class ElfieFactoryAdapter:
    def __init__(
        self,
        factory: ElfieFactory,
        godot_api: object | None,
        profile_store_factory: ProfileStoreFactory,
    ) -> None:
        self._factory = factory
        self._godot_api = godot_api
        self._profile_store_factory = profile_store_factory

    def restore(self, elfie_id: str, workspace: str) -> Elfie:
        try:
            return self._factory.restore(
                workspace,
                elfie_id=elfie_id,
                godot_api=self._godot_api,
                profile_store=self._profile_store_factory(workspace),
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            raise ResidentAdmissionPortError(
                "unable to construct final Elfie"
            ) from error


__all__ = ("ElfieFactoryAdapter", "ProfileStoreFactory")
