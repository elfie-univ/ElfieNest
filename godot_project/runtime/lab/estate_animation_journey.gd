extends "res://runtime/lab/estate_animation_tour.gd"
## Explicit offline journey. One visible actor, real routes, fail at first gap.

const JOURNEY_PLAN := preload("res://runtime/lab/estate_animation_journey_plan.gd")
const ARRIVAL_TIMING := preload("res://runtime/lab/estate_platform_cycle.gd")
var plan := JOURNEY_PLAN.new()
var _nest: Node3D
var _geometry: Node3D
var _arrival: Node3D
var _arrival_lights: Node3D
var _effects: Node3D
var _water: Node3D
var _splash: Node3D
var _journey_running := false
var _chapter_pause := false
var _waiting := false
var _pause_started := 0
var _last_error := ""
var _played_sources: Dictionary = {}
var _status: Label
var _details: Label
var _report_panel: ScrollContainer
var _play_button: Button
var _retry_button: Button
var _pause_button: Button
var _continue_button: Button
var _ready_for_play := false
var _chair_prepared := false
var _doors_seen: Dictionary = {}
var _restart_button: Button
var _restart_pending := false
var _loading_failed := false
var load_timeout_seconds := 30.0
var _bed_journey: Node3D
signal runtime_restart_requested


func setup(nest: Node3D, characters: Node3D) -> void:
	_nest = nest
	_build_journey_controls()
	runtime_restart_requested.connect(_restart_runtime, CONNECT_DEFERRED)
	get_tree().create_timer(load_timeout_seconds, true, false, true).timeout.connect(_loading_timeout)
	# Reuse the complete current world, its colliders and precompiled navigation.
	while nest.get("_estate_physics") == null:
		if _loading_failed: return
		await get_tree().process_frame
	if _loading_failed: return
	_phase = "Preparing validated collision and navigation..."
	nest.set_process_unhandled_input(false)
	nest.set_observation_hud_visible(false)
	var physics: Node3D = nest.get("_estate_physics")
	if physics == null or not bool(physics.get("loaded_precompiled")):
		_setup_failure("Matching precompiled collision resources were not loaded; refusing to walk without validated colliders")
		return
	if not nest.bake_navigation() or not await nest.wait_for_navigation_sync():
		_setup_failure("Complete estate navigation did not become ready")
		return
	if _loading_failed: return
	_geometry = nest.get_node("Generated/CompleteEstate")
	_tour_world = preload("res://runtime/lab/estate_tour_room.gd").new()
	add_child(_tour_world)
	if not _tour_world.bind_existing(nest):
		_setup_failure("An original sofa/contact annotation is missing")
		return
	_tour_world.semantics.align_approaches(get_world_3d().navigation_map)
	_actor = create_actor()
	_actor.name = "JourneyTestActor"
	_actor.install_shared_animations = true
	characters.add_child(_actor)
	_player = _actor.get_node("AnimationPlayer") as AnimationPlayer
	# Add source poses for the final inventory comparison; confirmed furniture
	# libraries are loaded separately and are never replaced by these raw clips.
	_actor.get("_animation_runtime").call("_install_animations", JOURNEY_PLAN.clip_sources())
	_install_navigation_locomotion()
	_player.add_animation_library("chair", _library(_actor))
	_camera = Camera3D.new()
	add_child(_camera)
	_camera.near = 0.03
	_camera.fov = 65.0
	if not _bind_arrival():
		_setup_failure(_last_error)
		return
	_focus = _actor.global_position + Vector3.UP * 0.7
	_camera.global_position = _focus + _follow_offset
	_camera.look_at(_focus)
	_camera.make_current()
	_ready_camera = true
	_ready_for_play = true
	_restart_button.disabled = false
	_phase = "Ready. Play starts a new local test; no resident data is changed."
	_play_button.disabled = false
	_update_journey_status()
	_play_button.grab_focus()
	if OS.has_feature("web") and JOURNEY_PLAN.auto_start(str(JavaScriptBridge.eval("window.location.search"))):
		call_deferred("_start_journey")


