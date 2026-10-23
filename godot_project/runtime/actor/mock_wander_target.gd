class_name MockWanderTarget
extends RefCounted

## Waypoints remain protocol IDs 0..5; the estate owns every physical position.
const MAX_TARGET_SNAP_DISTANCE := 1.35
const MAX_FLOOR_SNAP_DISTANCE := 0.25
const WAYPOINT_COUNT := 6


static func waypoint_count(nest: ModularNest) -> int:
	return WAYPOINT_COUNT if is_instance_valid(nest) else 0


static func is_wanderable_position(nest: ModularNest, position: Vector3) -> bool:
	if not is_instance_valid(nest) or not nest.is_inside_tree() or not position.is_finite():
		return false
	var map := nest.get_world_3d().navigation_map
	if not _map_ready(map):
		return false
	return _on_navigation_surface(map, position)


static func target_for(
	nest: ModularNest,
	actor: ElfieActor,
	waypoint: int,
	_sequence: int = 0,
) -> Variant:
	if waypoint < 0 or waypoint >= WAYPOINT_COUNT:
		return null
	var home_id := _home_anchor_id(actor)
	if home_id.is_empty() or not is_instance_valid(nest):
		return null
	var home := nest.resolve_anchor(home_id)
	if home == null or String(home.get_meta("kind", "")) != "bed":
		return null
	var zone_id := String(home.get_meta("zone_id", ""))
	if zone_id.is_empty():
		return null
	var ids := [
		home_id, zone_id + "/door", "central-01/activity", "courtyard/activity",
		"courtyard/lakeside-seat", "courtyard/picnic-seat",
	]
	return _reachable_anchor(nest, actor, String(ids[waypoint]))


static func sleep_target(nest: ModularNest, actor: ElfieActor) -> Variant:
	var anchor_id := _home_anchor_id(actor)
	if anchor_id.is_empty() or not is_instance_valid(nest):
		return null
	var anchor := nest.resolve_anchor(anchor_id)
	if anchor == null or String(anchor.get_meta("kind", "")) != "bed":
		return null
	# This schedule target is the real bed approach. Furniture posture is a
	# separate use_anchor action; do not fabricate a deck pose here.
	return _reachable_anchor(nest, actor, anchor_id)


static func _home_anchor_id(actor: ElfieActor) -> String:
	if not is_instance_valid(actor) or not actor.is_inside_tree():
		return ""
	var home_id := String(actor.get_meta("home_anchor_id", ""))
	return home_id if not home_id.is_empty() else String(actor.get_meta("spawn_anchor_id", ""))


static func _map_ready(map: RID) -> bool:
	return (
		map.is_valid() and NavigationServer3D.map_is_active(map)
		and NavigationServer3D.map_get_iteration_id(map) > 0
		and not NavigationServer3D.map_get_regions(map).is_empty()
	)


static func _on_navigation_surface(map: RID, position: Vector3) -> bool:
	if not NavigationServer3D.map_get_closest_point_owner(map, position).is_valid():
		return false
	var closest := NavigationServer3D.map_get_closest_point(map, position)
	return (
		closest.distance_to(position) <= MAX_TARGET_SNAP_DISTANCE
		and absf(closest.y - position.y) <= MAX_FLOOR_SNAP_DISTANCE
	)


static func _reachable_anchor(nest: ModularNest, actor: ElfieActor, anchor_id: String) -> Variant:
	if not is_instance_valid(actor) or not actor.is_inside_tree():
		return null
	var anchor := nest.resolve_anchor(anchor_id)
	if anchor == null:
		return null
	var navigation_map := actor.get_world_3d().navigation_map
	if navigation_map != nest.get_world_3d().navigation_map or not _map_ready(navigation_map):
		return null
	if not _on_navigation_surface(navigation_map, anchor.global_position):
		return null
	if not _on_navigation_surface(navigation_map, actor.global_position):
		return null
	var candidate := NavigationServer3D.map_get_closest_point(
		navigation_map,
		anchor.global_position,
	)
	var path := NavigationServer3D.map_get_path(
		navigation_map,
		actor.global_position,
		candidate,
		true,
	)
	if path.is_empty() or path[path.size() - 1].distance_to(candidate) > 0.05:
		return null
	if path.size() == 1 and actor.global_position.distance_to(candidate) > ElfieActor.ARRIVAL_DISTANCE:
		return null
	return candidate


static func motion_payload(waypoint: int, sequence: int) -> Dictionary:
	return {
		"waypoint": waypoint,
		"sequence": sequence,
	}


static func sleep_motion_payload(sequence: int) -> Dictionary:
	return {
		"mode": "sleep",
		"sequence": sequence,
	}
