extends Node
## Shared direct seated landing, driven by real furniture frames and collisions.
const CLIPS := preload("res://runtime/actor/chair_clip_sequence.gd")
const CONTACT := preload("res://runtime/actor/furniture_contact.gd")
const HULLS := preload("res://runtime/actor/furniture_seated_collision.gd")
const HANDS := preload("res://runtime/actor/direct_seated_arm_pose.gd")
const MOTION := preload("res://runtime/actor/direct_seat_motion.gd")
const PROFILE := preload("res://nest/furniture/layouts/bedroom/direct-seat.tres")
var actor: ElfieActor
var motion: RefCounted
var swivel: Node3D
var open_angle := PI
var _desk_turn_delta := -PI
var entry := Transform3D.IDENTITY
var waiting := Transform3D.IDENTITY
var _support_points: Array[Vector3] = []
var _bound := false
var _fit_source_id := 0
var _checking_fit := false
var _frame_ms: Dictionary = {}
var _previous_frame_usec := 0
var _engine_work: Dictionary = {}
var _released := false
var _original_library: AnimationLibrary
var _original_chair_library: AnimationLibrary
var _seat_library: AnimationLibrary
var _standing_visual := Transform3D.IDENTITY
var _standing_bones: Array[Dictionary] = []
var _fit_trace_enabled := OS.get_environment("ELFIENEST_SEAT_FIT_TRACE") == "1"
var _fit_trace_turn: Dictionary = {}

func _process(_delta: float) -> void:
	var now := Time.get_ticks_usec()
	var elapsed := float(now-_previous_frame_usec)/1000.0
	var has_previous := _previous_frame_usec != 0
	_previous_frame_usec = now
	if not has_previous or not is_instance_valid(actor): return
	var phase := "fit" if _checking_fit else ("prepare" if str(actor.get_meta("furniture_cycle_stage","")) == "prepare_seat" else "play")
	if not _frame_ms.has(phase): _frame_ms[phase] = []
	_frame_ms[phase].append(elapsed)
	if not _engine_work.has(phase): _engine_work[phase] = {"process":[],"physics":[],"draw_calls":0,"objects":0,"primitives":0}
	var work: Dictionary = _engine_work[phase]
	work.process.append(Performance.get_monitor(Performance.TIME_PROCESS)*1000.0)
	work.physics.append(Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS)*1000.0)
	work.draw_calls = Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)
	work.objects = Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME)
	work.primitives = Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)


func stage(value: String) -> void:
	actor.set_meta("furniture_cycle_stage",value)
	print("DIRECT_SEAT_STAGE ",value)

func available() -> bool:
	return is_instance_valid(actor) and actor.cycle_available()

func failed(reason: String) -> Dictionary:
	return {"status":"cancelled" if is_instance_valid(actor) and actor.cycle_cancelled else "failed","reason":reason}

func _wait_for_navigation(point: Vector3) -> RID:
	if not is_inside_tree() or not available(): return RID()
	var body := actor
	var command := actor.furniture_cycle_command
	var tree := get_tree()
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		# Do not resume a cancelled command or a detached/replaced owner after await.
		if not is_inside_tree() or is_queued_for_deletion() or not is_instance_valid(body): return RID()
		if actor != body or not body.is_inside_tree() or body.is_queued_for_deletion(): return RID()
		if body.furniture_cycle_command != command or not available(): return RID()
		var map := body.get_world_3d().navigation_map
		if map.is_valid() and NavigationServer3D.map_is_active(map) and NavigationServer3D.map_get_iteration_id(map) > 0:
			# An empty synchronized map is not yet the deferred estate navigation.
			if NavigationServer3D.map_get_closest_point_owner(map, point).is_valid(): return map
		await tree.physics_frame
	return RID()

func _project_waiting() -> bool:
	var map := await _wait_for_navigation(waiting.origin)
	if not map.is_valid(): return false
	var floor_point := NavigationServer3D.map_get_closest_point(map, waiting.origin)
	if floor_point.distance_to(waiting.origin) < 0.35:
		waiting.origin.x = floor_point.x
		waiting.origin.z = floor_point.z
	return true

func standing_floor(point: Vector3) -> float:
	var ray := PhysicsRayQueryParameters3D.create(point+Vector3.UP*0.25,point-Vector3.UP*0.30,actor.collision_mask)
	ray.exclude = [actor.get_rid()]
	var hit := actor.get_world_3d().direct_space_state.intersect_ray(ray)
	if not hit.is_empty() and (hit.normal as Vector3).y > 0.7:
		return (hit.position as Vector3).y+0.02
	return point.y

