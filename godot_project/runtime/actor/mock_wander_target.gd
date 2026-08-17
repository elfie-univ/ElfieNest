class_name MockWanderTarget
extends RefCounted

## Deterministic, room-local floor targets shared by Authority and Observer.
## The waypoint index is semantic state; coordinates stay inside Godot.
const WAYPOINT_OFFSETS := [
	Vector3(1.25, 0.0, 0.0),
	Vector3(-1.15, 0.0, 0.85),
	Vector3(0.85, 0.0, -1.15),
	Vector3(-0.85, 0.0, -0.95),
	Vector3(1.0, 0.0, 1.05),
	Vector3(-0.95, 0.0, 0.15),
]
const MIN_TARGET_DISTANCE := 0.45


static func target_for(nest: ModularNest, actor: ElfieActor, waypoint: int) -> Variant:
	var anchor_id := String(actor.get_meta("home_anchor_id", ""))
	if anchor_id.is_empty():
		anchor_id = String(actor.get_meta("spawn_anchor_id", ""))
	var anchor := nest.resolve_anchor(anchor_id)
	if anchor == null:
		return null
	var home_zone_id := String(anchor.get_meta("zone_id", ""))
	if home_zone_id.is_empty() or actor.get_world_3d() == null:
		return null
	var navigation_map := actor.get_world_3d().navigation_map
	if NavigationServer3D.map_get_iteration_id(navigation_map) == 0:
		return null
	var offset_start: int = posmod(waypoint, WAYPOINT_OFFSETS.size())
	for attempt in range(WAYPOINT_OFFSETS.size()):
		var offset: Vector3 = WAYPOINT_OFFSETS[
			(offset_start + attempt) % WAYPOINT_OFFSETS.size()
		]
		var candidate := NavigationServer3D.map_get_closest_point(
			navigation_map,
			anchor.global_position + offset,
		)
		if candidate.distance_to(anchor.global_position) < MIN_TARGET_DISTANCE:
			continue
		if nest.nearest_zone_id(candidate) != home_zone_id:
			continue
		return candidate
	return null


static func motion_payload(waypoint: int, sequence: int) -> Dictionary:
	return {
		"waypoint": waypoint,
		"sequence": sequence,
	}
