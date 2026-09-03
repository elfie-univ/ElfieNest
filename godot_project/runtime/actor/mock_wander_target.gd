class_name MockWanderTarget
extends RefCounted

## Deterministic whole-Nest floor targets shared by Authority and Observer.
## The waypoint and sequence are semantic state; physical coordinates stay in Godot.
const D := preload("res://rooms/room_dimensions.gd")
const WANDER_AREA_COUNT := 3
const WANDER_SAMPLES_PER_AREA := 4
const WANDER_AREA_MARGIN := 0.46
const PORTAL_EXCLUSION_Z := -0.45
const MIN_TARGET_DISTANCE := 0.45
const MAX_TARGET_SNAP_DISTANCE := 1.35
const TARGET_ATTEMPTS := 8


static func waypoint_count(nest: ModularNest) -> int:
	return (
		D.room_count_for_beds(nest.bed_count)
		* WANDER_AREA_COUNT
		* WANDER_SAMPLES_PER_AREA
	)


static func is_wanderable_position(nest: ModularNest, position: Vector3) -> bool:
	var room_count := D.room_count_for_beds(nest.bed_count)
	var min_x := D.ACTIVITY_OUTER_X + WANDER_AREA_MARGIN
	var max_x := D.DORM_OUTER_X - WANDER_AREA_MARGIN
	var min_z := -float(room_count) * D.CELL_PITCH + WANDER_AREA_MARGIN
	return (
		position.x >= min_x
		and position.x <= max_x
		and position.z >= min_z
		and position.z <= PORTAL_EXCLUSION_Z
	)


static func target_for(
	nest: ModularNest,
	actor: ElfieActor,
	waypoint: int,
	sequence: int = 0,
) -> Variant:
	if actor.get_world_3d() == null:
		return null
	var room_count := D.room_count_for_beds(nest.bed_count)
	var total_waypoints := waypoint_count(nest)
	if room_count <= 0 or total_waypoints <= 0:
		return null
	var normalized_waypoint := posmod(waypoint, total_waypoints)
	var room_index := normalized_waypoint % room_count
	var area_index := (normalized_waypoint / room_count) % WANDER_AREA_COUNT
	var sample_index := (
		normalized_waypoint / (room_count * WANDER_AREA_COUNT)
	) % WANDER_SAMPLES_PER_AREA
	var navigation_map := actor.get_world_3d().navigation_map
	if NavigationServer3D.map_get_iteration_id(navigation_map) == 0:
		return null
	for attempt in range(TARGET_ATTEMPTS):
		var desired := _sample_position(
			room_index,
			area_index,
			sample_index,
			waypoint,
			sequence,
			attempt,
		)
		var candidate := NavigationServer3D.map_get_closest_point(
			navigation_map,
			desired,
		)
		if candidate.distance_to(desired) > MAX_TARGET_SNAP_DISTANCE:
			continue
		if not is_wanderable_position(nest, candidate):
			continue
		if candidate.distance_to(actor.global_position) < MIN_TARGET_DISTANCE:
			continue
		var path := NavigationServer3D.map_get_path(
			navigation_map,
			actor.global_position,
			candidate,
			true,
		)
		if path.size() < 2:
			continue
		return candidate
	return null


static func sleep_target(nest: ModularNest, actor: ElfieActor) -> Variant:
	var anchor_id := String(actor.get_meta("home_anchor_id", ""))
	if anchor_id.is_empty():
		anchor_id = String(actor.get_meta("spawn_anchor_id", ""))
	var anchor := nest.resolve_anchor(anchor_id)
	if anchor == null or String(anchor.get_meta("kind", "")) != "bed":
		return null
	var navigation_map := actor.get_world_3d().navigation_map
	if NavigationServer3D.map_get_iteration_id(navigation_map) == 0:
		return null
	var candidate := NavigationServer3D.map_get_closest_point(
		navigation_map,
		anchor.global_position,
	)
	if candidate.distance_to(anchor.global_position) > MAX_TARGET_SNAP_DISTANCE:
		return null
	var path := NavigationServer3D.map_get_path(
		navigation_map,
		actor.global_position,
		candidate,
		true,
	)
	if path.size() < 2:
		return null
	return candidate


static func _sample_position(
	room_index: int,
	area_index: int,
	sample_index: int,
	waypoint: int,
	sequence: int,
	attempt: int,
) -> Vector3:
	var room_center_z := D.cell_center_z(room_index)
	var half_cell_span := D.CELL_PITCH / 2.0 - WANDER_AREA_MARGIN
	var z_fraction := _unit_value(waypoint, sequence, attempt, 17)
	var z_position := room_center_z + lerpf(
		-half_cell_span,
		half_cell_span,
		clampf(
			(float(sample_index) + z_fraction) / float(WANDER_SAMPLES_PER_AREA),
			0.04,
			0.96,
		),
	)
	var min_x := 0.0
	var max_x := 0.0
	match area_index:
		0:
			min_x = D.ACTIVITY_OUTER_X + WANDER_AREA_MARGIN
			max_x = D.ACTIVITY_INNER_X - WANDER_AREA_MARGIN
		1:
			min_x = -D.CORRIDOR_WIDTH / 2.0 + WANDER_AREA_MARGIN
			max_x = D.CORRIDOR_WIDTH / 2.0 - WANDER_AREA_MARGIN
		_:
			min_x = D.DORM_INNER_X + WANDER_AREA_MARGIN
			max_x = D.DORM_OUTER_X - WANDER_AREA_MARGIN
	var x_fraction := _unit_value(sequence, waypoint, attempt, 31)
	return Vector3(lerpf(min_x, max_x, x_fraction), 0.0, z_position)


static func _unit_value(first: int, second: int, third: int, salt: int) -> float:
	var seed := (
		float(first + 1) * 12.9898
		+ float(second + 1) * 78.233
		+ float(third + 1) * 37.719
		+ float(salt) * 19.193
	)
	return fposmod(sin(seed) * 43758.5453, 1.0)


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