func walk(point: Vector3) -> bool:
	var map := await _wait_for_navigation(point)
	if not map.is_valid(): return false
	var route := NavigationServer3D.map_get_path(map,actor.global_position,point,true)
	# The first point is the projected start. Physics recovery may already
	# have moved the body clear of it; never steer back into that obstacle.
	for index in range(1,route.size()):
		var waypoint: Vector3 = route[index]
		if Vector2(waypoint.x-actor.global_position.x,waypoint.z-actor.global_position.z).length() < 0.01: continue
		if not await walk_segment(waypoint): return false
	return await walk_segment(point)

func walk_segment(point: Vector3) -> bool:
	if not available(): return false
	actor.walk_precisely(point)
	var result: Array = await actor.precision_terminal
	if not bool(result[0]):
		print("DIRECT_SEAT_WALK_BLOCKED from=",actor.global_position," target=",point," reason=",result[1])
		for index in range(actor.get_slide_collision_count()):
			var obstacle := actor.get_slide_collision(index).get_collider() as Node
			print("DIRECT_SEAT_WALK_OBSTACLE ",obstacle.get_meta("source_node",obstacle.name))
	return bool(result[0]) and available()

func run(body: ElfieActor, marker: Marker3D, nest: ModularNest) -> Dictionary:
	actor = body
	_released = false
	var result := await _run(marker, nest)
	# Restore before returning the command: queue_free may run after a new action.
	_finish()
	return result

static func bench_bounds(geometry: Node3D, source: MeshInstance3D) -> AABB:
	var base_name := str(source.get_meta("extras",{}).get("source_name",source.name))
	var bounds := source.global_transform * source.get_aabb()
	var height := bounds.get_center().y
	var pending: Array[AABB] = []
	for mesh: MeshInstance3D in geometry.find_children("*","MeshInstance3D",true,false):
		if mesh.has_meta("source_geometry_path") or not str(mesh.name).begins_with(base_name+"_"): continue
		var candidate := mesh.global_transform * mesh.get_aabb()
		if absf(candidate.get_center().y-height) <= 0.02: pending.append(candidate)
	# Names also cover the bench across a picnic table. Include only the
	# connected run of boards; the authored slat gaps are under four cm.
	var changed := true
	while changed:
		changed = false
		for index in range(pending.size()-1,-1,-1):
			if bounds.grow(0.04).intersects(pending[index]):
				bounds = bounds.merge(pending[index])
				pending.remove_at(index)
				changed = true
	return bounds

func opening_target(requested: float) -> float:
	var current := swivel.rotation.y
	var delta := wrapf(requested-current,-PI,PI)
	# Preserve the selected side at a half-turn, but never spin an already-open
	# reused chair through 2*PI merely because Euler represents +PI as -PI.
	if is_equal_approx(absf(delta),PI): delta = PI if requested >= 0.0 else -PI
	return current+delta

func desk_target() -> float:
	return swivel.rotation.y+_desk_turn_delta

func exit_target() -> float:
	return swivel.rotation.y-_desk_turn_delta

