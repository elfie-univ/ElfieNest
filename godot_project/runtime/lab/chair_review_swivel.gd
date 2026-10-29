extends Node3D
var review_clock: Node
## First-chair fixture only. Original meshes and colliders share the same pivot.

var bodies: Array[AnimatableBody3D] = []
var excluded: Array[RID] = []
var last_obstacle := ""
var turning := false
var last_passenger_target := Transform3D.IDENTITY


func install(geometry: Node3D, physics: Node3D, contact: Transform3D) -> void:
	global_position = contact.origin
	var originals: Dictionary = {}
	for body: StaticBody3D in physics.find_children("*", "StaticBody3D", true, false):
		originals[String(body.get_meta("source_node", ""))] = body
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		var e: Dictionary = mesh.get_meta("extras", {})
		if e.get("resident") != "A" or e.get("assembly") != "chair": continue
		var piece := String(e.get("piece", ""))
		if piece in ["chair_post", "chair_base"]:
			if originals.has(String(mesh.name)): excluded.append((originals[String(mesh.name)] as StaticBody3D).get_rid())
			continue
		var original := originals.get(String(mesh.name)) as StaticBody3D
		var body: AnimatableBody3D
		if original != null or piece == "chair_petal":
			body = AnimatableBody3D.new()
			body.sync_to_physics = false
			body.set_meta("source_node", String(mesh.name))
			body.set_meta("piece", piece)
			add_child(body)
			body.global_transform = mesh.global_transform
			var shape := CollisionShape3D.new()
			if original != null:
				body.global_transform = original.global_transform
				shape.shape = (original.get_child(0) as CollisionShape3D).shape
				original.free()
			else:
				shape.shape = mesh.mesh.create_convex_shape(true, false)
			body.add_child(shape)
			bodies.append(body)
			excluded.append(body.get_rid())
		mesh.reparent(self, true)


func turn_to(angle: float, passenger: CharacterBody3D) -> bool:
	if turning: return false
	turning = true
	last_obstacle = ""
	var start := rotation.y
	var added_exceptions: Array[PhysicsBody3D] = []
	if passenger != null:
		# The seated passenger and carrier rotate as one joint. Do not sweep
		# the passenger against the carrier's previous-frame pose; keep all
		# external collisions active and restore exclusions at every exit.
		for body: AnimatableBody3D in bodies:
			if body not in passenger.get_collision_exceptions():
				passenger.add_collision_exception_with(body)
				added_exceptions.append(body)
	var passenger_frame := global_transform.affine_inverse() * passenger.global_transform if passenger != null else Transform3D.IDENTITY
	var elapsed := 0.0
	var duration := maxf(0.25, absf(angle - start) / 0.65)
	var clear_usec := 0
	var move_usec := 0
	var samples := 0
	while elapsed < duration:
		if review_clock != null: await review_clock.picker_physics_frame
		else: await get_tree().physics_frame
		elapsed = minf(elapsed + get_physics_process_delta_time(), duration)
		var fraction := smoothstep(0.0, 1.0, elapsed / duration)
		var target := Transform3D(Basis(Vector3.UP, lerpf(start, angle, fraction)), global_position)
		var started := Time.get_ticks_usec()
		var clear := _clear(target, passenger)
		clear_usec += Time.get_ticks_usec() - started
		if not clear:
			_restore_exceptions(passenger, added_exceptions)
			turning = false
			return false
		if passenger != null:
			var next := target * passenger_frame
			started = Time.get_ticks_usec()
			var passenger_clear := _passenger_clear(passenger, next)
			move_usec += Time.get_ticks_usec() - started
			if not passenger_clear:
				_restore_exceptions(passenger, added_exceptions)
				turning = false
				return false
			# Fixed seated joint, advanced one physics tick after swept queries.
			# Not a docking teleport or character-walking recovery solve.
			passenger.global_transform = next
		global_transform = target
		samples += 1
	print("CHAIR_SWIVEL_COST passenger=", passenger != null, " samples=", samples, " chair_query_ms=", clear_usec / 1000.0, " passenger_move_ms=", move_usec / 1000.0)
	turning = false
	_restore_exceptions(passenger, added_exceptions)
	return true


func _passenger_clear(passenger: CharacterBody3D, next: Transform3D) -> bool:
	last_passenger_target = next
	var omit := excluded.duplicate()
	omit.append(passenger.get_rid())
	var space := get_world_3d().direct_space_state
	for shape: CollisionShape3D in passenger.get_children().filter(func(child: Node) -> bool: return child is CollisionShape3D):
		if shape.disabled or shape.shape == null: continue
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = shape.shape
		query.exclude = omit
		query.collision_mask = passenger.collision_mask
		query.transform = passenger.global_transform * shape.transform
		query.motion = next.origin - passenger.global_position
		var fraction := space.cast_motion(query)
		if fraction.size() != 2 or fraction[0] < 1.0:
			last_obstacle = "seated body swept path / " + String(shape.shape.get_meta("body_region", "body"))
			return false
		query.motion = Vector3.ZERO
		query.transform = next * shape.transform
		if not space.intersect_shape(query, 1).is_empty():
			last_obstacle = "seated body rotated pose / " + String(shape.shape.get_meta("body_region", "body"))
			return false
	return true


func _restore_exceptions(passenger: CharacterBody3D, added: Array[PhysicsBody3D]) -> void:
	if passenger == null: return
	for body: PhysicsBody3D in added: passenger.remove_collision_exception_with(body)


func _clear(target: Transform3D, passenger: CharacterBody3D) -> bool:
	var omit := excluded.duplicate()
	if passenger != null: omit.append(passenger.get_rid())
	for body: AnimatableBody3D in bodies:
		var shape := body.get_child(0) as CollisionShape3D
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = shape.shape
		query.transform = target * body.transform * shape.transform
		query.exclude = omit
		var hits := get_world_3d().direct_space_state.intersect_shape(query, 1)
		if not hits.is_empty():
			var obstacle := hits[0]["collider"] as Node
			last_obstacle = String(obstacle.get_meta("source_node", obstacle.name))
			print("CHAIR_SWIVEL_BLOCKED ", last_obstacle)
			return false
	return true
