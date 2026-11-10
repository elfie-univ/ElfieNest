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
var entry := Transform3D.IDENTITY
var waiting := Transform3D.IDENTITY
var _support_points: Array[Vector3] = []
var _bound := false
var _fit_source_id := 0
var _checking_fit := false
var _frame_ms: Dictionary = {}
var _previous_frame_usec := 0
var _engine_work: Dictionary = {}

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
	return {"status":"cancelled" if actor.cycle_cancelled else "failed","reason":reason}

func standing_floor(point: Vector3) -> float:
	var ray := PhysicsRayQueryParameters3D.create(point+Vector3.UP*0.25,point-Vector3.UP*0.30,actor.collision_mask)
	ray.exclude = [actor.get_rid()]
	var hit := actor.get_world_3d().direct_space_state.intersect_ray(ray)
	if not hit.is_empty() and (hit.normal as Vector3).y > 0.7:
		return (hit.position as Vector3).y+0.02
	return point.y

func walk(point: Vector3) -> bool:
	if not available(): return false
	var route := NavigationServer3D.map_get_path(actor.get_world_3d().navigation_map,actor.global_position,point,true)
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
		var base_name := str(source.get_meta("extras",{}).get("source_name",source.name))
		var bounds := source.global_transform*source.get_aabb()
		for mesh: MeshInstance3D in geometry.find_children("*","MeshInstance3D",true,false):
			if mesh.has_meta("source_geometry_path"): continue
			if str(mesh.name).begins_with(base_name+"_"):
				bounds = bounds.merge(mesh.global_transform*mesh.get_aabb())
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
	var floor_point := NavigationServer3D.map_get_closest_point(actor.get_world_3d().navigation_map,waiting.origin)
	if floor_point.distance_to(waiting.origin) < 0.35:
		waiting.origin.x = floor_point.x
		waiting.origin.z = floor_point.z
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	var locomotion := CLIPS.locomotion_for(actor)
	var library := CLIPS.library_for(actor)
	if locomotion == null or library == null: return failed("direct_seat_retarget_missing")
	var hand_rest := PROFILE.get_meta("hand_rest") as Vector3
	if actor.species_id == "saevi": hand_rest = Vector3(0.23,0.05,0.06)
	HANDS.bake(library.get_animation("seated_idle"),actor,hand_rest)
	var merged := player.get_animation_library("").duplicate() as AnimationLibrary
	for key: String in ["idle","walking"]:
		if merged.has_animation(key): merged.remove_animation(key)
		merged.add_animation(key,locomotion.get_animation(key))
	player.remove_animation_library("")
	player.add_animation_library("",merged)
	if player.has_animation_library("chair"): player.remove_animation_library("chair")
	player.add_animation_library("chair",library)
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
		if not await swivel.turn_to(boarding_angle,null): return failed(swivel.last_obstacle)
		# +PI and -PI are the same pose, but select opposite half-turns.
		# Reuse the actual opening representation for the return trip.
		open_angle = swivel.rotation.y
	if not await fit_landing(opened): return failed("direct_seat_fit_blocked: "+str(motion.last_obstacle))
	stage("approach_seat")
	if not await walk(entry.origin): return failed("direct_seat_approach_blocked")
	actor.set_physics_process(false)
	actor.set_process(false)
	motion.capture_entry_pose()
	stage("tail_tuck")
	for i in range(40):
		await get_tree().physics_frame
		if not available(): return failed("cancelled")
		motion.tail_weight = smoothstep(0.0,1.0,float(i+1)/40.0)
		motion._apply_tail()
	stage("turn_on_floor")
	var heading := actor.global_basis.get_rotation_quaternion()
	for i in range(36):
		await get_tree().physics_frame
		if not available(): return failed("cancelled")
		var amount := smoothstep(0.0,1.0,float(i+1)/36.0)
		actor.global_basis = Basis(heading.slerp(entry.basis.get_rotation_quaternion(),amount))
		motion.blend_ground_pose(amount)
	CONTACT.ground(actor,entry.origin.y)
	(actor.get_node("CollisionShape3D") as CollisionShape3D).disabled = true
	stage("direct_seated_hop")
	if not await hop(false): return failed("direct_seat_hop_blocked: "+str(motion.last_obstacle))
	motion.install_seated_collision()
	if swivel != null:
		stage("chair_turn_to_desk")
		if not await swivel.turn_to(0.0,actor): return failed(swivel.last_obstacle)
	stage("seated_idle")
	var elapsed := 0.0
	while elapsed < 3.0:
		await get_tree().physics_frame
		if not available(): return failed("cancelled")
		elapsed += get_physics_process_delta_time()
	if swivel != null:
		stage("chair_turn_to_exit")
		if not await swivel.turn_to(open_angle,actor): return failed(swivel.last_obstacle)
	stage("direct_seated_exit")
	if not await hop(true): return failed("direct_seat_exit_blocked: "+str(motion.last_obstacle))
	for i in range(24):
		await get_tree().physics_frame
		if not available(): return failed("cancelled")
		motion.tail_weight = 1.0-float(i+1)/24.0
		motion.sample(0.0)
	motion.release()
	_bound = false
	stage("leave_seat")
	if not await walk(waiting.origin): return failed("direct_seat_leave_blocked")
	return {"status":"completed","reason":""}

