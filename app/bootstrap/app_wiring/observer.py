"""Production assembly for the scoped Observer workflow."""

from __future__ import annotations

from app.features.accounts import AccountsService
from app.features.elfies import ElfiesService
from app.orchestration.nest_session import NestSession
from app.orchestration.observer import ObserverFacade
from infrastructure.godot.observer_world import GodotObserverWorldAdapter
from infrastructure.platform.observer_runtime import (
    SecureObserverCapabilityIssuer,
    SystemObserverClock,
)


def build_observer_facade(
    *,
    accounts: AccountsService,
    elfies: ElfiesService,
    nest_session: NestSession | None,
) -> ObserverFacade:
    """Assemble Observer over the existing Nest projection without a second fact source."""
    world = GodotObserverWorldAdapter(
        entities=(
            nest_session.observer_semantic_entities
            if nest_session is not None
            else lambda: {}
        ),
        # No production world-changing sink exists yet; preserve that current boundary.
        intent_sink=None,
    )
    return ObserverFacade(
        accounts=accounts,
        elfies=elfies,
        world=world,
        clock=SystemObserverClock(),
        capabilities=SecureObserverCapabilityIssuer(),
    )


__all__ = ("build_observer_facade",)
