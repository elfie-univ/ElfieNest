"""Translate temporary Lab actors into the established Godot v2 actor command."""

from __future__ import annotations

from collections.abc import Iterable

from devtools.nest_lab.event_log import LabEventLog
from devtools.nest_lab.models import LabActor
from nest import Nest
from nest.godot.api import GodotAPIServer
from nest.godot.messages import CommandName


def sync_actors(
    gateway: GodotAPIServer,
    nest: Nest,
    events: LabEventLog,
    actors: Iterable[LabActor],
    *,
    world_revision: int,
) -> bool:
    """Send one complete actor catalog; return false while homes are unresolved."""
    descriptors = []
    for actor in actors:
        home_anchor_id = nest.home_anchor_id(actor.actor_id)
        if home_anchor_id is None:
            return False
        descriptors.append(
            {
                "actor_id": actor.actor_id,
                "species": actor.species,
                "home_anchor_id": home_anchor_id,
                "appearance": {},
            }
        )
    message_id = gateway.send_runtime_command(
        CommandName.SYNC_ACTORS,
        {"actors": descriptors},
        world_revision=world_revision,
    )
    if message_id is not None:
        events.append("sync_actors", f"count={len(descriptors)}")
        return True
    return False