func _build_journey_controls() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	if OS.has_feature("web"):
		layer.scale = Vector2.ONE * float(JavaScriptBridge.eval("window.devicePixelRatio || 1"))
	var panel := PanelContainer.new()
	panel.position = Vector2(10, 10)
	panel.custom_minimum_size.x = 330
	layer.add_child(panel)
	var box := VBoxContainer.new()
	panel.add_child(box)
	_status = Label.new()
	_status.custom_minimum_size.x = 330
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_status)
	var row := HBoxContainer.new()
	box.add_child(row)
	_play_button = Button.new()
	_play_button.text = "Play all"
	_play_button.disabled = true
	_play_button.pressed.connect(_start_journey)
	row.add_child(_play_button)
	_pause_button = Button.new()
	_pause_button.text = "Pause"
	_pause_button.pressed.connect(_toggle_pause)
	row.add_child(_pause_button)
	_continue_button = Button.new()
	_continue_button.text = "Continue"
	_continue_button.disabled = true
	_continue_button.pressed.connect(func() -> void: _waiting = false)
	row.add_child(_continue_button)
	var inspection := CheckButton.new()
	inspection.text = "Pause after each chapter"
	inspection.toggled.connect(func(value: bool) -> void: _chapter_pause = value)
	box.add_child(inspection)
	var actions := HBoxContainer.new()
	box.add_child(actions)
	_retry_button = Button.new()
	_retry_button.text = "Retry blocked chapter"
	_retry_button.disabled = true
	_retry_button.pressed.connect(_retry_chapter)
	actions.add_child(_retry_button)
	_restart_button = Button.new()
	_restart_button.text = "New run"
	_restart_button.disabled = true
	_restart_button.pressed.connect(request_new_run)
	actions.add_child(_restart_button)
	var details := Button.new()
	details.text = "Checklist / report"
	details.pressed.connect(func() -> void: _report_panel.visible = not _report_panel.visible)
	box.add_child(details)
	_report_panel = ScrollContainer.new()
	_report_panel.custom_minimum_size = Vector2(330, 180)
	_report_panel.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_report_panel.visible = false
	box.add_child(_report_panel)
	_details = Label.new()
	_details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_details.custom_minimum_size.x = 330
	_details.add_theme_font_size_override("font_size", 12)
	_report_panel.add_child(_details)
	_label = _status
	_phase = "Loading the complete current estate..."
	_update_journey_status()


func _process(delta: float) -> void:
	# Keep the established continuous follow camera and wall-occlusion checks.
	if _tour_world != null and _actor != null:
		super(delta)
		for door: Dictionary in _tour_world.physics.get("_doors"):
			if float(door["amount"]) >= 0.95:
				_doors_seen[(door["mesh"] as Node).get_instance_id()] = true
	_update_journey_status()


func _update_journey_status() -> void:
	if _status == null: return
	var title := str(plan.current().get("title", "Ready" if _ready_for_play else "Loading"))
	if plan.index >= JOURNEY_PLAN.STAGES.size(): title = "Playback ended / visual acceptance still pending"
	_status.text = "ANIMATION JOURNEY / LOCAL TEST\n%d / %d chapters played | %d / 25 source clips\n%s\n%s" % [plan.completed.size(), JOURNEY_PLAN.STAGES.size(), _played_sources.size(), title, _phase]
	if not plan.blocked.is_empty():
		_status.text += "\nSTOPPED at actual position %s\n%s\nRemaining chapters were NOT played." % [plan.blocked["position"], plan.blocked["reason"]]
	var lines: PackedStringArray = []
	for stage: Dictionary in JOURNEY_PLAN.STAGES:
		var state := "played" if plan.completed.has(stage["id"]) else ("BLOCKED" if plan.blocked.get("stage", "") == stage["id"] else "pending")
		lines.append("[%s] %s" % [state, stage["title"]])
	_details.text = "\n".join(lines)
	_retry_button.disabled = plan.blocked.is_empty() or _journey_running
	_continue_button.disabled = not _waiting


func _setup_failure(reason: String) -> void:
	_loading_failed = true
	_restart_button.disabled = false
	plan.start()
	plan.finish_current(false, "Setup: " + reason, _actor.global_position if _actor != null else Vector3.ZERO)
	_phase = "Setup blocked; no chapter was played."
	_update_journey_status()


func _loading_timeout() -> void:
	if _ready_for_play or _loading_failed or _restart_pending: return
	_setup_failure("Loading timed out before world/camera readiness. New run restarts this Web runtime; it does not skip validation.")