func _run(marker: Marker3D, nest: ModularNest) -> Dictionary:
	var geometry := nest.get_node("Generated/CompleteEstate") as Node3D
	var source := marker.get_meta("furniture_source",geometry.find_child(str(marker.get_meta("source_node")),true,false)) as MeshInstance3D
	if source == null: return failed("direct_seat_source_missing")
	_fit_source_id = source.get_instance_id()
	var extras := source.get_meta("extras",{}) as Dictionary
	var closed := marker.get_meta("direct_seat_closed_frame",marker.get_meta("interaction_transform")) as Transform3D
	var rotating: bool = str(extras.get("assembly","")) == "chair"
	var profile := PROFILE.duplicate(true)
	if rotating:
		for mesh: MeshInstance3D in geometry.find_children("*","MeshInstance3D",true,false):
			var e := mesh.get_meta("extras",{}) as Dictionary
			if e.get("module") == extras.get("module") and e.get("resident") == extras.get("resident") and e.get("source_name") == "Chair | central tall back petal":
				var forward := closed.origin - (mesh.global_transform * mesh.get_aabb()).get_center()
				forward.y = 0
				closed.basis = Basis(Vector3.UP,atan2(forward.x,forward.z))
		marker.set_meta("direct_seat_closed_frame",closed)
		swivel = marker.get_meta("furniture_carrier") as Node3D if marker.has_meta("furniture_carrier") else null
		if swivel == null:
			swivel = preload("res://runtime/actor/chair_swivel.gd").new()
			nest.add_child(swivel)
			swivel.install(geometry,nest._estate_physics,closed,str(extras.get("module")),str(extras.get("resident")))
			if swivel.bodies.is_empty(): return failed("chair_carrier_unavailable: "+str(swivel.last_obstacle))
			marker.set_meta("furniture_carrier",swivel)
			marker.set_meta("furniture_source",source)
	else:
		profile.set_meta("contact_offset",Vector3.ZERO)
		profile.set_meta("wait_offset",Vector3(0,0,0.90))
	if str(marker.get_meta("furniture_type","")) == "bench":
		# Slatted seats expose one semantic mesh but several adjacent boards.
		# Measure the complete seating surface, not the first board's centre.
		var bounds := bench_bounds(geometry,source)
		closed.origin = bounds.get_center()
		closed.origin.y = bounds.end.y+0.02
		var reach := 0.0
		for corner in range(8): reach = maxf(reach,(bounds.get_endpoint(corner)-closed.origin).dot(closed.basis.z))
		var radius := (actor._collision_shape.shape as CapsuleShape3D).radius
		profile.set_meta("entry_offset",Vector3(0,0,maxf(0.35,reach+radius+0.10)))
	var boarding_angle := PI
	if rotating:
		var best_clearance := -1.0
		for angle: float in [PI,-3.0*PI/4.0,3.0*PI/4.0,-PI/2.0,PI/2.0]:
			var facing := Basis(Vector3.UP,angle)*closed.basis
			var point := closed.origin + facing * ((profile.get_meta("contact_offset") as Vector3)+(profile.get_meta("entry_offset") as Vector3))
			point.y = marker.global_position.y
			var probe := PhysicsShapeQueryParameters3D.new()
			probe.shape = actor._collision_shape.shape
			probe.transform = Transform3D(facing,point)*actor._collision_shape.transform
			var ignored: Array[RID] = [actor.get_rid()]
			ignored.append_array(swivel.excluded)
			probe.exclude = ignored
			probe.collision_mask = actor.collision_mask
			probe.margin = 0.0
			var hits := actor.get_world_3d().direct_space_state.intersect_shape(probe,1)
			if not hits.is_empty():
				print("DIRECT_SEAT_DIRECTION blocked=",angle," obstacle=",(hits[0].collider as Node).get_meta("source_node","?"))
				continue
			var clearance := INF
			for mesh: MeshInstance3D in geometry.find_children("*","MeshInstance3D",true,false):
				var e: Dictionary = mesh.get_meta("extras",{})
				if e.get("piece") != "chair_cushion" or (e.get("module") == extras.get("module") and e.get("resident") == extras.get("resident")): continue
				var bounds := mesh.global_transform*mesh.get_aabb()
				var nearest := point.clamp(bounds.position,bounds.end)
				clearance = minf(clearance,Vector2(point.x-nearest.x,point.z-nearest.z).length())
			print("DIRECT_SEAT_DIRECTION angle=",angle," clearance=",clearance)
			if clearance > best_clearance:
				best_clearance = clearance
				boarding_angle = angle
			if best_clearance >= 0.85: break
	var opened := Transform3D((Basis(Vector3.UP,boarding_angle)*closed.basis) if rotating else closed.basis,closed.origin)
	opened.origin = opened * (profile.get_meta("contact_offset") as Vector3)
	entry = Transform3D(opened.basis,opened * (profile.get_meta("entry_offset") as Vector3))
	var wait_frame := Transform3D(Basis(Vector3.UP,PI)*closed.basis,closed.origin) if rotating else opened
	if rotating: wait_frame.origin = wait_frame * (profile.get_meta("contact_offset") as Vector3)
	waiting = Transform3D(wait_frame.basis,wait_frame * (profile.get_meta("wait_offset") as Vector3))
	entry.origin.y = standing_floor(Vector3(entry.origin.x,marker.global_position.y,entry.origin.z))
	waiting.origin.y = standing_floor(Vector3(waiting.origin.x,marker.global_position.y,waiting.origin.z))
	print("DIRECT_SEAT_FLOOR entry=",entry.origin," waiting=",waiting.origin)
	# Waiting is a walking-floor target, unlike the exact docking contact.
	# Project it clear of neighbouring furniture using the production navmesh.
	if not await _project_waiting(): return failed("direct_seat_navigation_unavailable")
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	var locomotion := CLIPS.locomotion_for(actor)
	var library := CLIPS.library_for(actor)
	if locomotion == null or library == null: return failed("direct_seat_retarget_missing")
	var hand_rest := PROFILE.get_meta("hand_rest") as Vector3
	if actor.species_id == "saevi": hand_rest = Vector3(0.23,0.05,0.06)
	HANDS.bake(library.get_animation("seated_idle"),actor,hand_rest)
	_install_seat_animations(locomotion, library)
	player.play("idle")
	player.advance(0.0)
	CONTACT.ground(actor,entry.origin.y)
	motion = MOTION.new()
	stage("prepare_seat")
	var prepared := Time.get_ticks_msec()
	var error: String = await motion.bind(actor,opened,entry,profile,Callable(HULLS,"shapes"),Callable(CONTACT,"butt_point"))
	print("DIRECT_SEAT_PREPARE elapsed_ms=",Time.get_ticks_msec()-prepared)
	if not error.is_empty(): return failed(error)
	_bound = true
	stage("wait_outside_chair")
	if not await walk(waiting.origin): return failed("direct_seat_wait_blocked")
	if swivel != null:
		stage("chair_turn_out")
		if not await swivel.turn_to(opening_target(boarding_angle),null): return failed(swivel.last_obstacle)
		# Keep the chosen signed arc, independently of Euler canonicalization.
		open_angle = boarding_angle
	if not await fit_landing(opened): return failed("direct_seat_fit_blocked: "+str(motion.last_obstacle))
	stage("approach_seat")
	if not await walk(entry.origin): return failed("direct_seat_approach_blocked")
	actor.set_physics_process(false)
	actor.set_process(false)
	motion.capture_entry_pose()
	stage("tail_tuck")
	var started_usec := Time.get_ticks_usec()
	var amount := 0.0
	while amount < 1.0:
		await get_tree().physics_frame
		if not available(): return failed("cancelled")
		amount = minf(1.0,float(Time.get_ticks_usec()-started_usec)/1000000.0 * Engine.time_scale/(40.0/60.0))
		motion.tail_weight = smoothstep(0.0,1.0,amount)
		motion._apply_tail()
	stage("turn_on_floor")
	var heading := actor.global_basis.get_rotation_quaternion()
	started_usec = Time.get_ticks_usec()
	amount = 0.0
	while amount < 1.0:
		await get_tree().physics_frame
		if not available(): return failed("cancelled")
		amount = smoothstep(0.0,1.0,minf(1.0,float(Time.get_ticks_usec()-started_usec)/1000000.0 * Engine.time_scale/0.6))
		actor.global_basis = Basis(heading.slerp(entry.basis.get_rotation_quaternion(),amount))
		motion.blend_ground_pose(amount)
	CONTACT.ground(actor,entry.origin.y)
	(actor.get_node("CollisionShape3D") as CollisionShape3D).disabled = true
	stage("direct_seated_hop")
	if not await hop(false): return failed("direct_seat_hop_blocked: "+str(motion.last_obstacle))
	motion.install_seated_collision()
	if swivel != null:
		stage("chair_turn_to_desk")
		if not await swivel.turn_to(desk_target(),actor): return failed(swivel.last_obstacle)
	stage("seated_idle")
	started_usec = Time.get_ticks_usec()
	while float(Time.get_ticks_usec()-started_usec) * Engine.time_scale < 3000000.0:
		await get_tree().physics_frame
		if not available(): return failed("cancelled")
	if swivel != null:
		stage("chair_turn_to_exit")
		if not await swivel.turn_to(exit_target(),actor): return failed(swivel.last_obstacle)
	stage("direct_seated_exit")
	if not await hop(true): return failed("direct_seat_exit_blocked: "+str(motion.last_obstacle))
	started_usec = Time.get_ticks_usec()
	amount = 0.0
	while amount < 1.0:
		await get_tree().physics_frame
		if not available(): return failed("cancelled")
		amount = minf(1.0,float(Time.get_ticks_usec()-started_usec)/1000000.0 * Engine.time_scale/0.4)
		motion.tail_weight = 1.0-amount
		motion.sample(0.0)
	motion.release()
	_bound = false
	stage("leave_seat")
	if not await walk(waiting.origin): return failed("direct_seat_leave_blocked")
	return {"status":"completed","reason":""}

