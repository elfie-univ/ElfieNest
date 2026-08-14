"""Semantic home assignment for the Lab's disposable actors."""

from __future__ import annotations

from collections.abc import Iterable

from devtools.nest_lab.models import NestLabConflictError
from nest import Nest
from nest.living_rules.errors import NoHomeAvailableError


def assign_missing_homes(nest: Nest, actor_ids: Iterable[str]) -> None:
    """Assign available semantic beds after the Runtime publishes a catalog."""
    if nest.world_catalog is None:
        return
    for actor_id in actor_ids:
        if nest.home_anchor_id(actor_id) is None:
            try:
                nest.admit_resident(actor_id)
            except NoHomeAvailableError as error:
                raise NestLabConflictError("当前房间没有可用床位") from error


def clear_home_assignments(nest: Nest, actor_ids: Iterable[str]) -> None:
    """Release homes before the fixed room receives a new revision."""
    for actor_id in actor_ids:
        if nest.home_anchor_id(actor_id) is not None:
            nest.release_home(actor_id)