func request_new_run() -> void:
	if _restart_pending or (not _ready_for_play and not _loading_failed): return
	_restart_pending = true
	_restart_button.disabled = true
	_phase = "Restarting this test runtime..."
	_update_journey_status()
	runtime_restart_requested.emit()


func _restart_runtime() -> void:
	# Reinitialise the same Web document/engine, releasing all old scene state.
	# An in-engine scene reload left this heavy world at a white loading screen.
	if OS.has_feature("web"):
		JavaScriptBridge.eval("window.location.reload()")
	else:
		get_tree().paused = false
		get_tree().call_deferred("reload_current_scene")


func _start_journey() -> void:
	if _journey_running or not _ready_for_play: return
	if plan.index >= 0: return # New run is an explicit fresh scene, never a warp.
	plan.start()
	_play_button.disabled = true
	await _run_journey()


func _retry_chapter() -> void:
	if _journey_running or not _ready_for_play or not plan.retry_current(): return
	# Reuse the actual failed position. No configure(), reset or next-stage skip.
	await _run_journey()


func _run_journey() -> void:
	_journey_running = true
	while plan.running:
		_last_error = ""
		var id := str(plan.current()["id"])
		_phase = str(plan.current()["title"])
		var success := await _execute_chapter(id)
		plan.finish_current(success, _last_error, _actor.global_position)
		print("ANIMATION_JOURNEY ", JSON.stringify(plan.report()))
		if not success:
			_phase = "BLOCKED / inspect the real failure before retrying"
			break
		if _chapter_pause and plan.running:
			_waiting = true
			_phase = "Chapter played. Inspect, then Continue."
			while _waiting: await get_tree().process_frame
	if plan.blocked.is_empty(): _phase = "All chapters played. This is not automatic visual approval."
	_journey_running = false
	_update_journey_status()


func _toggle_pause() -> void:
	if not _ready_for_play or not plan.running: return
	_paused = not _paused
	_pause_button.text = "Resume" if _paused else "Pause"
	_actor.process_mode = Node.PROCESS_MODE_DISABLED if _paused else Node.PROCESS_MODE_INHERIT
	if _paused:
		_pause_started = Time.get_ticks_msec()
	else:
		if not _actor.active_command_id.is_empty():
			_actor.set("_deadline_msec", int(_actor.get("_deadline_msec")) + Time.get_ticks_msec() - _pause_started)


func _wait(seconds: float, sample: Callable = Callable()) -> void:
	var elapsed := 0.0
	while elapsed < seconds:
		await get_tree().process_frame
		if _paused: continue
		elapsed = minf(elapsed + get_process_delta_time(), seconds)
		if sample.is_valid(): sample.call(elapsed)


func _fail(reason: String) -> bool:
	_last_error = reason
	return false


func _bind_arrival() -> bool:
	var platform := _mesh("central", "Roof01 complete raised landing platform")
	var floor := _mesh("central", "Central L4 round arrival floor")
	var steps := _assembly("central", "roof01_steps")
	if platform == null or floor == null or steps == null:
		return _fail("Original rooftop platform, treads or floor missing")
	var bounds := platform.global_transform * platform.get_aabb()
	var center := bounds.get_center()
	center.y = bounds.end.y + 0.025
	_effects = preload("res://runtime/lab/estate_event_effects.gd").new()
	add_child(_effects)
	_effects.configure_arrival(center, minf(1.1, minf(bounds.size.x, bounds.size.z) * 0.25))
	_arrival_lights = preload("res://runtime/lab/estate_arrival_lighting.gd").new()
	add_child(_arrival_lights)
	_arrival_lights.bind(_geometry)
	_arrival = preload("res://runtime/lab/estate_platform_cycle.gd").new()
	add_child(_arrival)
	var surfaces: Array[MeshInstance3D] = [platform, steps, floor]
	_arrival.bind(_effects, bounds, Callable(_arrival_lights, "sample"), (steps.global_transform * steps.get_aabb()).get_center(), surfaces, _actor)
	return true