func fit_landing(contact: Transform3D) -> bool:
	_checking_fit = true
	# Fit the same motion to the actual body and seat. Never move furniture,
	# shrink a body hull or accept a landing without a supporting seat surface.
	var saved := actor.global_transform
	var visual := (actor.get_node("VisualRoot") as Node3D).transform
	var pose: Array[Transform3D] = motion._capture()
	var base: Vector3 = motion.end_frame.origin
	var accepted := false
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
		if accepted:
			motion.end_frame.origin.y += float(support.offset)
			motion.sample(1.0)
			accepted = motion.clear_path(actor.global_transform,actor.global_transform,1.0)
			if accepted and swivel != null: accepted = seated_desk_clear()
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
					var previous: Transform3D = motion.start_frame
					for index in range(65):
						motion.sample(float(index)/64.0)
						if not motion.clear_path(previous,actor.global_transform,float(index)/64.0):
							accepted = false
							neighbour_blocked = swivel != null and is_instance_valid(motion.last_collider) and not motion.last_collider is AnimatableBody3D and str(motion.last_collider.get_meta("source_node","")).contains("Chair")
							break
						previous = actor.global_transform
						if index % 8 == 7:
							actor.global_transform = saved
							(actor.get_node("VisualRoot") as Node3D).transform = visual
							motion._apply(pose)
							await get_tree().process_frame
							if not available():
								accepted = false
								break
					actor.global_transform = saved
					(actor.get_node("VisualRoot") as Node3D).transform = visual
					motion._apply(pose)
					await get_tree().process_frame
					if accepted or neighbour_blocked or not available(): break
				if accepted or neighbour_blocked or not available(): break
		actor.global_transform = saved
		(actor.get_node("VisualRoot") as Node3D).transform = visual
		motion._apply(pose)
		await get_tree().process_frame
		if accepted or neighbour_blocked or not available():
			if accepted:
				if fit_cache.size() >= 32: fit_cache.erase(fit_cache.keys()[0])
				fit_cache[fit_key] = {"offset":offset,"rise":motion.rise_scale,"arc":motion.arc_clearance}
				actor.set_meta("seated_fit_cache",fit_cache)
				print("DIRECT_SEAT_FIT arc=",motion.arc_clearance," rise=",motion.rise_scale," offset=",offset," support_y=",support.offset)
			break
	motion.tail_weight = 0.0
	actor.set_physics_process(true)
	actor.set_process(true)
	_checking_fit = false
	return accepted and available()

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
	while elapsed < duration:
		await get_tree().physics_frame
		if not available(): return false
		elapsed = minf(duration,elapsed+get_physics_process_delta_time())
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
	if not is_instance_valid(actor): return
	if _bound:
		motion.tail_weight = 0.0
		motion.sample(0.0)
		motion.release()
	actor.remove_meta("furniture_cycle_stage")

func seated_desk_clear() -> bool:
	# Check the final desk-facing pose before accepting an airborne route.
	# This uses the same full skin hulls and exclusions as the actual swivel.
	var frame: Transform3D = Transform3D(Basis.IDENTITY,swivel.global_position)*swivel.global_transform.affine_inverse()*motion.end_frame
	var omit: Array[RID] = swivel.excluded.duplicate()
	omit.append(actor.get_rid())
	for shape: Shape3D in motion.seated_shapes:
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = shape
		query.transform = frame
		query.collision_mask = actor.collision_mask
		query.exclude = omit
		query.margin = 0.001
		var hits := actor.get_world_3d().direct_space_state.intersect_shape(query,1)
		if not hits.is_empty():
			motion.last_collider = hits[0].collider as Node
			motion.last_obstacle = "desk-facing "+str(shape.get_meta("body_region","body"))+" / "+str(motion.last_collider.get_meta("source_node",motion.last_collider.name))
			return false
	return true
