extends Node3D
## Original chair geometry and collision rotate together around its seat contact.

var bodies: Array[AnimatableBody3D] = []
var excluded: Array[RID] = []
var last_obstacle := ""
var turning := false
var last_passenger_target := Transform3D.IDENTITY
var _turn_serial := 0
var _active_turn: Dictionary = {}


func install(geometry: Node3D, physics: Node3D, contact: Transform3D, module: String, resident: String) -> void:
	global_position = contact.origin
	# Desktop silhouettes are baked with the world, never unioned/decomposed
	# synchronously on the browser thread when a user presses Play.
	var originals: Dictionary = {}
	for body: StaticBody3D in physics.find_children("*", "StaticBody3D", true, false):
		# Split layouts repeat mesh names even within a room. Match the
		# live source instance, never a display name or cached object ID.
		if str(body.get_meta("estate_module", "")) == module:
			originals[int(body.get_meta("source_mesh_id", 0))] = body
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		var e: Dictionary = mesh.get_meta("extras", {})
		if e.get("module") != module or e.get("resident") != resident or e.get("assembly") != "chair": continue
		var piece := String(e.get("piece", ""))
		if piece in ["chair_post", "chair_base"]:
			if originals.has(mesh.get_instance_id()): excluded.append((originals[mesh.get_instance_id()] as StaticBody3D).get_rid())
			continue
		var original := originals.get(mesh.get_instance_id()) as StaticBody3D
		var body: AnimatableBody3D
		if original != null or piece == "chair_petal":
			body = AnimatableBody3D.new()
			body.sync_to_physics = false
			body.set_meta("source_node", String(mesh.name))
			body.set_meta("source_mesh_id", mesh.get_instance_id())
			body.set_meta("piece", piece)
			body.set_meta("estate_module",module)
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
	if turning or not is_inside_tree() or is_queued_for_deletion(): return false
	turning = true
	_turn_serial += 1
	last_obstacle = ""
	var start := rotation.y
	print("CHAIR_SWIVEL_PATH start=",start," target=",angle," passenger=",passenger != null)
	var added_exceptions: Array[PhysicsBody3D] = []
	var state := {"serial":_turn_serial,"passenger":passenger,"has_passenger":passenger != null,
		"command":str(passenger.get("furniture_cycle_command")) if passenger != null and passenger.has_method("cycle_available") else "",
		"chair_frame":global_transform,"passenger_frame":passenger.global_transform if passenger != null else Transform3D.IDENTITY,
		"added":added_exceptions,"samples":0,"batches":0,"budget_yields":0,
		"chair_usec":0,"passenger_usec":0,"max_batch_usec":0,
		"max_query_usec":0,"max_query_kind":"","max_query_region":""}
	_active_turn = state
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
	var started_usec := _clock_usec()
	var tree := get_tree()
	var batch_frame := -1
	var batch_usec := 0
	while elapsed < duration:
		await tree.physics_frame
		if not _turn_valid(state): return _finish_turn(state,false)
		var target_elapsed := minf(duration, float(_clock_usec()-started_usec)/1000000.0 * Engine.time_scale)
		# Retain the pending horizon and elapsed cursor across yields. Backlog is
		# never discarded to follow the real-time clock without collision checks.
		while elapsed < target_elapsed:
			if not _turn_valid(state): return _finish_turn(state,false)
			if batch_frame != Engine.get_process_frames():
				batch_frame = Engine.get_process_frames()
				batch_usec = 0
				state.batches += 1
			var slice_started := _clock_usec()
			var next_elapsed := minf(elapsed + 1.0 / 60.0, target_elapsed)
			var fraction := smoothstep(0.0, 1.0, next_elapsed / duration)
			var target := Transform3D(Basis(Vector3.UP, lerpf(start, angle, fraction)), global_position)
			var started := _clock_usec()
			var clear := _clear(target, passenger)
			state.chair_usec += _clock_usec() - started
			if not clear or not _turn_valid(state): return _finish_turn(state,false)
			if passenger != null:
				var next := target * passenger_frame
				started = _clock_usec()
				var passenger_clear := _passenger_clear(passenger, next)
				state.passenger_usec += _clock_usec() - started
				if not passenger_clear or not _turn_valid(state): return _finish_turn(state,false)
				# Fixed seated joint, advanced one physics tick after swept queries.
				# Not a docking teleport or character-walking recovery solve.
				passenger.global_transform = next
				state.passenger_frame = next
			global_transform = target
			state.chair_frame = target
			elapsed = next_elapsed
			state.samples += 1
			batch_usec += _clock_usec()-slice_started
			state.max_batch_usec = maxi(int(state.max_batch_usec),batch_usec)
			if batch_usec >= work_budget_usec(get_process_delta_time()) and elapsed < duration:
				state.budget_yields += 1
				# Several physics ticks may belong to one render frame. Cross a
				# process-frame boundary before resuming at a legal physics tick.
				while Engine.get_process_frames() == batch_frame:
					await tree.process_frame
					if not _turn_valid(state): return _finish_turn(state,false)
				await tree.physics_frame
				if not _turn_valid(state): return _finish_turn(state,false)
	return _finish_turn(state,true)