func _execute_chapter(id: String) -> bool:
	match id:
		"arrival":
			await _wait(ARRIVAL_TIMING.ARRIVAL_END, Callable(_arrival, "sample"))
			return true
		"platform-exit":
			# Never sample the presentation's walk-down leg: it assigns a
			# sampled path position. Hand the same visible body to real physics.
			_actor.add_to_group(&"runtime_elfie_actors")
			(_actor.get_node("CollisionShape3D") as CollisionShape3D).disabled = false
			_actor.set_physics_process(true)
			await get_tree().physics_frame
			var goal: Vector3 = _arrival.walk_profile.back()
			_actor.call("walk_precisely", goal, 12.0)
			var terminal: Signal = _actor.get("precision_terminal")
			var result: Array = await terminal
			if not bool(result[0]) or absf(_actor.global_position.y - goal.y) > 0.25:
				return _fail("Real platform-step traversal failed: %s; goal=%s; %s" % [result, goal, _collision_reason()])
			return true
		"stairs":
			for level: int in [3, 2, 1]:
				if not await _walk_anchor("central-%02d/activity" % level): return false
			return true
		"doors": return await _internal_doors()
		"garden-door": return await _garden_door()
		"locomotion":
			if not await _walk_anchor("courtyard/activity"): return false
			return await _review_clips(["idle", "walking", "running", "left_turn", "right_turn", "left_turn_90", "right_turn_90", "left_strafe", "right_strafe", "left_strafe_walking", "right_strafe_walking"])
		"expressions":
			if not await _review_clips(["jump", "twist_dance", "pose_waving", "pose_thinking", "pose_victory", "pose_thumbs_up", "pose_hands_on_hips"]): return false
			_actor.set("audition", true)
			for gesture: String in ["nod_head", "shake_head"]:
				_phase = "Gesture / " + gesture
				if not _actor.play_preview_intent({"type": "motion", "motion": gesture}):
					_actor.set("audition", false)
					return _fail("Gesture is not connected: " + gesture)
				await _wait(1.5)
			_actor.set("audition", false)
			return true
		"chair": return await _desk_chair()
		"sofa-central", "sofa-cinema", "sofa-tea":
			var seat_index := ["sofa-central", "sofa-cinema", "sofa-tea"].find(id)
			_player.remove_animation_library("chair")
			_player.add_animation_library("chair", _library(_actor))
			if not await _measure_motion(): return false
			if not await _visit_seat(seat_index): return _fail(_phase + "; " + _collision_reason())
			return true
		"sleep-back", "sleep-left", "sleep-right", "embodiment":
			return await _sleep_chapter(id)
		"fountain", "spillway", "lake", "water-night": return await _water_chapter(id)
		"clip-inventory":
			var remaining: Array[String] = []
			for key: String in JOURNEY_PLAN.clip_sources():
				if not _played_sources.has(JOURNEY_PLAN.clip_sources()[key]): remaining.append(key)
			return await _review_clips(remaining)
	return _fail("Unregistered chapter: " + id)


func _walk_anchor(id: String) -> bool:
	var marker := _nest.resolve_anchor(id) as Marker3D
	if marker == null: return _fail("Missing actual world anchor: " + id)
	if not await _walk(id, marker.global_position):
		return _fail("Route failed: %s; goal=%s; %s; %s" % [id, marker.global_position, _phase, _collision_reason()])
	return true


func _collision_reason() -> String:
	var sources: PackedStringArray = []
	for index in range(_actor.get_slide_collision_count()):
		var node := _actor.get_slide_collision(index).get_collider() as Node
		if node != null: sources.append(str(node.get_meta("source_node", node.name)))
	return "colliders=" + ", ".join(sources)


func _internal_doors() -> bool:
	# One representative leaf exercises the animation. This does not certify
	# the other seven rooms or remove any of their physical collision bodies.
	if not await _walk_anchor("dorm-01/bed-01"): return false
	if not await _walk_anchor("central-01/activity"): return false
	await _wait(2.6)
	var checked := 0
	for door: Dictionary in _tour_world.physics.get("_doors"):
		var mesh := door["mesh"] as Node
		if mesh.get_meta("generated_garden_leaf", false): continue
		if str((mesh.get_meta("extras", {}) as Dictionary).get("connection", "")) != "M01": continue
		checked += 1
		if not _doors_seen.has(mesh.get_instance_id()): return _fail("Internal door did not visibly open on the actual route: " + mesh.name)
	return checked == 1 or _fail("The representative M01 sliding door is missing or ambiguous")


func _install_navigation_locomotion() -> void:
	# Inventory clips must not undo the accepted species retarget or move the
	# visual rig separately from its physics body during real travel.
	var confirmed := CLIPS.locomotion_for(_actor)
	var library := _player.get_animation_library("")
	for key: StringName in confirmed.get_animation_list():
		if library.has_animation(key): library.remove_animation(key)
		library.add_animation(key, confirmed.get_animation(key))