func _install_seat_animations(locomotion: AnimationLibrary, seated: AnimationLibrary) -> void:
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	var runtime: RefCounted = actor.get("_animation_runtime")
	_original_library = player.get_animation_library("")
	_original_chair_library = player.get_animation_library("chair") if player.has_animation_library("chair") else null
	_standing_visual = runtime.standing_visual_transform()
	_standing_bones.assign(runtime.capture_visual_pose()["bones"])
	_seat_library = _original_library.duplicate() as AnimationLibrary
	for key: String in ["idle", "walking"]:
		if _seat_library.has_animation(key): _seat_library.remove_animation(key)
		_seat_library.add_animation(key, locomotion.get_animation(key))
	player.remove_animation_library("")
	player.add_animation_library("", _seat_library)
	if player.has_animation_library("chair"): player.remove_animation_library("chair")
	player.add_animation_library("chair", seated)

func _restore_seat_animations() -> void:
	if _seat_library == null: return
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	# Another owner must not inherit a late restoration from this controller.
	if not player.has_animation_library("") or player.get_animation_library("") != _seat_library: return
	var runtime: RefCounted = actor.get("_animation_runtime")
	runtime.cancel_expression()
	runtime.reset_procedural_pose()
	player.stop()
	player.remove_animation_library("")
	player.add_animation_library("", _original_library)
	if player.has_animation_library("chair"): player.remove_animation_library("chair")
	if _original_chair_library != null: player.add_animation_library("chair", _original_chair_library)
	# Retargeted locomotion has a different Hips origin. Its ground offset belongs
	# to that temporary library, not to the actor's other shared expressions.
	(actor.get_node("VisualRoot") as Node3D).transform = _standing_visual
	for pose: Dictionary in _standing_bones:
		var skeleton := pose.skeleton as Skeleton3D
		if not is_instance_valid(skeleton): continue
		skeleton.set_bone_pose_position(pose.bone, pose.position)
		skeleton.set_bone_pose_rotation(pose.bone, pose.rotation)
	player.playback_active = true
	player.play("idle", 0.0)
	player.seek(0.0, true)
	player.advance(0.0)
	_seat_library = null
	_original_library = null
	_original_chair_library = null
	_standing_bones.clear()

