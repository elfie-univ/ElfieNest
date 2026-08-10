"""Elfie construction Adapter used by Resident Admission."""

from __future__ import annotations

from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie import Elfie, ElfieFactory


class ElfieFactoryAdapter:
    def __init__(self, factory: ElfieFactory, godot_api: object | None) -> None:
        self._factory = factory
        self._godot_api = godot_api

    def restore(self, elfie_id: str, workspace: str) -> Elfie:
        try:
            return self._factory.restore(
                workspace,
                elfie_id=elfie_id,
                godot_api=self._godot_api,
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            raise ResidentAdmissionPortError(
                "unable to construct final Elfie"
            ) from error


__all__ = ("ElfieFactoryAdapter",)
