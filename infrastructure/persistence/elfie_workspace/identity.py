"""Read final Elfie identity owners for Infrastructure projections.

The Nest database stores only operational relationships and runtime state.  A
projection that needs an Elfie's public identity must load the committed
Profile from that Elfie's final workspace through this boundary; it must not
reconstruct identity from a copied SQL row.
"""

from __future__ import annotations

from pathlib import Path

from elfie.brain.selfhood.contracts import (
    SelfhoodState,
    normalize_selfhood_mapping,
)
from elfie.profile import ElfieProfile
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.layout.data_home import data_home_from_db_path
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


def load_profile_from_db(db_path: str | Path, elfie_id: str) -> ElfieProfile:
    """Load and validate one committed Profile from its final workspace."""

    layout = final_root_layout(data_home_from_db_path(db_path)).elfie(elfie_id)
    profile = YamlProfileStoreAdapter(layout.profile.parent).load()
    profile.validate()
    if profile.identity.elfie_id != elfie_id:
        raise ValueError("Profile Elfie ID does not match the requested resident")
    return profile


def load_selfhood_from_db(db_path: str | Path, elfie_id: str) -> SelfhoodState:
    """Load one final Selfhood seed and normalize YAML sequence containers."""

    layout = final_root_layout(data_home_from_db_path(db_path)).elfie(elfie_id)
    raw = YamlSelfhoodSeedAdapter(layout.brain).load()
    state = SelfhoodState.model_validate(normalize_selfhood_mapping(raw))
    if state.identity_core.elfie_id != elfie_id:
        raise ValueError("Selfhood Elfie ID does not match the requested resident")
    return state


__all__ = ("load_profile_from_db", "load_selfhood_from_db")
