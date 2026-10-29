extends "res://runtime/lab/sofa_world_review.gd"
## One continuous dog tour; shares one AnimationLibrary across all three seats.

var _tour_world: Node3D
var completed_seats: Array[String] = []
var stairs_up := false
var stairs_down := false
var _stair_leg := ""
var _stair_sources: Dictionary = {}
var _seat_index := -1
var _follow_offset := Vector3(2.5, 1.8, 3.4)
var _orbit_offset := Vector3(2.5, 1.8, 3.4)
var _focus := Vector3.ZERO
var _ready_camera := false
var _camera_side := false
signal tour_checkpoint(title: String)


func setup(nest: Node3D, characters: Node3D) -> void:
	nest.set_process_unhandled_input(false)
	_build_controls()
	_tour_world = preload("res://runtime/lab/estate_tour_room.gd").new()
	add_child(_tour_world)
	if not await _tour_world.build():
		_phase = "BLOCKED: original route or sofa missing"
		return
	_actor = create_actor()
	characters.add_child(_actor)
	_player = _actor.get_node("AnimationPlayer") as AnimationPlayer
	_player.add_animation_library("", CLIPS.locomotion_for(_actor))
	# The very same library is used by the three seats; no seat-specific poses.
	_player.add_animation_library("chair", _library(_actor))
	var first: Transform3D = _tour_world.seats[0]["contact"]
	_start = first.origin + Vector3(1.8, 0, 1.9)
	_start.y = 0.3
	_actor.configure("connected-tour-dog", _start)
	CONTACT.ground(_actor, 0.3)
	var probe := create_actor()
	characters.add_child(probe)
	var player := probe.get_node("AnimationPlayer") as AnimationPlayer
	player.add_animation_library("", CLIPS.locomotion_for(probe))
	player.add_animation_library("chair", _player.get_animation_library("chair"))
	probe.configure("hidden-common-seat-measurement", Vector3.ZERO)
	_measured_motion = PLAN.measure(probe)
	probe.free()
	if _measured_motion.is_empty():
		_phase = "BLOCKED: shared motion measurement failed"
		return
	_camera = Camera3D.new()
	add_child(_camera)
	_camera.near = 0.03
	_camera.fov = 58
	_focus = _actor.global_position + Vector3.UP * 0.7
	_camera.global_position = _actor.global_position + _follow_offset
	_camera.look_at(_focus)
	_camera.make_current()
	_ready_camera = true
	# Register the new NavigationAgent before the first navigation command.
	await get_tree().physics_frame
	await get_tree().physics_frame
	_phase = "READY / walk > stairs up/down > 3 sofas"


func _build_controls() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	if OS.has_feature("web"): layer.scale = Vector2.ONE * float(JavaScriptBridge.eval("window.devicePixelRatio || 1"))
	var panel := PanelContainer.new()
	panel.position = Vector2(10, 10)
	layer.add_child(panel)
	var box := VBoxContainer.new()
	panel.add_child(box)
	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 14)
	_label.custom_minimum_size.x = 350
	_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_label)
	var play := Button.new()
	play.text = "Play full tour / replay"
	play.pressed.connect(_run_trial)
	box.add_child(play)
	var row := HBoxContainer.new()
	box.add_child(row)
	var view := Button.new()
	view.text = "Front / side"
	view.pressed.connect(func() -> void:
		_camera_side = not _camera_side
		_update_offset())
	row.add_child(view)
	var inspect := CheckButton.new()
	inspect.text = "Pause at each seat"
	inspect.toggled.connect(func(enabled: bool) -> void: _inspect_steps = enabled)
	box.add_child(inspect)
	var next := Button.new()
	next.text = "Continue"
	next.pressed.connect(func() -> void: continue_review.emit())
	box.add_child(next)


func _process(delta: float) -> void:
	if is_instance_valid(_label):
		var place := String(_tour_world.seats[_seat_index]["label"]) if _seat_index >= 0 else "Central stairs"
		_label.text = "Dog / original estate / shared sitting clips\n" + place + " / " + _phase + "\nSofas %d / 3" % completed_seats.size()
	if not _ready_camera or _paused: return
	var target := _actor.global_position + Vector3.UP * 0.7
	var amount := 1.0 - exp(-delta * 4.0)
	_focus = _focus.lerp(target, amount)
	var offset := _follow_offset
	if not bool(_actor.get("root_motion")) and (not _actor.active_command_id.is_empty() or bool(_actor.get("_precision"))):
		var travel := Vector3(_actor.velocity.x, 0, _actor.velocity.z)
		if travel.length() > 0.05:
			var behind := -travel.normalized()
			offset = behind * 2.8 + Vector3.UP * 1.4
			if _camera_side: offset += behind.cross(Vector3.UP) * 0.7
	# Orbit between headings rather than cutting through the dog when the
	# walking view changes to a front-facing seated composition.
	_orbit_offset = _orbit_offset.slerp(offset, amount)
	var desired := _actor.global_position + _orbit_offset
	# Keep the single continuous follow camera on the actor's side of walls
	# and stair slabs. No automatic heading swaps or preset-camera jumps.
	var query := PhysicsRayQueryParameters3D.create(target, desired)
	var omit: Array[RID] = [_actor.get_rid()]
	for attempt in range(8):
		query.exclude = omit
		var hit := get_world_3d().direct_space_state.intersect_ray(query)
		if hit.is_empty(): break
		var body := hit["collider"] as CollisionObject3D
		var source := String(body.get_meta("source_node", "")).to_lower()
		# Thin open rails may cross the image; they must not collapse the
		# camera arm into the dog's tail. Their actor collisions remain active.
		if "handrail" in source or "baluster" in source or "low screen" in source:
			omit.append(body.get_rid())
			continue
		desired = (hit["position"] as Vector3) + (hit["normal"] as Vector3) * 0.15
		break
	_camera.global_position = _camera.global_position.lerp(desired, amount)
	_camera.look_at(_focus)


