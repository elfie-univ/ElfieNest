from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorldAction:
    target_furniture: str
    posture: str
    animation: str


def map_action_to_world(action: str) -> WorldAction | None:
    action_lower = action.lower()
    if "sleep" in action_lower or "bed" in action_lower:
        return WorldAction(
            target_furniture="bed_1",
            posture="lying",
            animation="sleep_loop",
        )
    if (
        "sit" in action_lower
        or "chair" in action_lower
        or "chat" in action_lower
    ):
        return WorldAction(
            target_furniture="chair_1",
            posture="sitting",
            animation="chat_look",
        )
    if (
        "door" in action_lower
        or "away" in action_lower
        or "leave" in action_lower
    ):
        return WorldAction(
            target_furniture="wormhole_door",
            posture="away",
            animation="walk_loop",
        )
    return None
