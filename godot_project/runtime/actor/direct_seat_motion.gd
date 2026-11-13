extends RefCounted
## One authored hop, fitted to a measured seat. No standing-on-seat phase.
const TRAVEL := preload("res://characters/animation/candidates/direct_seated_hop.tres")
const EXIT := preload("res://characters/animation/candidates/direct_seated_exit.tres")
const TAIL_POSE := preload("res://runtime/actor/seated_tail_pose.gd")
const LEG_POSE := preload("res://runtime/actor/chair_dog_leg_keys.gd")
var actor: ElfieActor
var skeleton: Skeleton3D
var standing: Array[Transform3D] = []
var sitting: Array[Transform3D] = []
var crouching: Array[Transform3D] = []
var incoming: Array[Transform3D] = []
var incoming_visual := Transform3D.IDENTITY
var standing_visual := Transform3D.IDENTITY
var start_frame := Transform3D.IDENTITY
var end_frame := Transform3D.IDENTITY
var tail_bone := -1
var tail_pose: RefCounted
var tail_weight := 0.0
var arc_clearance := 0.0
var rise_scale := 1.0
var pose_shapes: Array[Array] = []
var exit_shapes: Array[Array] = []
var seated_shapes: Array[Shape3D] = []
var _shape_builder: Callable
var _contact_sampler: Callable
var _saved_collision := Transform3D.IDENTITY
var _saved_shape: Shape3D
var _extra_shapes: Array[CollisionShape3D] = []
var last_obstacle := ""
var last_collider: Node

