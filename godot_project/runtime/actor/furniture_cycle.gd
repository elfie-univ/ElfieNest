extends Node
## Production-owned approved furniture motion. The Lab only submits a semantic target.
const CLIPS := preload("res://runtime/actor/chair_clip_sequence.gd")
const CONTACT := preload("res://runtime/actor/furniture_contact.gd")
const PLAN := preload("res://runtime/actor/furniture_motion_plan.gd")
var actor: ElfieActor
var stage := ""
var swivel: Node3D
var sleep: Node3D
var _cloth: MeshInstance3D
var _cloth_mesh: Mesh
var _command := ""

func run(body: ElfieActor, marker: Marker3D, anchor_id: String, variant: String, nest: ModularNest) -> Dictionary:
	actor = body
	_command = str(actor.get("furniture_cycle_command"))
	var error := ElfieActor.furniture_marker_error(marker)
	if not error.is_empty(): return _result("failed", error)
	if variant.begins_with("sleep-"):
		if str(marker.get_meta("kind")) != "bed": return _result("failed", "sleep_requires_bed")
		return await _sleep(marker, anchor_id, variant, nest)
	if variant != "seat" or str(marker.get_meta("kind")) != "chair": return _result("failed", "seat_requires_chair")
	return await _seat(marker, nest)

func _stage(value: String) -> void:
	stage = value
	actor.set_meta("furniture_cycle_stage", value)
	print("FURNITURE_CYCLE ", JSON.stringify({"actor_id":actor.elfie_id,"command_id":_command,"stage":value}))

func _result(status: String, reason: String = "") -> Dictionary:
	return {"status":status, "reason":reason}

func _failure(reason: String) -> Dictionary:
	return _result("cancelled" if bool(actor.get("cycle_cancelled")) else "failed", reason)

func _available() -> bool:
	return bool(actor.call("cycle_available"))

func _dock(point: Vector3) -> bool:
	if not _available(): return false
	print("FURNITURE_DOCK from=", actor.global_position, " target=", point)
	actor.call("walk_precisely", point)
	var terminal: Signal = actor.get("precision_terminal")
	var result: Array = await terminal
	if not bool(result[0]):
		print("FURNITURE_DOCK_BLOCKED actual=", actor.global_position, " reason=", result[1])
		for index in range(actor.get_slide_collision_count()):
			var collider := actor.get_slide_collision(index).get_collider() as Node
			print("FURNITURE_DOCK_OBSTACLE ", collider.get_meta("source_node", collider.name))
	return bool(result[0]) and _available()

func _play(key: String, repeats: int = 1) -> bool:
	if not _available(): return false
	_stage(key)
	if not bool(actor.call("start_clip", key, repeats)): return false
	var terminal: Signal = actor.get("clip_terminal")
	var result: Array = await terminal
	if not bool(result[1]): actor.set("cycle_error", str(result[2]))
	return bool(result[1]) and _available()

func _wait(seconds: float) -> bool:
	var elapsed := 0.0
	while elapsed < seconds:
		await get_tree().physics_frame
		if not _available(): return false
		elapsed += get_physics_process_delta_time()
	return true