static func work_budget_usec(frame_delta: float) -> int:
	# A seated half turn needs hundreds of swept poses. At low frame rates,
	# reserve half a frame for these checks so rendering does not dominate the
	# turn duration. The cap still prevents processing the entire backlog at once.
	return clampi(int(frame_delta * 500000.0), 8000, 64000)


func _clock_usec() -> int:
	return Time.get_ticks_usec()


func _turn_valid(state: Dictionary) -> bool:
	if state.serial != _turn_serial or not turning or not is_inside_tree() or is_queued_for_deletion(): return false
	if not global_transform.is_equal_approx(state.chair_frame): return false
	if state.has_passenger:
		if not is_instance_valid(state.passenger): return false
		var passenger := state.passenger as CharacterBody3D
		if not passenger.is_inside_tree() or passenger.is_queued_for_deletion(): return false
		if not passenger.global_transform.is_equal_approx(state.passenger_frame): return false
		if passenger.has_method("cycle_available"):
			if not passenger.cycle_available() or str(passenger.get("furniture_cycle_command")) != state.command: return false
	return true


func _finish_turn(state: Dictionary, accepted: bool) -> bool:
	if state.serial != _turn_serial or not turning: return false
	turning = false
	_active_turn = {}
	if state.has_passenger and is_instance_valid(state.passenger):
		_restore_exceptions(state.passenger,state.added)
	print("CHAIR_SWIVEL_COST passenger=",state.has_passenger," completed=",accepted,
		" samples=",state.samples," chair_query_ms=",float(state.chair_usec)/1000.0,
		" passenger_move_ms=",float(state.passenger_usec)/1000.0," batches=",state.batches,
		" budget_yields=",state.budget_yields," max_batch_ms=",float(state.max_batch_usec)/1000.0,
		" max_query_ms=",float(state.max_query_usec)/1000.0,
		" query_kind=",state.max_query_kind," query_region=",state.max_query_region)
	return accepted


func _record_query(started: int, kind: String, region: String) -> void:
	if _active_turn.is_empty(): return
	var cost := _clock_usec()-started
	if cost > int(_active_turn.max_query_usec):
		_active_turn.max_query_usec = cost
		_active_turn.max_query_kind = kind
		_active_turn.max_query_region = region


func _exit_tree() -> void:
	if turning: _finish_turn(_active_turn,false)
	_turn_serial += 1


func _passenger_clear(passenger: CharacterBody3D, next: Transform3D) -> bool:
	last_passenger_target = next
	var omit := excluded.duplicate()
	omit.append(passenger.get_rid())
	var space := get_world_3d().direct_space_state
	for shape: CollisionShape3D in passenger.get_children().filter(func(child: Node) -> bool: return child is CollisionShape3D):
		if shape.disabled or shape.shape == null: continue
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = shape.shape
		query.margin = 0.001
		query.exclude = omit
		query.collision_mask = passenger.collision_mask
		query.transform = passenger.global_transform * shape.transform
		query.motion = next.origin - passenger.global_position
		var started := _clock_usec()
		var fraction := space.cast_motion(query)
		_record_query(started,"passenger_cast",str(shape.shape.get_meta("body_region","body")))
		if fraction.size() != 2 or fraction[0] < 1.0:
			last_obstacle = "seated body swept path / " + String(shape.shape.get_meta("body_region", "body"))
			return false
		query.motion = Vector3.ZERO
		query.transform = next * shape.transform
		started = _clock_usec()
		var hits := space.intersect_shape(query, 1)
		_record_query(started,"passenger_pose",str(shape.shape.get_meta("body_region","body")))
		if not hits.is_empty():
			var obstacle := hits[0]["collider"] as Node
			last_obstacle = "seated body rotated pose / " + String(shape.shape.get_meta("body_region", "body")) + " / " + str(obstacle.get_meta("source_node", obstacle.name)) + " / " + str(obstacle.get_path())
			return false
	return true


func _restore_exceptions(passenger: CharacterBody3D, added: Array[PhysicsBody3D]) -> void:
	if not is_instance_valid(passenger): return
	for body: PhysicsBody3D in added:
		if is_instance_valid(body): passenger.remove_collision_exception_with(body)


func _clear(target: Transform3D, passenger: CharacterBody3D) -> bool:
	var omit := excluded.duplicate()
	if passenger != null: omit.append(passenger.get_rid())
	for body: AnimatableBody3D in bodies:
		var shape := body.get_child(0) as CollisionShape3D
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = shape.shape
		query.margin = 0.001
		query.transform = target * body.transform * shape.transform
		query.exclude = omit
		var started := _clock_usec()
		var hits := get_world_3d().direct_space_state.intersect_shape(query, 1)
		_record_query(started,"chair_pose",str(body.get_meta("source_node",body.name)))
		if not hits.is_empty():
			var obstacle := hits[0]["collider"] as Node
			last_obstacle = String(obstacle.get_meta("source_node", obstacle.name))
			print("CHAIR_SWIVEL_BLOCKED ", last_obstacle)
			return false
	return true