func _update_offset() -> void:
	var basis := _contact.basis if _seat_index >= 0 else Basis.IDENTITY
	_follow_offset = basis * (Vector3(2.7, 1.5, 1.3) if _camera_side else Vector3(0.7, 1.7, 3.5))


func _physics_process(_delta: float) -> void:
	if _stair_leg.is_empty() or not is_instance_valid(_actor): return
	var position := _actor.global_position
	var query := PhysicsRayQueryParameters3D.create(position + Vector3.UP * 0.1, position - Vector3.UP * 0.35)
	query.exclude = [_actor.get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty(): return
	var name := String((hit["collider"] as Node).get_meta("source_node", ""))
	if "Public stair L1 tread" in name: _stair_sources[name] = true


func _run_trial() -> void:
	if _running or not is_instance_valid(_actor): return
	if bool(_actor.get("root_motion")):
		_phase = "BLOCKED: reload after a failed contact"
		return
	_running = true
	completed_seats.clear()
	stairs_up = false
	stairs_down = false
	_seat_index = -1
	_update_offset()
	var anchors: Dictionary = _tour_world.semantics.anchors
	if not await _walk("Walk through central lounge", anchors["central-01/activity"].global_position):
		_running = false
		return
	for leg: String in ["up", "down"]:
		_stair_leg = leg
		_stair_sources.clear()
		var goal := "central-02/activity" if leg == "up" else "central-01/activity"
		var accepted := await _walk("Public stairs / " + leg, anchors[goal].global_position)
		_stair_leg = ""
		print("TOUR_STAIRS ", leg, " steps=", _stair_sources.size(), " reached=", accepted)
		if not accepted or _stair_sources.is_empty():
			if accepted: _phase = "BLOCKED: stairs were not traversed"
			_running = false
			return
		if leg == "up": stairs_up = true
		else: stairs_down = true
	for index in range(_tour_world.seats.size()):
		if not await _visit_seat(index):
			_running = false
			return
	_phase = "TOUR COMPLETE / walk + stairs + 3 sofas"
	_running = false
	tour_checkpoint.emit(_phase)


func _walk(id: String, target: Vector3) -> bool:
	_phase = id
	print("TOUR_WALK ", id, " from=", _actor.global_position, " to=", target)
	if not _actor.move_to(id, target, 90.0):
		_phase = "BLOCKED: navigation could not start / " + id
		return false
	var result: Array = await _actor.navigation_terminal
	if String(result[1]) != "completed":
		_phase = "BLOCKED: " + str(result)
		print("TOUR_BLOCKED ", _phase, " at=", _actor.global_position)
		return false
	return true


func _visit_seat(index: int) -> bool:
	_seat_index = index
	var seat: Dictionary = _tour_world.seats[index]
	_contact = seat["contact"]
	_update_offset()
	_approach = PLAN.approach(_contact, _measured_motion)
	_approach.origin.y = float(seat["floor_y"]) + 0.02
	var staging := _approach.origin - _approach.basis.z * 0.4
	if not await _walk("%s / walk to sofa" % seat["label"], staging): return false
	if not await _dock(staging) or not await _dock(_approach.origin): return false
	await _review_delay(0.35)
	_actor.call("begin_sequence", CONTACT.butt_point(_actor).y)
	for key: String in ["step_up", "turn_left_90", "turn_left_90", "sit_down", "seated_idle", "stand_up", "jump_down"]:
		if not await _play_motion(key, 2 if key == "seated_idle" else 1): return false
		_phase = "%s / %s" % [seat["label"], key]
		print("TOUR_MOTION ", seat["id"], " ", key)
		if key == "sit_down":
			var offset := CONTACT.butt_point(_actor) - _contact.origin
			print("TOUR_SEAT_CONTACT ", seat["id"], " offset=", offset)
			if absf(offset.y) > 0.05 or Vector2(offset.x, offset.z).length() > 0.16:
				_phase = "BLOCKED: seat contact / " + String(seat["id"])
				return false
			tour_checkpoint.emit(String(seat["id"]) + " seated")
			if _inspect_steps: await continue_review
	_actor.call("end_sequence")
	if not await _walk("%s / leave sofa" % seat["label"], staging): return false
	completed_seats.append(String(seat["id"]))
	return true