func _finish() -> void:
	if _released: return
	_released = true
	if not is_instance_valid(actor): return
	if _bound:
		_bound = false
		motion.tail_weight = 0.0
		motion.sample(0.0)
		motion.release()
	_restore_seat_animations()
	actor.remove_meta("furniture_cycle_stage")

static func fit_budget_usec(frame_delta: float) -> int:
	return clampi(int(frame_delta*250000.0),8000,32000)

func fit_landing(contact: Transform3D) -> bool:
	_checking_fit = true
	# Fit the same motion to the actual body and seat. Never move furniture,
	# shrink a body hull or accept a landing without a supporting seat surface.
	var saved := actor.global_transform
	var visual := (actor.get_node("VisualRoot") as Node3D).transform
	var pose: Array[Transform3D] = motion._capture()
	var base: Vector3 = motion.end_frame.origin
	var accepted := false
	var slice_started := Time.get_ticks_usec()
	var budget_us := fit_budget_usec(get_process_delta_time())
	var neighbour_blocked := false
	actor.set_physics_process(false)
	actor.set_process(false)
	var cells := {}
	for shape: Shape3D in motion.seated_shapes:
		if not str(shape.get_meta("body_region","")).contains("Hips"): continue
		for point: Vector3 in (shape as ConvexPolygonShape3D).points:
			var cell := Vector2i(roundi(point.x/0.04),roundi(point.z/0.04))
			if not cells.has(cell) or point.y < (cells[cell] as Vector3).y: cells[cell] = point
	_support_points.assign(cells.values())
	var fit_key := hash([_fit_source_id,(actor.get_meta("seated_pose_cache",{}) as Dictionary).get("key",0)])
	var fit_cache: Dictionary = actor.get_meta("seated_fit_cache",{})
	var hint: Dictionary = fit_cache.get(fit_key,{})
	print("DIRECT_SEAT_FIT_HINT available=",not hint.is_empty())
	var offsets: Array[Vector2] = []
	for forward: float in [0.0,0.02,0.04,0.06,0.08,0.10,0.12,0.16,0.20,0.24,-0.04,-0.08,-0.12]:
		offsets.append(Vector2(0,forward))
	for side: float in [-0.10,0.10,-0.20,0.20]:
		for forward: float in [0.0,-0.08]: offsets.append(Vector2(side,forward))
	if not hint.is_empty():
		offsets.erase(hint.offset)
		offsets.push_front(hint.offset)
	for offset: Vector2 in offsets:
		motion.end_frame.origin = base + contact.basis.z * offset.y + contact.basis.x * offset.x
		motion.tail_weight = 1.0
		var support := seat_support(contact.origin.y,motion.end_frame)
		accepted = not support.is_empty()
		if not accepted: _trace_fit_rejection("support",offset)
		if accepted:
			motion.end_frame.origin.y += float(support.offset)
			motion.sample(1.0)
			accepted = motion.clear_path(actor.global_transform,actor.global_transform,1.0)
			if not accepted: _trace_fit_rejection("seated_endpoint",offset,false,1.0,actor.global_transform)
			if accepted and swivel != null:
				# The turn preflight yields; keep displaying the actor's waiting pose.
				actor.global_transform = saved
				(actor.get_node("VisualRoot") as Node3D).transform = visual
				motion._apply(pose)
				accepted = await fit_seated_turn(hint,offset)
		if accepted:
			accepted = false
			var rises: Array[float] = [1.0,1.75,2.5]
			var arcs: Array[float] = [0.0,1.0,2.0]
			if not hint.is_empty() and offset == hint.offset:
				rises.erase(float(hint.rise)); rises.push_front(float(hint.rise))
				arcs.erase(float(hint.arc)); arcs.push_front(float(hint.arc))
			for rise: float in rises:
				motion.rise_scale = rise
				for arc: float in arcs:
					motion.arc_clearance = arc
					accepted = true
					# The outgoing clip and hull cache differ from the incoming ones.
					# Accept this exact offset/rise/arc only if both full sweeps pass.
					for leaving: bool in [false,true]:
						var previous: Transform3D = motion.end_frame if leaving else motion.start_frame
						var seconds := float(PROFILE.get_meta("leave_seconds" if leaving else "hop_seconds"))
						var steps := maxi(64,ceili(seconds*60.0))
						for index in range(steps+1):
							if not available():
								accepted = false
								break
							var amount := float(index)/steps
							if leaving: motion.sample_exit(amount)
							else: motion.sample(amount)
							if not motion.clear_path(previous,actor.global_transform,amount,leaving):
								accepted = false
								neighbour_blocked = not leaving and swivel != null and is_instance_valid(motion.last_collider) and not motion.last_collider is AnimatableBody3D and str(motion.last_collider.get_meta("source_node","")).contains("Chair")
								_trace_fit_rejection("exit" if leaving else "enter",offset,leaving,amount,previous,neighbour_blocked)
								break
							previous = actor.global_transform
							if Time.get_ticks_usec()-slice_started >= budget_us:
								actor.global_transform = saved
								(actor.get_node("VisualRoot") as Node3D).transform = visual
								motion._apply(pose)
								await get_tree().process_frame
								slice_started = Time.get_ticks_usec()
								budget_us = fit_budget_usec(get_process_delta_time())
								if not available():
									accepted = false
									break
						if not accepted: break
					actor.global_transform = saved
					(actor.get_node("VisualRoot") as Node3D).transform = visual
					motion._apply(pose)
					if not accepted and Time.get_ticks_usec()-slice_started >= budget_us:
						await get_tree().process_frame
						slice_started = Time.get_ticks_usec()
						budget_us = fit_budget_usec(get_process_delta_time())
					if accepted or neighbour_blocked or not available(): break
				if accepted or neighbour_blocked or not available(): break
		actor.global_transform = saved
		(actor.get_node("VisualRoot") as Node3D).transform = visual
		motion._apply(pose)
		if not accepted and Time.get_ticks_usec()-slice_started >= budget_us:
			await get_tree().process_frame
			slice_started = Time.get_ticks_usec()
			budget_us = fit_budget_usec(get_process_delta_time())
		accepted = accepted and available()
		if accepted or neighbour_blocked or not available():
			if accepted:
				if fit_cache.size() >= 32: fit_cache.erase(fit_cache.keys()[0])
				fit_cache[fit_key] = {"offset":offset,"rise":motion.rise_scale,"arc":motion.arc_clearance}
				if swivel != null: fit_cache[fit_key]["turn_delta"] = _desk_turn_delta
				actor.set_meta("seated_fit_cache",fit_cache)
				print("DIRECT_SEAT_FIT arc=",motion.arc_clearance," rise=",motion.rise_scale," offset=",offset," support_y=",support.offset," turn_delta=",_desk_turn_delta if swivel != null else 0.0)
			break
	motion.tail_weight = 0.0
	actor.set_physics_process(true)
	actor.set_process(true)
	_checking_fit = false
	return accepted and available()