func _garden_door() -> bool:
	var doors: Array = _tour_world.physics.get("_doors")
	var leaves := doors.filter(func(door: Dictionary) -> bool: return bool((door["mesh"] as Node).get_meta("generated_garden_leaf", false)))
	if leaves.size() != 2: return _fail("Original paired garden leaves are not available")
	if not await _walk_anchor("courtyard/activity"): return false
	if not await _walk_anchor("central-01/activity"): return false
	await _wait(2.6)
	for leaf: Dictionary in leaves:
		if not _doors_seen.has((leaf["mesh"] as Node).get_instance_id()):
			return _fail("Garden route did not exercise both real door leaves; no forced opening or skipped acceptance")
	return true


func _review_clips(keys: Array) -> bool:
	# Explicit source inventory audition, not proof of physical locomotion.
	# Body routes before/after it still go through real navigation/collisions.
	_actor.set("audition", true)
	for key: String in keys:
		if not _player.has_animation(key):
			_actor.set("audition", false)
			return _fail("Source clip did not import for this actor: " + key)
		_phase = "Source clip comparison / " + key
		_player.play(key, 0.22)
		await _wait(maxf(1.2, _player.get_animation(key).length))
		_played_sources[JOURNEY_PLAN.clip_sources()[key]] = true
	_player.play("idle", 0.22)
	await _wait(0.3)
	_actor.set("audition", false)
	return true


func _measure_motion() -> bool:
	var probe := create_actor()
	probe.visible = false
	add_child(probe)
	var player := probe.get_node("AnimationPlayer") as AnimationPlayer
	player.add_animation_library("", CLIPS.locomotion_for(probe))
	player.add_animation_library("chair", _player.get_animation_library("chair"))
	probe.configure("hidden-journey-contact-measurement", Vector3.ZERO)
	_measured_motion = PLAN.measure(probe)
	_actor.set("seated_shape_cache", _measured_motion.get("seated_shapes", []))
	probe.free()
	return not _measured_motion.is_empty() or _fail("Original clip endpoint measurement failed")


func _desk_chair() -> bool:
	if _chair_prepared:
		await run_chair_trial()
		return _phase.begins_with("PHYSICS TRIAL ENDED") or _fail(_phase + "; " + _collision_reason())
	if not await _walk_anchor("dorm-01/bed-01"): return false
	_room = preload("res://runtime/lab/chair_review_room.gd").new()
	add_child(_room)
	var scope := Node3D.new()
	_geometry.add_child(scope)
	for mesh: MeshInstance3D in _geometry.find_children("*", "MeshInstance3D", true, false):
		var extra := mesh.get_meta("extras", {}) as Dictionary
		if extra.get("module") == "M01" and int(extra.get("floor", 1)) == 1: mesh.reparent(scope, true)
	_room.geometry = scope
	_room.physics = _tour_world.physics
	_room.semantics = _tour_world.semantics
	_marker = _nest.resolve_anchor("dorm-01/chair-01")
	var seating := PLAN.seating_contact(scope, _marker.get_meta("interaction_transform") as Transform3D)
	if seating.is_empty(): return _fail("Original chair-facing annotation missing")
	_contact = seating["transform"]
	_closed_contact = _contact
	_swivel = _room.configure_swivel()
	if _swivel == null: return _fail("Original chair swivel/collision binding failed")
	_player.remove_animation_library("chair")
	_player.add_animation_library("chair", CLIPS.library_for(_actor, true))
	if not await _measure_motion(): return false
	_chair_prepared = true
	# Reuse the confirmed physical trial, including contact and sweep rejection.
	await run_chair_trial()
	return _phase.begins_with("PHYSICS TRIAL ENDED") or _fail(_phase + "; " + _collision_reason())


