"""Resident restoration, persistence, and Runtime actor projection."""

from __future__ import annotations

from collections.abc import Mapping

from app.orchestration.nest_session.models import ActorDescriptor
from app.orchestration.nest_session.ports import NestStateStorePort
from elfie.public import AppearanceResolver, Elfie, ElfieProfile
from nest.public import Nest, NestSnapshot


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


def restore_snapshot(nest: Nest, snapshot: NestSnapshot) -> None:
    nest.restore_snapshot(snapshot)


def persist_resident(
    nest: Nest,
    state_store: NestStateStorePort | None,
    elfie_id: str,
) -> None:
    if state_store is None:
        return
    _ = elfie_id
    state_store.save_snapshot(nest.export_snapshot())


__all__ = ["actor_catalog", "persist_resident", "restore_snapshot"]