func _trace_fit_rejection(phase: String, offset: Vector2, leaving: bool = false,
	amount: float = -1.0, previous: Transform3D = Transform3D.IDENTITY, neighbour_stop: bool = false) -> void:
	if not _fit_trace_enabled: return
	var obstacle := str(motion.last_obstacle) if phase != "support" else "no seat support"
	# Swept queries do not identify a collider; do not label a prior hit as it.
	var confirmed := phase != "support" and not obstacle.begins_with("swept ") and not obstacle.begins_with("desk-turn swept")
	var collider := motion.last_collider as Node if confirmed else null
	var own_carrier := false
	if is_instance_valid(collider) and swivel != null:
		own_carrier = swivel.is_ancestor_of(collider)
		if collider is PhysicsBody3D:
			own_carrier = own_carrier or (collider as PhysicsBody3D).get_rid() in swivel.excluded
	print("DIRECT_SEAT_FIT_REJECT ",JSON.stringify({"species":actor.species_id,"phase":phase,
		"offset":[offset.x,offset.y],"rise":motion.rise_scale,"arc":motion.arc_clearance,
		"leaving":leaving,"amount":amount,"obstacle":obstacle,
		"collider_path":str(collider.get_path()) if is_instance_valid(collider) else "",
		"collider_class":collider.get_class() if is_instance_valid(collider) else "",
		"own_carrier":own_carrier,"neighbour_stop":neighbour_stop,
		"previous":str(previous),"actor_frame":str(actor.global_transform),
		"visual_frame":str((actor.get_node("VisualRoot") as Node3D).transform),
		"start_frame":str(motion.start_frame),"end_frame":str(motion.end_frame),
		"open_angle":open_angle,"carrier_angle":swivel.rotation.y if swivel != null else null,
		"desk_turn_delta":_desk_turn_delta,
		"turn":_fit_trace_turn if phase == "desk_turn" else {}}))