func bind(body: ElfieActor, contact: Transform3D, entry: Transform3D, profile: Resource, shape_builder: Callable, contact_sampler: Callable) -> String:
	actor = body
	skeleton = actor._furniture_hips()["skeleton"] as Skeleton3D
	_shape_builder = shape_builder
	_contact_sampler = contact_sampler
	var original_frame := actor.global_transform
	var original_visual := (actor.get_node("VisualRoot") as Node3D).transform
	var original_pose := _capture()
	actor.set_physics_process(false)
	actor.set_process(false)
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	# Keep the original visible pose and animation cursor while immutable
	# inputs compile. Background yields must not advance the fitting pose.
	player.pause()
	if not await preload("res://runtime/actor/furniture_seated_collision.gd").prepare_inputs(actor):
		actor.set_physics_process(true)
		actor.set_process(true)
		player.play("idle",0.0)
		return "cancelled"
	actor.global_transform = entry
	(actor.get_node("VisualRoot") as Node3D).rotation = Vector3.ZERO
	player.play("idle", 0.0)
	player.seek(0.0,true)
	player.advance(0.0)
	preload("res://runtime/actor/furniture_contact.gd").ground(actor,entry.origin.y)
	standing = _capture()
	standing_visual = (actor.get_node("VisualRoot") as Node3D).transform
	start_frame = entry
	_make_crouch()
	_apply(standing)
	for i in range(skeleton.get_bone_count()):
		if "tail" in String(skeleton.get_bone_name(i)).to_lower():
			tail_bone = i
			break
	if tail_bone < 0:
		return "tail_joint_missing"
	tail_pose = TAIL_POSE.new()
	var tail_error: String = tail_pose.bind(actor, skeleton, profile)
	if not tail_error.is_empty(): return tail_error
	player.play("chair/seated_idle", 0.0)
	player.seek(0.0,true)
	player.advance(0.0)
	player.pause()
	sitting = _capture()
	# Match the clip's facing to the standing actor without changing bone lengths.
	var hips := int(actor._furniture_hips()["bone"])
	var yaw := Basis(sitting[hips].basis.get_rotation_quaternion() * standing[hips].basis.get_rotation_quaternion().inverse()).get_euler().y
	sitting[hips].basis = Basis(Vector3.UP, -yaw) * sitting[hips].basis
	_apply(sitting)
	tail_weight = 1.0
	_apply_tail()
	var butt: Vector3 = _contact_sampler.call(actor)
	if not butt.is_finite():
		return "seated_skin_contact_missing"
	end_frame = Transform3D(entry.basis, entry.origin + contact.origin + Vector3.UP * float(profile.get_meta("seat_clearance")) - butt)
	var cache_key := _collision_cache_key(profile)
	var cached: Dictionary = actor.get_meta("seated_pose_cache",{})
	var cache_hit: bool = cached.get("key") == cache_key
	print("DIRECT_SEAT_CACHE hit=",cache_hit)
	if cache_hit:
		pose_shapes.assign(cached.incoming)
		exit_shapes.assign(cached.outgoing)
		seated_shapes.assign(pose_shapes.back())
	else:
		# Target a quarter of the observed frame time, bounded at 8–100 ms.
		# A native hull call completes atomically before the budget is checked.
		# Yielding after every pose otherwise adds 34 full garden renders.
		var budget_us := clampi(int(250000.0/maxf(Engine.get_frames_per_second(),1.0)),8000,100000)
		var slice_started := Time.get_ticks_usec()
		var unique_poses := {}
		for animation: Animation in [TRAVEL, EXIT]:
			var samples := pose_shapes if animation == TRAVEL else exit_shapes
			for index in range(17):
				var t := smoothstep(0.0, 1.0, float(index) / 16.0)
				var weights := _pose_weights(animation, t)
				if not unique_poses.has(weights):
					# Hulls are in actor coordinates. Translation along the arc only
					# enters the subsequent world-space overlap and sweep queries.
					actor.global_transform = start_frame
					(actor.get_node("VisualRoot") as Node3D).transform = standing_visual
					_apply_body_pose(weights)
					_apply_tail()
					unique_poses[weights] = _shape_builder.call(actor, true)
				samples.append(unique_poses[weights])
				if Time.get_ticks_usec() - slice_started >= budget_us:
					# Only the original visible pose may cross a rendered frame.
					actor.global_transform = original_frame
					(actor.get_node("VisualRoot") as Node3D).transform = original_visual
					_apply(original_pose)
					await actor.get_tree().process_frame
					slice_started = Time.get_ticks_usec()
					if not actor.cycle_available():
						actor.set_physics_process(true)
						actor.set_process(true)
						player.play("idle", 0.0)
						return "cancelled"
		seated_shapes.assign(pose_shapes.back())
		print("DIRECT_SEAT_HULLS unique=", unique_poses.size(), " samples=", pose_shapes.size() + exit_shapes.size())
		actor.set_meta("seated_pose_cache",{"key":cache_key,"incoming":pose_shapes.duplicate(),"outgoing":exit_shapes.duplicate()})
	tail_weight = 0.0
	_saved_shape = actor._collision_shape.shape
	_saved_collision = actor._collision_shape.transform
	actor.global_transform = original_frame
	(actor.get_node("VisualRoot") as Node3D).transform = original_visual
	_apply(original_pose)
	player.play("idle", 0.0)
	actor.set_physics_process(true)
	actor.set_process(true)
	return ""

func _make_crouch() -> void:
	var feet := {}
	for side: String in ["Left", "Right"]:
		var foot := skeleton.find_bone("mixamorig_" + side + "Foot")
		feet[side] = skeleton.global_transform * skeleton.get_bone_global_pose(foot)
	var hips := int(actor._furniture_hips()["bone"])
	skeleton.set_bone_pose_position(hips, skeleton.get_bone_pose_position(hips) + skeleton.global_basis.inverse() * Vector3.DOWN * 0.035)
	for side: String in ["Left", "Right"]:
		var upper := skeleton.find_bone("mixamorig_" + side + "UpLeg")
		var lower := skeleton.find_bone("mixamorig_" + side + "Leg")
		var foot := skeleton.find_bone("mixamorig_" + side + "Foot")
		var a := _point(upper)
		var b := _point(lower)
		var c := _point(foot)
		var target: Transform3D = feet[side]
		var first := a.distance_to(b)
		var second := b.distance_to(c)
		var distance := clampf(a.distance_to(target.origin), absf(first - second) + 0.001, first + second - 0.001)
		var direction := (target.origin - a).normalized()
		var along := (first * first + distance * distance - second * second) / (2.0 * distance)
		var pole := actor.global_basis.z - direction * actor.global_basis.z.dot(direction)
		var knee := a + direction * along + pole.normalized() * sqrt(maxf(0.0, first * first - along * along))
		LEG_POSE._rotate_toward(skeleton, upper, b - a, knee - a)
		LEG_POSE._rotate_toward(skeleton, lower, _point(foot) - _point(lower), target.origin - _point(lower))
		LEG_POSE._set_world_basis(skeleton, foot, target.basis)
	crouching = _capture()

