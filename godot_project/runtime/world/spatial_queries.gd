class_name NestSpatialQueries
extends RefCounted

## Coordinate queries owned by the Godot world; callers receive semantic IDs only.
const VISUAL_MAX_RANGE: float = 18.0
const VISUAL_FOV_DEGREES: float = 120.0
const VISUAL_EYE_HEIGHT: float = 0.9
const ACTOR_TARGET_HEIGHT: float = 1.25
const SPEECH_RANGE_BY_PROFILE := {
	"quiet": 4.0,
	"normal": 10.0,
	"loud": 18.0,
}


static func nearest_zone_id(
	anchor_markers: Dictionary,
	world_position: Vector3,
) -> String:
	var nearest_zone_id := ""
	var nearest_distance := INF
	for marker_value: Variant in anchor_markers.values():
		if not marker_value is Marker3D:
			continue
		var marker := marker_value as Marker3D
		var distance := marker.global_position.distance_squared_to(world_position)
		if distance < nearest_distance:
			nearest_distance = distance
			nearest_zone_id = String(marker.get_meta("zone_id", ""))
	return nearest_zone_id


static func speech_range(acoustic_profile: String) -> float:
	return float(SPEECH_RANGE_BY_PROFILE.get(acoustic_profile, 0.0))


static func within_visual_cone(
	observer: Node3D,
	target_position: Vector3,
	max_range: float = VISUAL_MAX_RANGE,
) -> bool:
	var offset := target_position - observer.global_position
	offset.y = 0.0
	var distance_squared := offset.length_squared()
	if distance_squared <= 0.0001 or distance_squared > max_range * max_range:
		return false
	var direction := offset.normalized()
	var forward := observer.global_transform.basis.z
	forward.y = 0.0
	if forward.is_zero_approx():
		return false
	return forward.normalized().dot(direction) >= cos(deg_to_rad(VISUAL_FOV_DEGREES / 2.0))


static func has_line_of_sight(
	world: World3D,
	from_position: Vector3,
	to_position: Vector3,
	target: Node3D = null,
	excluded: Array[RID] = [],
) -> bool:
	var query := PhysicsRayQueryParameters3D.create(from_position, to_position)
	query.exclude = excluded
	query.collide_with_areas = true
	query.collide_with_bodies = true
	var hit := world.direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return true
	if target == null:
		return false
	return hit.get("collider") == target