func _water_chapter(id: String) -> bool:
	if not await _walk_anchor("courtyard/activity"): return false
	var wanted := "Reference fountain water" if id in ["fountain", "water-night"] else ("COMPLETE Inset natural lake receiving under spillway" if id == "spillway" else "COMPLETE Inset natural lake")
	var mesh := _mesh("", wanted)
	if mesh == null: return _fail("Actual water surface missing: " + wanted)
	var bounds := mesh.global_transform * mesh.get_aabb()
	var target := bounds.get_center()
	var shore := NavigationServer3D.map_get_closest_point(get_world_3d().navigation_map, target)
	if not await _walk("Walk to water viewing point", shore): return _fail(_phase)
	# Only the camera moves off the walkable ground, never the actor.
	_camera.global_position = target + Vector3(4, 3, 5)
	_camera.look_at(target)
	_ready_camera = false
	if _water == null:
		_water = preload("res://rooms/estate/estate_water_display.gd").new()
		add_child(_water)
		_water.bind(_geometry, (_nest.get_node("WorldEnvironment") as WorldEnvironment).environment, true)
		_water.set_process(false)
		_splash = preload("res://runtime/lab/estate_fountain_splash.gd").new()
		add_child(_splash)
		_splash.bind(_geometry)
	await _wait(12.0, func(seconds: float) -> void:
		_water.sample(seconds, id == "water-night")
		_splash.sample(seconds))
	_ready_camera = true
	return true


func _sleep_chapter(id: String) -> bool:
	if _bed_journey == null:
		if not await _walk_anchor("dorm-01/bed-01"): return false
		var duvet: MeshInstance3D
		for mesh: MeshInstance3D in _geometry.find_children("*", "MeshInstance3D", true, false):
			var extra := mesh.get_meta("extras", {}) as Dictionary
			if extra.get("module") == "M01" and extra.get("resident") == "A" and extra.get("piece") == "bed_cover": duvet = mesh
		_bed_journey = preload("res://runtime/lab/estate_sleep_journey.gd").new()
		add_child(_bed_journey)
		var prepared: String = _bed_journey.prepare(_actor, _nest.resolve_anchor("dorm-01/bed-01"), duvet, _geometry, _tour_world.physics, "dorm-01/bed-01")
		if not prepared.is_empty(): return _fail(prepared)
	if _bed_journey.active:
		var exit_error: String = _bed_journey.finish()
		return exit_error.is_empty() or _fail(exit_error)
	if not await _walk("Walk to measured bedside", _bed_journey.goal_position): return _fail(_phase)
	_actor.call("walk_precisely", _bed_journey.goal_position, 8.0)
	var terminal: Signal = _actor.get("precision_terminal")
	var result: Array = await terminal
	if not bool(result[0]): return _fail("Physical bedside approach failed: " + str(result))
	# Navigation completion can be emitted inside a physics callback. Contact
	# setup and shape-state changes happen on the following render frame.
	await _review_process_frame()
	var selected := "side-left" if id == "sleep-left" else ("side-right" if id == "sleep-right" else "back")
	_phase = "Checking actual bed/contact clearance / " + selected
	var contact_error: String = _bed_journey.begin(selected)
	if not contact_error.is_empty(): return _fail(contact_error)
	await _wait(0.5, func(seconds: float) -> void: _bed_journey.blend_entry(seconds / 0.5))
	if id == "embodiment":
		await _wait(5.5, func(seconds: float) -> void: _bed_journey.sample(1.5 + seconds))
		await _wait(5.5, Callable(_bed_journey.effects, "preview_cover"))
		await _wait(4.0, func(seconds: float) -> void: _bed_journey.sample(12.0 + seconds))
	else:
		await _wait(14.5, func(seconds: float) -> void:
			_bed_journey.sample(1.5 + seconds)
			_phase = "Original duvet / %s / %s" % [selected, _bed_journey.review.get("animation_stage")])
	var exit_error: String = _bed_journey.finish()
	if not exit_error.is_empty(): return _fail(exit_error)
	await _wait(0.7)
	return true


func _mesh(module: String, prefix: String) -> MeshInstance3D:
	for mesh: MeshInstance3D in _geometry.find_children("*", "MeshInstance3D", true, false):
		var extra := mesh.get_meta("extras", {}) as Dictionary
		if not module.is_empty() and str(extra.get("module", "")) != module: continue
		if str(extra.get("source_name", mesh.name)).begins_with(prefix): return mesh
	return null


func _assembly(module: String, assembly: String) -> MeshInstance3D:
	for mesh: MeshInstance3D in _geometry.find_children("*", "MeshInstance3D", true, false):
		var extra := mesh.get_meta("extras", {}) as Dictionary
		if extra.get("module") == module and extra.get("assembly") == assembly: return mesh
	return null