func _point(bone: int) -> Vector3:
	return skeleton.to_global(skeleton.get_bone_global_pose(bone).origin)

func capture_entry_pose() -> void:
	incoming = _capture()
	incoming_visual = (actor.get_node("VisualRoot") as Node3D).transform
	(actor.get_node("AnimationPlayer") as AnimationPlayer).pause()

func blend_ground_pose(weight: float) -> void:
	for i in range(standing.size()):
		var pose := incoming[i].interpolate_with(standing[i], weight)
		skeleton.set_bone_pose_position(i, pose.origin)
		skeleton.set_bone_pose_rotation(i, pose.basis.orthonormalized().get_rotation_quaternion())
	(actor.get_node("VisualRoot") as Node3D).transform = incoming_visual.interpolate_with(standing_visual, weight)
	_apply_tail()

func _capture() -> Array[Transform3D]:
	var result: Array[Transform3D] = []
	for i in range(skeleton.get_bone_count()):
		result.append(skeleton.get_bone_pose(i))
	return result

func _apply(pose: Array[Transform3D]) -> void:
	for i in range(pose.size()):
		skeleton.set_bone_pose_position(i, pose[i].origin)
		skeleton.set_bone_pose_rotation(i, pose[i].basis.orthonormalized().get_rotation_quaternion())

func _apply_tail() -> void:
	if tail_pose != null:
		tail_pose.apply(tail_weight)

func tail_root_position() -> Vector3:
	return tail_pose.root_position()

func sample(amount: float) -> void:
	_sample(TRAVEL, amount, false)

func sample_exit(amount: float) -> void:
	_sample(EXIT, amount, true)

func _sample(animation: Animation, amount: float, leaving: bool) -> void:
	(actor.get_node("VisualRoot") as Node3D).transform = standing_visual
	var t := smoothstep(0.0, 1.0, clampf(amount, 0.0, 1.0))
	var travel := animation.position_track_interpolate(0, t)
	travel.x = clampf(travel.x, 0.0, 1.0)
	travel.y = maxf(travel.y, 0.0)
	_apply_body_pose(_pose_weights(animation, t))
	var from := end_frame.origin if leaving else start_frame.origin
	var to := start_frame.origin if leaving else end_frame.origin
	# Keep the pelvis forward of a narrow chair back while airborne. The
	# authored timing, poses and endpoint stay unchanged; never overshoot entry.
	var horizontal := Vector2(end_frame.origin.x-start_frame.origin.x,end_frame.origin.z-start_frame.origin.z).length()
	var remaining := horizontal * (1.0-travel.x if leaving else travel.x)
	var clearance := minf(travel.y * arc_clearance,remaining)
	actor.global_transform = Transform3D(start_frame.basis, from.lerp(to, travel.x) + Vector3.UP * travel.y * rise_scale + start_frame.basis.z * clearance)
	_apply_tail()

static func _pose_weights(animation: Animation, t: float) -> Array[float]:
	return [
		clampf(float(animation.value_track_interpolate(1, t)), 0.0, 1.0),
		clampf(float(animation.value_track_interpolate(2, t)), 0.0, 1.0)]

func _apply_body_pose(weights: Array[float]) -> void:
	var crouch := weights[0]
	var fold := weights[1]
	tail_pose.set("seated_weight", fold)
	for i in range(standing.size()):
		var pose := standing[i].interpolate_with(sitting[i], fold).interpolate_with(crouching[i], crouch)
		skeleton.set_bone_pose_position(i, pose.origin)
		skeleton.set_bone_pose_rotation(i, pose.basis.orthonormalized().get_rotation_quaternion())

