class_name ActorPathPlanner
extends RefCounted

const ACTOR_EGRESS_CLEARANCE := 0.9
const ACTOR_EGRESS_LOOKAHEAD := 2.0
const ACTOR_COLLISION_CLEARANCE := 0.73


static func path_with_actor_egress(
	actor: CharacterBody3D,
	target_position: Vector3,
) -> PackedVector3Array:
	var navigation_map := actor.get_world_3d().navigation_map
	var direct_path := NavigationServer3D.map_get_path(
		navigation_map,
		actor.global_position,
		target_position,
		true,
	)
	if direct_path.size() < 2:
		return direct_path
	var egress_direction := direct_path[1] - actor.global_position
	egress_direction.y = 0.0
	if egress_direction.is_zero_approx():
		return direct_path
	egress_direction = egress_direction.normalized()
	var egress_end := (
		actor.global_position + egress_direction * ACTOR_EGRESS_LOOKAHEAD
	)
	for node in actor.get_tree().get_nodes_in_group(&"runtime_elfie_actors"):
		if node == actor or not node is CharacterBody3D:
			continue
		var other := node as CharacterBody3D
		if (
			actor.global_position.distance_to(other.global_position)
			> ACTOR_EGRESS_LOOKAHEAD
		):
			continue
		if _horizontal_segment_distance(
			other.global_position,
			actor.global_position,
			egress_end,
		) >= ACTOR_COLLISION_CLEARANCE:
			continue
		var side := (
			-1.0
			if String(actor.get("elfie_id")) < String(other.get("elfie_id"))
			else 1.0
		)
		var perpendicular := Vector3(
			-egress_direction.z,
			0.0,
			egress_direction.x,
		)
		var detour := NavigationServer3D.map_get_closest_point(
			navigation_map,
			other.global_position
				+ perpendicular * side * ACTOR_EGRESS_CLEARANCE,
		)
		var first_leg := NavigationServer3D.map_get_path(
			navigation_map,
			actor.global_position,
			detour,
			true,
		)
		var second_leg := NavigationServer3D.map_get_path(
			navigation_map,
			detour,
			target_position,
			true,
		)
		if first_leg.is_empty() or second_leg.is_empty():
			continue
		first_leg.append_array(second_leg.slice(1))
		return first_leg
	return direct_path


static func _horizontal_segment_distance(
	point: Vector3,
	start: Vector3,
	end: Vector3,
) -> float:
	var point_2d := Vector2(point.x, point.z)
	var start_2d := Vector2(start.x, start.z)
	var segment := Vector2(end.x - start.x, end.z - start.z)
	var length_squared := segment.length_squared()
	if length_squared <= 0.000001:
		return point_2d.distance_to(start_2d)
	var projection := clampf(
		(point_2d - start_2d).dot(segment) / length_squared,
		0.0,
		1.0,
	)
	return point_2d.distance_to(start_2d + segment * projection)
