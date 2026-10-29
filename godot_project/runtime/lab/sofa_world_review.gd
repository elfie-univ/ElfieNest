extends "res://runtime/lab/chair_world_review.gd"
## First sofa audition, reuses the existing physical clip runner and dog rig.

var _start := Vector3.ZERO
var _sofa_room: Node3D


func setup(nest: Node3D, characters: Node3D) -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	if OS.has_feature("web"): layer.scale = Vector2.ONE * float(JavaScriptBridge.eval("window.devicePixelRatio || 1"))
	var box := VBoxContainer.new()
	box.position = Vector2(12, 12)
	layer.add_child(box)
	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 14)
	box.add_child(_label)
	var play := Button.new()
	play.text = "Sofa / approach > mount > sit > leave"
	play.pressed.connect(_run_trial)
	box.add_child(play)
	var row := HBoxContainer.new()
	box.add_child(row)
	var side := Button.new()
	side.text = "Side view"
	side.pressed.connect(func() -> void: _set_camera(Vector3(2.6, 1.0, 1.6)))
	row.add_child(side)
	var wide := Button.new()
	wide.text = "Wide view"
	wide.pressed.connect(func() -> void: _set_camera(Vector3(0, 2.6, 3.3)))
	row.add_child(wide)
	var inspect := CheckButton.new()
	inspect.text = "Inspect each stage"
	inspect.toggled.connect(func(enabled: bool) -> void: _inspect_steps = enabled)
	box.add_child(inspect)
	var next := Button.new()
	next.text = "Continue"
	next.pressed.connect(func() -> void: continue_review.emit())
	box.add_child(next)
	var arms := Button.new()
	arms.text = "Compare source / retarget / furniture arms"
	arms.pressed.connect(func() -> void:
		if OS.has_feature("web"): JavaScriptBridge.eval("window.location.href='/runtime/godot/elfienest.html?mode=elfie_lab&review=animation&compare=arms'"))
	box.add_child(arms)
	_sofa_room = preload("res://runtime/lab/sofa_review_room.gd").new()
	add_child(_sofa_room)
	var configured: Dictionary = await _sofa_room.build()
	if not bool(configured.get("ready", false)):
		_phase = "BLOCKED: original sofa or navigation missing"
		return
	_contact = _sofa_room.contact
	_camera_basis = Basis.IDENTITY
	_actor = create_actor()
	characters.add_child(_actor)
	_player = _actor.get_node("AnimationPlayer") as AnimationPlayer
	_player.add_animation_library("", CLIPS.locomotion_for(_actor))
	_player.add_animation_library("chair", _library(_actor))
	_start = _contact.origin + Vector3(1.8, 0, 1.9)
	_start.y = _sofa_room.floor_y
	_actor.configure("F08-sofa-dog-sample", _start)
	CONTACT.ground(_actor, _sofa_room.floor_y)
	var probe := create_actor()
	characters.add_child(probe)
	var player := probe.get_node("AnimationPlayer") as AnimationPlayer
	player.add_animation_library("", CLIPS.locomotion_for(probe))
	player.add_animation_library("chair", _library(probe))
	probe.configure("hidden-sofa-endpoint", Vector3.ZERO)
	var measured := PLAN.measure(probe)
	probe.free()
	_approach = PLAN.approach(_contact, measured)
	_approach.origin.y = _sofa_room.floor_y + 0.02
	nest.set_process_unhandled_input(false)
	_camera = Camera3D.new()
	add_child(_camera)
	_camera.fov = 52
	_camera.near = 0.03
	_set_camera(Vector3(2.6, 1.0, 1.6))
	_camera.make_current()
	await get_tree().physics_frame
	var map := get_world_3d().navigation_map
	print("SOFA_APPROACH start=", _start, " approach=", _approach, " nearest_start=", NavigationServer3D.map_get_closest_point(map, _start), " nearest_approach=", NavigationServer3D.map_get_closest_point(map, _approach.origin))
	_phase = "READY: original central L1 sofa / adapted platform mount"


func _library(actor: ElfieActor) -> AnimationLibrary:
	var result := CLIPS.library_for(actor, true)
	var edits := preload("res://characters/animation/candidates/dog_sofa_contact_edits.tres") as AnimationLibrary
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	var root_path := NodePath("Skeleton3D:" + String(skeleton.get_bone_name(int(actor._furniture_hips()["bone"]))))
	for key: String in edits.get_animation_list():
		var clip := result.get_animation(key)
		var correction := edits.get_animation(key)
		var track := clip.find_track(root_path, Animation.TYPE_POSITION_3D)
		for index in range(clip.track_get_key_count(track)):
			var time := clip.track_get_key_time(track, index)
			var point := clip.track_get_key_value(track, index) as Vector3
			clip.track_set_key_value(track, index, point + skeleton.global_basis.inverse() * correction.position_track_interpolate(0, time))
	var idle := CLIPS.locomotion_for(actor).get_animation("idle")
	preload("res://runtime/actor/chair_dog_leg_keys.gd").bake(result.get_animation("turn_left_90"), "turn_left_90", actor, idle, edits.get_meta("turn_ankle_lift") as Vector2)
	return result


func _process(_delta: float) -> void:
	if not is_instance_valid(_label): return
	_label.text = "F08 / original dog + original sofa\n" + _phase
	if is_instance_valid(_player): _label.text += "\n" + String(_player.assigned_animation)


func _dock(target: Vector3) -> bool:
	print("SOFA_DOCK from=", _actor.global_position, " target=", target)
	_actor.call("walk_precisely", target, 2.0)
	var terminal: Signal = _actor.get("precision_terminal")
	var result: Array = await terminal
	var accepted := bool(result[0])
	if not accepted: _phase = "BLOCKED: precision approach / " + str(result[1])
	if not accepted:
		for index in range(_actor.get_slide_collision_count()):
			var collider := _actor.get_slide_collision(index).get_collider() as Node
			print("SOFA_DOCK_OBSTACLE ", collider.get_meta("source_node", collider.name), " actual=", _actor.global_position)
	return accepted


func _run_trial() -> void:
	if _running or not is_instance_valid(_actor): return
	_running = true
	if bool(_actor.get("root_motion")):
		_phase = "Reload fixture after blocked contact"
		_running = false
		return
	var staging := _approach.origin - _approach.basis.z * 0.4
	if not await _walk("Walk toward original sofa", staging) or not await _dock(staging) or not await _dock(_approach.origin):
		_running = false
		return
	# Finish the walking-to-idle blend before capturing the root-motion frame,
	# exactly as the chair fixture does. Otherwise the gait phase changes feet.
	await get_tree().create_timer(0.35).timeout
	_actor.call("begin_sequence", CONTACT.butt_point(_actor).y)
	for key: String in ["step_up", "turn_left_90", "turn_left_90", "sit_down", "seated_idle", "stand_up", "jump_down"]:
		if not await _play_motion(key, 4 if key == "seated_idle" else 1):
			_running = false
			return
		await _checkpoint(key + " end pose")
		if key == "sit_down":
			var offset := CONTACT.butt_point(_actor) - _contact.origin
			print("SOFA_SEAT_CONTACT ", offset)
			if absf(offset.y) > 0.04 or Vector2(offset.x, offset.z).length() > 0.16:
				_phase = "BLOCKED: sofa contact mismatch " + str(offset)
				_running = false
				return
	_actor.call("end_sequence")
	if await _walk("Leave original sofa", _start): _phase = "SOFA TRIAL ENDED / visual review pending"
	_running = false
