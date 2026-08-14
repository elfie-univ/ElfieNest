"""精灵巢状态模型。"""

from nest.state.config import NestConfig
from nest.state.models import (
    AnchorKind,
    HomeAssignment,
    InteractionAnchor,
    PersistentResidentState,
    ResidentPresence,
    ResidentState,
    RuntimeResidentMirror,
    WorldCatalog,
    ZoneDescriptor,
)
from nest.state.repository import (
    NestPersistenceError,
    NestPersistenceSnapshot,
    NestRepository,
)

_STORE_EXPORTS = {
    "BedConflictError",
    "NestState",
    "NoHomeAvailableError",
    "ReconciliationRequiredError",
    "UnknownAnchorError",
    "UnknownResidentError",
}


def __getattr__(name: str):
    """Load the state shell lazily so owner modules remain acyclic."""
    if name in _STORE_EXPORTS:
        from nest.state import store

        return getattr(store, name)
    raise AttributeError(name)


__all__ = [
    "AnchorKind",
    "BedConflictError",
    "HomeAssignment",
    "InteractionAnchor",
    "NestConfig",
    "NestState",
    "NestPersistenceError",
    "NestPersistenceSnapshot",
    "NestRepository",
    "NoHomeAvailableError",
    "ReconciliationRequiredError",
    "PersistentResidentState",
    "ResidentPresence",
    "ResidentState",
    "RuntimeResidentMirror",
    "UnknownAnchorError",
    "UnknownResidentError",
    "WorldCatalog",
    "ZoneDescriptor",
]
