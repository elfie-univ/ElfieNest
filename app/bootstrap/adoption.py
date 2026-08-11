"""Production assembly for Adoption and accepted-resident admission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.features.adoption import (
    AcceptedAdoptionReservation,
    AdoptionReservationRecord,
    AdoptionService,
)
from app.features.configuration.settings import SettingsStorePort
from app.orchestration.nest_session import NestSession
from app.orchestration.resident_admission import ResidentAdmissionService
from elfie import ElfieFactory
from infrastructure.persistence.account_repository import AccountRepository
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.adoption_profiles import FinalElfieWorkspaceAdapter
from infrastructure.persistence.elfies import SQLiteElfiesProjectionAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter
from infrastructure.persistence.store import get_db
from infrastructure.platform import (
    ElfieFactoryAdapter,
    SettingsAdoptionPolicyAdapter,
)


@dataclass(frozen=True)
class AdoptionServices:
    adoption: AdoptionService
    resident_admission: ResidentAdmissionService


def seed_single_elfie(db_path: str) -> bool:
    """Create the existing development seed through Bootstrap-owned Adapters."""
    if SQLiteElfiesProjectionAdapter(db_path).list_directory():
        return False
    with get_db(db_path) as connection:
        owner = AccountRepository(connection).find_owner()
    if owner is None:
        return False

    persistence = SQLiteAdoptionAdapter(db_path)
    elfie_id = "00000001"
    birth_date = datetime.now(timezone.utc).date().isoformat()
    persistence.reserve(
        AdoptionReservationRecord(
            elfie_id=elfie_id,
            owner_user_id=owner.user_id,
            name="Aifei",
            species_id="fox",
            gender="female",
            birth_date=birth_date,
            summary="好奇探索",
        ),
        default_limit=1,
    )
    try:
        FinalElfieWorkspaceAdapter.from_database_path(db_path).materialize(
            AcceptedAdoptionReservation(
                elfie_id=elfie_id,
                owner_user_id=owner.user_id,
                name="Aifei",
                species_id="fox",
                personality_style="好奇探索",
                height="tall",
                build="plump",
                appearance_seed=uuid4().int & ((1 << 63) - 1),
                face="any",
                signature="any",
                gender="female",
                birth_date=birth_date,
            )
        )
    except Exception:
        persistence.release(elfie_id)
        raise
    return True


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
                lambda workspace: YamlProfileStoreAdapter(Path(workspace) / "profile"),
            ),
            nest_session,
        ),
    )


__all__ = ("AdoptionServices", "build_adoption_services", "seed_single_elfie")
