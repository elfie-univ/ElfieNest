extends Node3D
## Real Nest candidate trial. Does not issue production commands or claim acceptance.

const CLIPS := preload("res://runtime/actor/chair_clip_sequence.gd")
const ROOM := preload("res://runtime/lab/chair_review_room.gd")
const CONTACT := preload("res://runtime/lab/chair_review_contact.gd")
const SCALE := preload("res://runtime/lab/chair_review_scale.gd")
const PLAN := preload("res://runtime/lab/chair_motion_plan.gd")
var _room: Node3D
var _actor: ElfieActor
var _player: AnimationPlayer
var _label: Label
var _phase := "Loading real Nest..."
var _running := false
var _marker: Marker3D
var _contact := Transform3D.IDENTITY
var _paused := false
var _choices: OptionButton
var _camera: Camera3D
var _fit_issues: Array[String] = []
var _scale_summary := ""
var _approach := Transform3D.IDENTITY
var _camera_basis := Basis.IDENTITY
var _comparing := false
var _swivel: Node3D
var _measured_motion: Dictionary
var _closed_contact := Transform3D.IDENTITY
var _inspect_steps := false
signal continue_review
signal stage_reached(title: String)
var review_clock: Node

func _review_delay(seconds: float) -> void:
	if review_clock != null: await review_clock.wait_preview_delay(seconds)
	else: await get_tree().create_timer(seconds).timeout

func _review_process_frame() -> void:
	if review_clock != null: await review_clock.picker_frame
	else: await get_tree().process_frame

func _review_physics_frame() -> void:
	if review_clock != null: await review_clock.picker_physics_frame
	else: await get_tree().physics_frame


func create_actor() -> ElfieActor:
	# Same authored scene/default scale as production, not a live adopted resident.
	var actor := (load("res://characters/tovren/tovren.tscn") as PackedScene).instantiate() as ElfieActor
	var species := actor.species_id
	actor.set_script(load("res://runtime/lab/chair_review_actor.gd"))
	actor.species_id = species
	actor.install_shared_animations = false
	return actor


func build_room() -> Dictionary:
	_room = ROOM.new()
	add_child(_room)
	return await _room.build()


func setup(nest: Node3D, characters: Node3D) -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	if OS.has_feature("web"):
		layer.scale = Vector2.ONE * float(JavaScriptBridge.eval("window.devicePixelRatio || 1"))
	var box := VBoxContainer.new()
	box.position = Vector2(12, 12)
	layer.add_child(box)
	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 14)
	box.add_child(_label)
	var button := Button.new()
	button.text = "Swivel chair / complete physical trial"
	button.pressed.connect(_run_trial)
	box.add_child(button)
	_choices = OptionButton.new()
	for key: String in CLIPS.FILES:
		_choices.add_item(key)
	box.add_child(_choices)
	var row := HBoxContainer.new()
	box.add_child(row)
	var play := Button.new()
	play.text = "Raw clip"
	play.pressed.connect(_audition_selected)
	row.add_child(play)
	var pause := Button.new()
	pause.text = "Pause clip"
	pause.pressed.connect(func() -> void:
		_paused = not _paused
		if is_instance_valid(_player): _player.speed_scale = 0.0 if _paused else 1.0)
	row.add_child(pause)
	var side := Button.new()
	side.text = "Side view"
	side.pressed.connect(func() -> void: _set_camera(Vector3(2.2, 0.8, 0.8)))
	row.add_child(side)
	var wide := Button.new()
	wide.text = "Wide view"
	wide.pressed.connect(_set_wide_camera)
	row.add_child(wide)
	var inspection := HBoxContainer.new()
	box.add_child(inspection)
	var inspect := CheckButton.new()
	inspect.text = "Inspect each stage"
	inspect.toggled.connect(func(enabled: bool) -> void: _inspect_steps = enabled)
	inspection.add_child(inspect)
	var next := Button.new()
	next.text = "Continue"
	next.pressed.connect(func() -> void: continue_review.emit())
	inspection.add_child(next)
	var compare := Button.new()
	compare.text = "Walk beside chair / same-scale view"
	compare.pressed.connect(_compare_scale)
	box.add_child(compare)
	await get_tree().process_frame
	var configured := await build_room()
	if not bool(configured.get("ready", false)):
		_phase = "BLOCKED: real navigation did not configure"
		return
	_marker = _room.semantics.anchors["dorm-01/chair-01"]
	_contact = _marker.get_meta("interaction_transform") as Transform3D
	_camera_basis = _contact.basis
	var seating := PLAN.seating_contact(_room.geometry, _contact)
	if seating.is_empty():
		_phase = "BLOCKED: original chair back orientation unavailable"
		return
	_contact = seating["transform"] as Transform3D
	_closed_contact = _contact
	_swivel = _room.configure_swivel()
	if _swivel == null:
		_phase = "BLOCKED: original desk collision could not be preserved"
		return
	_actor = create_actor()
	characters.add_child(_actor)
	_player = _actor.get_node("AnimationPlayer") as AnimationPlayer
	var locomotion := CLIPS.locomotion_for(_actor)
	var furniture := CLIPS.library_for(_actor, true)
	if locomotion == null or furniture == null:
		_phase = "BLOCKED: downloaded motion retarget needs repair"
		return
	_player.add_animation_library("", locomotion)
	_player.add_animation_library("chair", furniture)
	_actor.configure("chair-candidate", (_room.semantics.anchors["dorm-01/bed-01"] as Marker3D).global_position)
	if not is_finite(CONTACT.ground(_actor, _actor.global_position.y)):
		_phase = "BLOCKED: actual skinned sole could not be sampled"
		return
	var measured := SCALE.measure(_actor)
	var body: AABB = measured.get("body", AABB())
	var seat := SCALE.seat_size(_room.geometry, _contact)
	var floor_mesh := _room.semantics.room_floors["M01"] as MeshInstance3D
	var seat_height := SCALE.seat_height(_room.geometry, floor_mesh)
	_scale_summary = "Body %.2f m high / FLOOR-to-seat %.2f m / cushion %.2f x %.2f m" % [body.size.y, seat_height, seat.x, seat.z]
	var probe := create_actor()
	probe.visible = false
	characters.add_child(probe)
	var probe_player := probe.get_node("AnimationPlayer") as AnimationPlayer
	probe_player.add_animation_library("", CLIPS.locomotion_for(probe))
	probe_player.add_animation_library("chair", CLIPS.library_for(probe, true))
	probe.configure("hidden-motion-measurement", Vector3.ZERO)
	var measured_motion := PLAN.measure(probe)
	_measured_motion = measured_motion
	_actor.set("seated_shape_cache", measured_motion.get("seated_shapes", []))
	probe.free()
	if measured_motion.is_empty():
		_phase = "BLOCKED: downloaded motion endpoint unavailable"
		return
	_approach = PLAN.approach(_contact, measured_motion)
	# Only XZ is calibrated. Never lift/lower the live actor to fake seat height.
	_approach.origin.y = _marker.global_position.y
	nest.set_process_unhandled_input(false)
	_camera = Camera3D.new()
	add_child(_camera)
	_camera.fov = 48
	_camera.near = 0.03
	_set_camera(Vector3(1.7, 1.0, 2.8))
	_camera.make_current()
	_phase = "READY: actual dorm-01/chair-01 / adapted dog sample"