func _seat(marker: Marker3D, nest: ModularNest) -> Dictionary:
	if str(marker.get_meta("furniture_type", "")) == "bench":
		return await _bench(marker)
	var geometry := nest.get_node("Generated/CompleteEstate") as Node3D
	var physics := nest.get("_estate_physics") as Node3D
	if physics == null or physics.get_node_or_null("StaticGeometry") == null: return _result("failed", "world_physics_unavailable")
	var sofa := str(marker.get_meta("furniture_type", "")) == "sofa"
	var contact := marker.get_meta("interaction_transform") as Transform3D
	var source := marker.get_meta("furniture_source", geometry.find_child(str(marker.get_meta("source_node", "")), true, false)) as MeshInstance3D
	if not sofa and source == null: return _result("failed", "seat_source_unavailable")
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	# The approved sequence measured the species-rest locomotion, not raw FBX hips.
	var locomotion := CLIPS.locomotion_for(actor)
	if locomotion == null: return _result("failed", "locomotion_retarget_unavailable")
	var merged := player.get_animation_library("").duplicate() as AnimationLibrary
	for key: String in ["idle", "walking"]:
		if merged.has_animation(key): merged.remove_animation(key)
		merged.add_animation(key, locomotion.get_animation(key))
	player.remove_animation_library("")
	player.add_animation_library("", merged)
	player.play("idle")
	player.advance(0.0)
	CONTACT.ground(actor, marker.global_position.y)
	var library := _library(actor, sofa)
	if library == null: return _result("failed", "furniture_retarget_unavailable")
	if player.has_animation_library("chair"): player.remove_animation_library("chair")
	player.add_animation_library("chair", library)
	var probe := (load(actor.scene_file_path) as PackedScene).instantiate() as ElfieActor
	probe.visible = false
	add_child(probe)
	probe.remove_from_group(&"runtime_elfie_actors")
	var initial_player := probe.get_node("AnimationPlayer") as AnimationPlayer
	initial_player.remove_animation_library("")
	initial_player.add_animation_library("", merged)
	probe.configure("furniture-measurement", Vector3.ZERO, actor.get("_appearance_payload"))
	var probe_player := probe.get_node("AnimationPlayer") as AnimationPlayer
	probe_player.add_animation_library("chair", library)
	var measured := PLAN.measure(probe)
	probe.free()
	if measured.is_empty(): return _result("failed", "furniture_measurement_unavailable")
	actor.set("seated_shape_cache", measured.get("seated_shapes", []))
	if not sofa:
		var extras := source.get_meta("extras", {}) as Dictionary
		if extras.get("assembly") != "chair": return _result("failed", "seat_cycle_not_adapted")
		# Keep the actual chair's outward frame, using its matching back mesh.
		for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
			var e := mesh.get_meta("extras", {}) as Dictionary
			if e.get("module") == extras.get("module") and e.get("resident") == extras.get("resident") and e.get("source_name") == "Chair | central tall back petal":
				var forward := contact.origin - (mesh.global_transform * mesh.get_aabb()).get_center()
				forward.y = 0
				contact.basis = Basis(Vector3.UP, atan2(forward.x,forward.z))
		swivel = marker.get_meta("furniture_carrier") as Node3D if marker.has_meta("furniture_carrier") else null
		if swivel == null:
			swivel = preload("res://runtime/actor/chair_swivel.gd").new()
			# The carrier belongs to the scene and remains after this command.
			nest.add_child(swivel)
			swivel.install(geometry, physics, contact, str(extras.get("module")), str(extras.get("resident")))
			marker.set_meta("furniture_carrier", swivel)
			marker.set_meta("furniture_source", source)
		_stage("chair_turn_out")
		if not await swivel.turn_to(PI, null): return _failure("chair_rotation_blocked: " + swivel.last_obstacle)
		contact.basis = swivel.global_basis * contact.basis
		contact.origin += contact.basis.z * float(preload("res://characters/animation/candidates/dog_chair_contact_edits.tres").get_meta("seat_forward_offset"))
	var approach := PLAN.approach(contact, measured)
	approach.origin.y = marker.global_position.y
	# Preview starts at the measured mounting entrance. Navigation may project
	# a generic sofa marker across its coffee table; that is not this clip's
	# approach path. The remaining docking and clip still use real collisions.
	if sofa and bool(nest.get_meta("lab_action_preview", false)):
		actor.global_position = approach.origin - approach.basis.z * 0.4
		actor.velocity = Vector3.ZERO
	_stage("approach_seat")
	if not await _dock(approach.origin - approach.basis.z * 0.4) or not await _dock(approach.origin): return _failure("seat_approach_blocked")
	if not await _wait(0.35): return _failure("cancelled")
	if sofa:
		CONTACT.ground(actor, actor.global_position.y)
		var height_delta := contact.origin.y - actor.global_position.y - (measured["contact_offset"] as Vector3).y
		PLAN.fit_sofa_mount(library, actor, height_delta)
		print("SOFA_MOUNT_FIT delta_m=", height_delta)
	actor.call("begin_sequence", CONTACT.butt_point(actor).y)
	for key: String in ["step_up", "turn_left_90", "turn_left_90", "sit_down", "seated_idle", "stand_up", "jump_down"]:
		if not await _play(key, 4 if key == "seated_idle" else 1): return _failure(str(actor.get("cycle_error")))
		if key == "seated_idle":
			var offset := CONTACT.butt_point(actor) - contact.origin
			print("SEAT_CONTACT error_m=", offset)
			if absf(offset.y) > 0.04 or Vector2(offset.x,offset.z).length() > 0.16: return _result("failed", "seat_contact_mismatch: " + str(offset))
			if swivel != null:
				if not bool(actor.call("use_seated_collision")): return _result("failed", "seated_collision_unavailable")
				_stage("chair_turn_to_desk")
				if not await swivel.turn_to(0.0, actor): return _failure(swivel.last_obstacle)
				if not await _wait(3.0): return _failure("cancelled")
				_stage("chair_turn_to_exit")
				if not await swivel.turn_to(PI, actor): return _failure(swivel.last_obstacle)
				actor.call("clear_seated_collision")
	actor.call("end_sequence")
	_stage("leave_seat")
	# Return along the measured clear mounting path, as the approved sofa tour
	# does; the generic furniture marker may lie behind a nearby coffee table.
	var exit := approach.origin - approach.basis.z * 0.4 if sofa else marker.global_position
	if sofa:
		# Larger species need more clearance from the coffee table. Choose a
		# clear point on the same mounting segment; never disable collisions.
		var query := PhysicsShapeQueryParameters3D.new()
		var shape := actor.get_node("CollisionShape3D") as CollisionShape3D
		query.shape = shape.shape
		query.collision_mask = actor.collision_mask
		query.exclude = [actor.get_rid()]
		for distance: float in [0.4, 0.35, 0.3, 0.25, 0.2]:
			var candidate := approach.origin - approach.basis.z * distance
			query.transform = Transform3D(actor.global_basis, candidate) * shape.transform
			if actor.get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty():
				exit = candidate
				break
	if not await _dock(exit): return _failure("seat_exit_blocked")
	return _result("completed")

