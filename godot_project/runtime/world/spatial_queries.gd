class_name NestSpatialQueries
extends RefCounted

## Coordinate queries owned by the Godot world; callers receive semantic IDs only.
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