func _process(_delta: float) -> void:
	if is_instance_valid(_label):
		if _comparing:
			_label.text = "Original-scale dog / orthographic comparison\n" + _scale_summary + "\n" + _phase
			return
		_label.text = "F01 / original-size dog + original dorm chair\n" + _phase
		if is_instance_valid(_player):
			_label.text += "\n" + String(_player.assigned_animation)
			_label.text += " | " + ("PAUSED" if _paused else "playing")
			_label.text += " %.2f / %.2f" % [_player.current_animation_position, _player.current_animation_length]


func _set_camera(offset: Vector3) -> void:
	if not is_instance_valid(_camera): return
	_camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	_camera.global_position = _contact.origin + _camera_basis * offset
	_camera.look_at(_contact.origin + Vector3.UP * 0.55)


func _set_wide_camera() -> void:
	# Look down from above the reachable open-side approach, not from behind
	# the wall or through the foreground bed at ankle height.
	_set_camera(Vector3(0.0, 2.1, 1.5))
	_camera.fov = 65.0


func _compare_scale() -> void:
	if _running or not is_instance_valid(_actor) or bool(_actor.get("root_motion")): return
	_running = true
	var beside := _contact.origin + _camera_basis.x * 0.8
	beside.y = _marker.global_position.y
	beside = NavigationServer3D.map_get_closest_point(get_world_3d().navigation_map, beside)
	if await _walk("walk beside original chair for scale comparison", beside):
		await _dock(beside)
	# Compare at the position actually reached, including when the side is blocked.
	# Camera changes never relocate the actor or conceal a failed route.
	var blocked := _phase.begins_with("BLOCKED")
	var center := (_actor.global_position + _contact.origin) * 0.5
	center.y = _actor.global_position.y + 0.65
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.size = 2.8
	_camera.global_position = center + _camera_basis * Vector3(0.0, 0.3, 1.5)
	_camera.look_at(center)
	_phase = "Side route blocked; actual reached position" if blocked else "Standing beside chair; no sitting"
	_comparing = true
	for control: Node in _label.get_parent().get_children():
		if control != _label and control is Control: (control as Control).hide()
	_running = false


func _audition_selected() -> void:
	if _running or not is_instance_valid(_actor): return
	_running = true
	if bool(_actor.get("root_motion")):
		_phase = "Reload this isolated fixture before another raw audition"
		_running = false
		return
	_actor.set("audition", false)
	_player.speed_scale = 1.0
	_paused = false
	if not await _walk("approach chair with real collision", _marker.global_position):
		_running = false
		return
	_actor.basis = _contact.basis
	_actor.set("audition", true)
	_paused = false
	_player.speed_scale = 1.0
	var key := _choices.get_item_text(_choices.selected)
	_phase = "Pose audition: " + key + " / sit and rise use authored contact edits"
	_player.play("chair/" + key)
	_player.advance(0.0)
	_running = false