func _bench(marker: Marker3D) -> Dictionary:
	var error := actor.enter_furniture(marker, str(marker.get_meta("anchor_id", "")))
	if not error.is_empty(): return _result("failed", error)
	_stage("sit_down")
	if not await _wait(0.7): return _failure("cancelled")
	_stage("seated_idle")
	if not await _wait(2.0): return _failure("cancelled")
	_stage("stand_up")
	if not actor.leave_furniture(): return _result("failed", "bench_exit_blocked")
	if not await _wait(0.7): return _failure("cancelled")
	return _result("completed")

func _library(body: ElfieActor, sofa: bool) -> AnimationLibrary:
	var result := CLIPS.library_for(body, true)
	if result == null or not sofa: return result
	var edits := preload("res://characters/animation/candidates/dog_sofa_contact_edits.tres") as AnimationLibrary
	var skeleton := body._furniture_hips()["skeleton"] as Skeleton3D
	var path := NodePath("Skeleton3D:" + str(skeleton.get_bone_name(int(body._furniture_hips()["bone"]))))
	for key: String in edits.get_animation_list():
		var clip := result.get_animation(key)
		var correction := edits.get_animation(key)
		var track := clip.find_track(path, Animation.TYPE_POSITION_3D)
		for index in range(clip.track_get_key_count(track)):
			var time := clip.track_get_key_time(track,index)
			clip.track_set_key_value(track,index,(clip.track_get_key_value(track,index) as Vector3) + skeleton.global_basis.inverse() * correction.position_track_interpolate(0,time))
	var idle := CLIPS.locomotion_for(body).get_animation("idle")
	preload("res://runtime/actor/chair_dog_leg_keys.gd").bake(result.get_animation("turn_left_90"), "turn_left_90", body, idle, edits.get_meta("turn_ankle_lift") as Vector2)
	return result

func _sleep(marker: Marker3D, anchor_id: String, variant: String, nest: ModularNest) -> Dictionary:
	var source := nest.get_node("Generated/CompleteEstate").find_child(str(marker.get_meta("source_node", "")),true,false) as MeshInstance3D
	if source == null: return _result("failed", "bed_source_unavailable")
	var e := source.get_meta("extras", {}) as Dictionary
	for mesh: MeshInstance3D in nest.get_node("Generated/CompleteEstate").find_children("*","MeshInstance3D",true,false):
		var extras := mesh.get_meta("extras", {}) as Dictionary
		if extras.get("module") == e.get("module") and extras.get("resident") == e.get("resident") and extras.get("piece") == "bed_cover": _cloth = mesh
	if _cloth == null: return _result("failed", "authored_duvet_unavailable")
	var error := actor.enter_furniture(marker,anchor_id)
	if not error.is_empty(): return _result("failed",error)
	_cloth_mesh = _cloth.mesh
	sleep = preload("res://runtime/actor/sleep_cycle.gd").new()
	add_child(sleep)
	sleep.bind(actor,_cloth,null)
	sleep.set_process(false)
	sleep.set_mode("back" if variant == "sleep-back" else ("side-left" if variant == "sleep-left" else "side-right"))
	var seconds := 1.5
	if bool(nest.get_meta("lab_action_preview", false)):
		seconds = clampf(float(actor.get_meta("preview_sleep_start", 1.5)), 1.5, 15.5)
		actor.remove_meta("preview_sleep_start")
	var last := ""
	while seconds < 16.0:
		sleep.sample_bedding(seconds)
		if sleep.animation_stage != last:
			last = sleep.animation_stage
			_stage(last)
		await get_tree().process_frame
		if not _available(): return _failure("sleep_cancelled")
		seconds += get_process_delta_time()
	sleep.sample_bedding(16.0)
	if not actor.leave_furniture(): return _result("failed","bed_exit_blocked")
	_stage("leave_and_lay_back")
	return _result("completed")

func _exit_tree() -> void:
	if is_instance_valid(_cloth) and _cloth_mesh != null: _cloth.mesh = _cloth_mesh
	if is_instance_valid(actor): actor.remove_meta("furniture_cycle_stage")
