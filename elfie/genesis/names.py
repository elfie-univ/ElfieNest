"""Allocate configured private names once for a whole Genesis person graph."""

import random
from typing import Callable, Dict, Iterable, Tuple

from elfie.genesis.world import GenesisSourcePackage


def allocate_person_names(
    source: GenesisSourcePackage,
    seed: int,
    persons: Iterable[Tuple[str, str]],
    reserved_names: Iterable[str] = (),
    *,
    seed_for: Callable[[int, str], int],
) -> Dict[str, str]:
    """Assign unique lexical names without suffixes or unconfigured fallbacks.

    Repeated references to one ID share a name. Allocation depends on the stable
    person IDs rather than traversal order, and uses the caller's registered
    Genesis naming domain. A pool shortage is a source error, never a reason to
    manufacture a new name.
    """
    aliases = {"Saevi": "saevi", "Tovren": "tovren", "Myelle": "myelle"}
    identities: Dict[str, str] = {}
    for person_id, species_id in persons:
        canonical_species = aliases.get(species_id, species_id)
        if not person_id:
            raise ValueError("人物姓名分配需要稳定人物 ID")
        if person_id in identities and identities[person_id] != canonical_species:
            raise ValueError(f"同一人物的物种不一致: {person_id}")
        identities[person_id] = canonical_species

    used = set(reserved_names)
    result: Dict[str, str] = {}
    for person_id, species_id in sorted(identities.items()):
        configured = (
            source.name_rules.pool(species_id) + source.name_rules.default_names
        )
        candidates = list(dict.fromkeys(name for name in configured if name))
        random.Random(seed_for(seed, f"names:person:{person_id}")).shuffle(candidates)
        available = next((name for name in candidates if name not in used), None)
        if available is None:
            raise ValueError(f"已配置姓名词库不足: {species_id} / {person_id}")
        result[person_id] = available
        used.add(available)
    return result