func seat_support(height: float, frame: Transform3D) -> Dictionary:
	# Use the actual underside of the visible pelvis, not one rig's groin
	# centroid. Long-bodied species can rest their rump while the thighs
	# naturally project past the front edge of the cushion.
	var closest := INF
	for local: Vector3 in _support_points:
		var point := frame * local
		if absf(point.y-height) > 0.20: continue
		var from := Vector3(point.x,height+0.15,point.z)
		var to := Vector3(point.x,height-0.15,point.z)
		var ray := PhysicsRayQueryParameters3D.create(from,to,actor.collision_mask)
		ray.exclude = [actor.get_rid()]
		var hit := actor.get_world_3d().direct_space_state.intersect_ray(ray)
		if hit.is_empty() or absf((hit.position as Vector3).y-height) > 0.08: continue
		closest = minf(closest,point.y-(hit.position as Vector3).y)
	if not is_finite(closest) or absf(closest) > 0.18: return {}
	return {"offset":0.008-closest}

func hop(leaving: bool) -> bool:
	var elapsed := 0.0
	var duration := float(PROFILE.get_meta("leave_seconds" if leaving else "hop_seconds"))
	var started_usec := Time.get_ticks_usec()
	while elapsed < duration:
		await get_tree().physics_frame
		if not available(): return false
		var target_elapsed := minf(duration,float(Time.get_ticks_usec()-started_usec)/1000000.0 * Engine.time_scale)
		while elapsed < target_elapsed:
			elapsed = minf(target_elapsed,elapsed+1.0/60.0)
			var previous := actor.global_transform
			if leaving: motion.sample_exit(elapsed/duration)
			else: motion.sample(elapsed/duration)
			if not motion.clear_path(previous,actor.global_transform,elapsed/duration,leaving):
				actor.global_transform = previous
				return false
	return true