func clear_path(previous: Transform3D, next: Transform3D, amount: float, leaving: bool = false) -> bool:
	last_obstacle = ""
	last_collider = null
	var index := clampi(int(round(amount * 16.0)), 0, 16)
	var space := actor.get_world_3d().direct_space_state
	var cache: Array[Array] = exit_shapes if leaving else pose_shapes
	for shape: Shape3D in cache[index]:
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = shape
		query.collision_mask = actor.collision_mask
		query.exclude = [actor.get_rid()]
		query.margin = 0.0
		query.transform = next
		var hits := space.intersect_shape(query, 1)
		if not hits.is_empty():
			var obstacle := hits[0]["collider"] as Node
			last_collider = obstacle
			last_obstacle = str(shape.get_meta("body_region", "body")) + " / " + str(obstacle.get_meta("source_node", obstacle.name))
			return false
		query.transform = previous
		query.motion = next.origin - previous.origin
		if query.motion.length() > 0.00001:
			var fraction := space.cast_motion(query)
			if fraction.size() != 2 or fraction[0] < 0.999:
				last_obstacle = "swept " + str(shape.get_meta("body_region", "body"))
				return false
	return true

func install_seated_collision() -> void:
	actor._collision_shape.transform = Transform3D.IDENTITY
	actor._collision_shape.shape = seated_shapes[0]
	actor._collision_shape.disabled = false
	for index in range(1, seated_shapes.size()):
		var node := CollisionShape3D.new()
		node.shape = seated_shapes[index]
		actor.add_child(node)
		_extra_shapes.append(node)

func release() -> void:
	for node in _extra_shapes:
		node.disabled = true
		node.queue_free()
	_extra_shapes.clear()
	actor._collision_shape.shape = _saved_shape
	actor._collision_shape.transform = _saved_collision
	actor._collision_shape.disabled = false
	actor.set_physics_process(true)
	actor.set_process(true)

func _collision_cache_key(profile: Resource) -> int:
	# Body identity is exact. Only derived pose roundoff from world-space IK
	# may reuse a signature (20 micrometres/radians, below contact clearance).
	var body: Array = [actor.species_id,actor._appearance_payload,profile.get_meta("hand_rest"),profile.get_meta("tail_joint_angles"),profile.get_meta("tail_seated_joint_angles")]
	# Animation Resources may unload with an action runner. Use their actual
	# key data, not a transient Resource instance ID, for the body signature.
	var animations: Array[Animation] = [TRAVEL,EXIT]
	for path: String in ["res://characters/animation/idle.fbx","res://characters/animation/candidates/Sitting Idle.fbx"]:
		var library := load(path) as AnimationLibrary
		animations.append(library.get_animation(library.get_animation_list()[0]))
	for animation: Animation in animations:
		body.append(animation.length)
		for track in range(animation.get_track_count()):
			body.append_array([animation.track_get_type(track),animation.track_get_path(track),animation.track_get_interpolation_type(track)])
			for key in range(animation.track_get_key_count(track)):
				body.append_array([animation.track_get_key_time(track,key),animation.track_get_key_transition(track,key),animation.track_get_key_value(track,key)])
	for bone in range(skeleton.get_bone_count()): body.append(skeleton.get_bone_rest(bone))
	for mesh: MeshInstance3D in actor.find_children("*","MeshInstance3D",true,false):
		if mesh.skin != null and mesh.mesh != null: body.append(mesh.mesh.get_instance_id()); body.append(mesh.skin.get_instance_id())
	var body_key := hash(body)
	# The cached poses are compiled from these authored clips and this body,
	# not from the transient idle/tail pose left by the preceding action.
	var values: Array[Vector3] = [(actor.get_node("VisualRoot") as Node3D).scale]
	for bone in range(skeleton.get_bone_count()): values.append(skeleton.get_bone_pose_scale(bone))
	var previous: Dictionary = actor.get_meta("seated_cache_signature",{})
	if previous.get("body") == body_key and (previous["values"] as Array).size() == values.size():
		var same := true
		for index in range(values.size()):
			if values[index].distance_to(previous["values"][index]) > 0.00002:
				same = false
				break
		if same: return int(previous.key)
	var key := hash([body_key,values])
	actor.set_meta("seated_cache_signature",{"body":body_key,"values":values,"key":key})
	return key
