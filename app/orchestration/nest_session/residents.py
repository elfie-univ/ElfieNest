"""Resident restoration, persistence, and Runtime actor projection."""

from __future__ import annotations

from collections.abc import Mapping

from app.orchestration.nest_session.models import ActorDescriptor
from elfie.public import AppearanceResolver, Elfie, ElfieProfile
from nest.public import (
    Nest,
    NestPersistenceSnapshot,
    NestRepository,
    PersistentResidentState,
    ResidentPresence,
)


def actor_catalog(elfies: Mapping[str, Elfie]) -> tuple[ActorDescriptor, ...]:
    descriptors: list[ActorDescriptor] = []
    for elfie_id, elfie in sorted(elfies.items()):
        profile = getattr(elfie, "character_profile", None)
        if isinstance(profile, ElfieProfile):
            resolved = AppearanceResolver().resolve(profile)
            descriptors.append(
                ActorDescriptor(
                    actor_id=elfie_id,
                    species=profile.identity.species_id,
                    appearance=resolved.to_payload(),
                )
            )
        else:
            descriptors.append(
                ActorDescriptor(actor_id=elfie_id, species="fox", appearance={})
            )
    return tuple(descriptors)


def restore_snapshot(nest: Nest, snapshot: NestPersistenceSnapshot) -> None:
    nest.state.elapsed_seconds = snapshot.elapsed_seconds
    nest.state.clock_paused = snapshot.clock_paused
    nest.state.time_scale = snapshot.time_scale
    nest.state.environment_desired = snapshot.environment_desired
    nest.state.environment_rules = snapshot.environment_rules
    if snapshot.catalog is not None:
        nest.apply_catalog(snapshot.catalog)
    for resident in snapshot.residents:
        nest.register_resident(resident.elfie_id)
        if resident.home_anchor_id is not None and resident.home_zone_id is not None:
            nest.assign_home(resident.elfie_id, resident.home_anchor_id)


def persist_resident(
    nest: Nest,
    repository: NestRepository | None,
    elfie_id: str,
) -> None:
    if repository is None:
        return
    assignment = nest.state.home_assignments.get(elfie_id)
    repository.save_resident(
        PersistentResidentState(
            elfie_id=elfie_id,
            presence=(
                ResidentPresence.ACTIVE
                if assignment is not None
                else ResidentPresence.PENDING_RUNTIME
            ),
            home_zone_id=assignment.home_zone_id if assignment is not None else None,
            home_anchor_id=(
                assignment.home_anchor_id if assignment is not None else None
            ),
        )
    )


__all__ = ["actor_catalog", "persist_resident", "restore_snapshot"]