func _exit_tree() -> void:
	var profile := {}
	for phase: String in _frame_ms:
		var times: Array = _frame_ms[phase]
		times.sort()
		if not times.is_empty(): profile[phase] = {"frames":times.size(),"p50_ms":times[int((times.size()-1)*0.5)],"p95_ms":times[int((times.size()-1)*0.95)],"max_ms":times.back()}
	print("DIRECT_SEAT_FRAME_PROFILE ",JSON.stringify(profile))
	for phase: String in _engine_work:
		var work: Dictionary = _engine_work[phase]
		for key: String in ["process","physics"]:
			var samples: Array = work[key]
			samples.sort()
			work[key] = {"p50_ms":samples[int((samples.size()-1)*0.5)],"p95_ms":samples[int((samples.size()-1)*0.95)]}
	print("DIRECT_SEAT_ENGINE_PROFILE ",JSON.stringify(_engine_work))
	_finish()

func fit_seated_turn(hint: Dictionary = {}, offset: Vector2 = Vector2.ZERO) -> bool:
	# A half-open chair has two physical return arcs. Keep the pose fixed while
	# testing both, rather than forcing a direction from the Euler representation.
	var routes: Array[float] = []
	if is_equal_approx(absf(open_angle),PI): routes.assign([PI,-PI])
	else: routes.append(-open_angle)
	if hint.has("turn_delta"):
		for route: float in routes.duplicate():
			if is_equal_approx(route,float(hint.turn_delta)):
				routes.erase(route); routes.push_front(route)
	for route: float in routes:
		if not available(): return false
		_desk_turn_delta = route
		if await seated_desk_clear(): return true
		_trace_fit_rejection("desk_turn",offset)
	return false

func seated_desk_clear() -> bool:
	# Validate the same signed arc as turn_to(), not just its final pose. A foot
	# can hit a drawer midway even when both the landing and desk pose are clear.
	var start := swivel.rotation.y
	var target := desk_target()
	var local: Transform3D = swivel.global_transform.affine_inverse()*motion.end_frame
	var previous: Transform3D = motion.end_frame
	var steps := maxi(1,ceili(absf(target-start)/(0.65/60.0)))
	var slice_started := Time.get_ticks_usec()
	var budget_us := fit_budget_usec(get_process_delta_time())
	if _fit_trace_enabled: _fit_trace_turn.clear()
	for index in range(steps+1):
		if not available(): return false
		var angle := lerpf(start,target,float(index)/steps)
		var carrier_frame := Transform3D(Basis(Vector3.UP,angle),swivel.global_position)
		var frame := carrier_frame*local
		var clear: bool = swivel._clear(carrier_frame,actor)
		if not clear:
			motion.last_collider = null
			motion.last_obstacle = "chair-turn / "+str(swivel.last_obstacle)
		else:
			clear = _seated_turn_frame_clear(previous,frame)
		if not clear:
			if _fit_trace_enabled:
				_fit_trace_turn = {"start_angle":start,"target_angle":target,"angle":angle,
					"index":index,"steps":steps,"previous":str(previous),"frame":str(frame)}
			return false
		previous = frame
		if Time.get_ticks_usec()-slice_started >= budget_us:
			await get_tree().process_frame
			slice_started = Time.get_ticks_usec()
			budget_us = fit_budget_usec(get_process_delta_time())
	return available()

func _seated_turn_frame_clear(previous: Transform3D, frame: Transform3D) -> bool:
	var omit: Array[RID] = swivel.excluded.duplicate()
	omit.append(actor.get_rid())
	var space := actor.get_world_3d().direct_space_state
	for shape: Shape3D in motion.seated_shapes:
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = shape
		query.transform = previous
		query.collision_mask = actor.collision_mask
		query.exclude = omit
		query.margin = 0.001
		query.motion = frame.origin-previous.origin
		var fraction := space.cast_motion(query)
		if fraction.size() != 2 or fraction[0] < 1.0:
			motion.last_obstacle = "desk-turn swept path / "+str(shape.get_meta("body_region","body"))
			return false
		query.motion = Vector3.ZERO
		query.transform = frame
		var hits := space.intersect_shape(query,1)
		if not hits.is_empty():
			motion.last_collider = hits[0].collider as Node
			motion.last_obstacle = "desk-turn pose / "+str(shape.get_meta("body_region","body"))+" / "+str(motion.last_collider.get_meta("source_node",motion.last_collider.name))
			return false
	return true