func _walk(id: String, target: Vector3) -> bool:
	_phase = id
	if not _actor.move_to(id, target, 30.0):
		_phase = "BLOCKED: navigation could not start"
		return false
	var result: Array = await _actor.navigation_terminal
	if String(result[1]) != "completed":
		_phase = "BLOCKED: " + str(result)
		return false
	return true


func _checkpoint(title: String) -> void:
	stage_reached.emit(title)
	if not _inspect_steps: return
	_phase = title + " / inspect, then Continue"
	await continue_review


func _dock(target: Vector3) -> bool:
	_actor.call("walk_precisely", target)
	var terminal: Signal = _actor.get("precision_terminal")
	var result: Array = await terminal
	if not bool(result[0]): _phase = "BLOCKED: precision approach / " + str(result[1])
	return bool(result[0])


func _play_motion(key: String, repeats: int = 1) -> bool:
	_phase = "PLAYING: " + key
	if not bool(_actor.call("start_clip", key, repeats)):
		_phase = "BLOCKED: missing downloaded root track for " + key
		return false
	var done: Signal = _actor.get("clip_terminal")
	var result: Array = await done
	if not bool(result[1]):
		_phase = "BLOCKED: " + key + " / " + String(result[2])
		var offset := CONTACT.butt_point(_actor) - _contact.origin
		_phase += "\nSkin-seat offset: vertical %.3f m / horizontal %.3f m" % [offset.y, Vector2(offset.x, offset.z).length()]
		return false
	return true


func _run_trial() -> void:
	await run_chair_trial()


func run_chair_trial() -> void:
	if _running or not is_instance_valid(_actor):
		return
	_running = true
	if bool(_actor.get("root_motion")):
		_phase = "Reload fixture before replay; failed contact must not teleport home"
		_running = false
		return
	_fit_issues.clear()
	_actor.set("audition", false)
	_phase = "Turn empty chair toward open room"
	if not await _swivel.turn_to(PI, null):
		_phase = "BLOCKED: chair rotation / " + _swivel.last_obstacle
		_running = false
		return
	_contact = Transform3D(Basis(Vector3.UP, PI) * _closed_contact.basis, _closed_contact.origin)
	_contact.origin += _contact.basis.z * float(preload("res://characters/animation/candidates/dog_chair_contact_edits.tres").get_meta("seat_forward_offset"))
	_approach = PLAN.approach(_contact, _measured_motion)
	_approach.origin.y = _marker.global_position.y
	var staging := _approach.origin - _approach.basis.z * 0.45
	if not await _walk("walk to chair staging", staging):
		_running = false
		return
	_phase = "precise collision-aware approach / original walking clip"
	if not await _dock(staging) or not await _dock(_approach.origin):
		_running = false
		return
	await _review_delay(0.35)
	var butt := CONTACT.butt_point(_actor)
	if not butt.is_finite():
		_phase = "BLOCKED: real skinned body contact could not be measured"
		_running = false
		return
	_actor.call("begin_sequence", butt.y)
	_player.speed_scale = 1.0
	_paused = false
	for key: String in ["step_up", "turn_left_90", "turn_left_90", "sit_down", "seated_idle", "stand_up", "jump_down"]:
		if not await _play_motion(key, 6 if key == "seated_idle" else 1):
			_running = false
			return
		await _checkpoint(key + " end pose")
		if key == "seated_idle":
			var contact := CONTACT.butt_point(_actor)
			var offset := contact - _contact.origin
			if absf(offset.y) > 0.04 or Vector2(offset.x, offset.z).length() > 0.16:
				_fit_issues.append("seat mismatch: vertical %.3f m / horizontal %.3f m" % [offset.y, Vector2(offset.x, offset.z).length()])
				_phase = "NOT ACCEPTED: " + ", ".join(_fit_issues)
				_running = false
				return
			_phase = "Seated / rotate toward desk"
			if not bool(_actor.call("use_seated_collision")):
				_phase = "BLOCKED: seated skin collision unavailable"
				_running = false
				return
			await _review_physics_frame()
			if not await _swivel.turn_to(0.0, _actor):
				_phase = "BLOCKED: seated rotation / " + _swivel.last_obstacle
				_running = false
				return
			await _checkpoint("Seated at desk")
			await _review_delay(3.0)
			_phase = "Rotate toward clear exit before rising"
			if not await _swivel.turn_to(PI, _actor):
				_phase = "BLOCKED: exit rotation / " + _swivel.last_obstacle
				_running = false
				return
			await _checkpoint("Facing clear exit")
			_actor.call("clear_seated_collision")
	_actor.call("end_sequence")
	if await _walk("leave chair", (_room.semantics.anchors["dorm-01/bed-01"] as Marker3D).global_position):
		_phase = "PHYSICS TRIAL ENDED / visual acceptance pending" if _fit_issues.is_empty() else "NOT ACCEPTED: " + ", ".join(_fit_issues)
	_running = false
