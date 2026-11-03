"""Create and reuse saved identities through the shared Elfie Lab library."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from devtools.elfie_lab.storage import ElfieLabStorage
from devtools.nest_lab.models import LabActor, LabSpecies
from elfie.profile import AppearanceResolver, get_species_definition
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


class SavedLabActors:
    """Create through Elfie Lab and project its shared experiment library."""

    def __init__(self, storage: ElfieLabStorage) -> None:
        self._storage = storage
        self._cache: dict[str, tuple[int, int, str, LabActor]] = {}

    def create(
        self,
        species: LabSpecies,
        age_years: int | None,
        gender: Literal["male", "female"] | None,
        name: str | None,
    ) -> LabActor:
        label = get_species_definition(species).display_name_zh
        spec = self._storage.create_elfie(
            name=name or f"{label} {datetime.now():%m%d-%H%M%S}",
            species_id=species,
            age_years=age_years,
            gender=gender,
        )
        return next(actor for actor in self() if actor.actor_id == spec.elfie_id)

    def __call__(self) -> tuple[LabActor, ...]:
        actors: list[LabActor] = []
        for spec in self._storage.list_elfies():
            repository = YamlProfileStoreAdapter(
                self._storage.elfie_dir(spec.elfie_id) / "profile"
            )
            stat = repository.path.stat()
            key = (stat.st_mtime_ns, stat.st_size, spec.name)
            cached = self._cache.get(spec.elfie_id)
            if cached is not None and cached[:3] == key:
                actors.append(cached[3])
                continue
            profile = repository.load()
            identity = profile.identity
            if identity.species_id not in {"saevi", "tovren"}:
                raise ValueError(f"实验精灵物种不支持: {identity.species_id}")
            if identity.gender not in {"male", "female"}:
                raise ValueError(f"实验精灵缺少性别: {spec.elfie_id}")
            age = identity.origin.age_years
            if age is None or not float(age).is_integer():
                raise ValueError(f"实验精灵缺少有效年龄: {spec.elfie_id}")
            actor = LabActor(
                actor_id=spec.elfie_id,
                species=cast(LabSpecies, identity.species_id),
                age_years=int(age),
                gender=cast(Literal["male", "female"], identity.gender),
                appearance=AppearanceResolver().resolve(profile),
                name=spec.name,
                saved=True,
            )
            self._cache[spec.elfie_id] = (*key, actor)
            actors.append(actor)
        self._cache = {actor.actor_id: self._cache[actor.actor_id] for actor in actors}
        return tuple(actors)
