"""Production assembly for Adoption and accepted-resident admission."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.adoption import AdoptionService
from app.features.configuration.settings import SettingsStorePort
from app.orchestration.nest_session import NestSession
from app.orchestration.resident_admission import ResidentAdmissionService
from elfie import ElfieFactory
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.adoption_profiles import FinalElfieWorkspaceAdapter
from infrastructure.platform import (
    ElfieFactoryAdapter,
    SettingsAdoptionPolicyAdapter,
)


@dataclass(frozen=True)
class AdoptionServices:
    adoption: AdoptionService
    resident_admission: ResidentAdmissionService


def build_adoption_services(
    db_path: str,
    *,
    settings: SettingsStorePort,
    nest_session: NestSession | None,
) -> AdoptionServices:
    adoption = AdoptionService(
        SettingsAdoptionPolicyAdapter(settings),
        SQLiteAdoptionAdapter(db_path),
    )
    return AdoptionServices(
        adoption=adoption,
        resident_admission=ResidentAdmissionService(
            adoption,
            FinalElfieWorkspaceAdapter.from_database_path(db_path),
            ElfieFactoryAdapter(
                ElfieFactory(),
                None if nest_session is None else nest_session.world_runtime,
            ),
            nest_session,
        ),
    )


__all__ = ("AdoptionServices", "build_adoption_services")
