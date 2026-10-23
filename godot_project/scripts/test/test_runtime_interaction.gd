extends SceneTree

const ACTOR_CONTROLLER_SCRIPT := preload("res://runtime/actor/actor_controller.gd")
const WORLD_CONTROLLER_SCRIPT := preload("res://runtime/world/world_controller.gd")
const SPATIAL_QUERIES := preload("res://runtime/world/spatial_queries.gd")
const ACTOR_SCENES := {
	"tovren": preload("res://characters/tovren/tovren.tscn"),
	"saevi": preload("res://characters/saevi/saevi.tscn"),
}


func _init() -> void:
	var main := (load("res://main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	var nest := main.get_node("Nest") as ModularNest
	var world_controller := WORLD_CONTROLLER_SCRIPT.new()
	root.add_child(world_controller)
	world_controller.setup(nest)
	var configured: Dictionary = await world_controller.configure_world(
		{"nest_id": "interaction-test", "bed_count": 32, "world_revision": 1},
		"configure-1",
	)
	if not bool(configured.get("accepted", false)):
		_fail("Interaction world failed to configure")
		return

	var controller := ACTOR_CONTROLLER_SCRIPT.new()
	root.add_child(controller)
	controller.setup(
		nest,
		main.get_node("Characters") as Node3D,
		ACTOR_SCENES,
		false,
	)
	world_controller.set_actor_provider(
		Callable(controller, "actor_instances")
	)
	var synced := controller.sync_actors([
		{
			"actor_id": "saevi-1",
			"species": "saevi",
			"spawn_anchor_id": "dorm-01/bed-02",
			"appearance": {},
		},
		{
				"actor_id": "tovren-1",
				"species": "tovren",
			"spawn_anchor_id": "dorm-01/bed-01",
			"appearance": {},
		},
	]) as Dictionary
	if not bool(synced.get("accepted", false)):
		_fail("Interaction actors failed to sync")
		return
	# Face the observer toward the second actor so this test exercises the
	# positive FOV path rather than relying on the scene's default orientation.
	var saevi := controller.actor("saevi-1")
	var tovren := controller.actor("tovren-1")
	if not _place_query_pair(nest, saevi, tovren, 1.0, 3.5, true):
		_fail("No clear nearby query fixture exists at the real dorm anchors")
		return
	await physics_frame
	_face_toward(saevi, tovren.global_position)

	var events: Array[Dictionary] = []
	world_controller.runtime_event.connect(
		func(name: String, payload: Dictionary, _cause_id: String) -> void:
			events.append({"name": name, "payload": payload})
	)
	controller.runtime_event.connect(
		func(name: String, payload: Dictionary, _cause_id: String) -> void:
			events.append({"name": name, "payload": payload})
	)
	world_controller.resolve_speech_reach({
		"command_id": "speech-1",
		"actor_id": "saevi-1",
		"acoustic_profile": "normal",
	})
	controller.execute_intent({
		"command_id": "speech-1",
		"actor_id": "saevi-1",
		"intent": "speak",
		"deadline_seconds": 2.0,
	})
	var audience: Variant = _event_payload(events, "speech_reach", "speech-1")
	if audience == null or audience.get("audience_actor_ids", []) != ["tovren-1"]:
		_fail("Speech audience was not limited to the active semantic zone")
		return
	world_controller.resolve_visual_observation({
		"observation_id": "vision-1",
		"actor_id": "saevi-1",
		"max_results": 8,
	})
	var visual: Variant = _event_payload(events, "visual_observation", "vision-1")
	var visible_ids: Array = [] if visual == null else visual.get(
		"visible_semantic_ids",
		[],
	)
	if visual == null or "actor/tovren-1" not in visible_ids:
		_fail("Semantic visual observation did not include the nearby actor")
		return
	var rest_marker := nest.resolve_facility("dorm-01/rest")
	if rest_marker == null:
		_fail("Semantic facility marker was not built")
		return
	var nearby_target_position := tovren.global_position
	_face_toward(saevi, rest_marker.global_position)
	tovren.global_position = saevi.global_position - saevi.global_basis.z.normalized()
	await physics_frame
	world_controller.resolve_visual_observation({
		"observation_id": "facility-visible",
		"actor_id": "saevi-1",
		"max_results": 64,
	})
	var visible_facilities: Variant = _event_payload(events, "visual_observation", "facility-visible")
	if visible_facilities == null or "facility/dorm-01/rest" not in visible_facilities.get("visible_semantic_ids", []):
		_fail("Semantic visual observation did not apply physical filtering to a facility")
		return
	var rest_position := rest_marker.global_position
	rest_marker.global_position = saevi.global_position - saevi.global_basis.z.normalized()
	world_controller.resolve_visual_observation({
		"observation_id": "facility-behind",
		"actor_id": "saevi-1",
		"max_results": 64,
	})
	var hidden_facilities: Variant = _event_payload(events, "visual_observation", "facility-behind")
	if hidden_facilities == null or "facility/dorm-01/rest" in hidden_facilities.get("visible_semantic_ids", []):
		_fail("Semantic visual observation returned a facility outside the visual cone")
		return
	rest_marker.global_position = rest_position
	tovren.global_position = nearby_target_position
	_face_toward(saevi, tovren.global_position)
	var observer_position := saevi.global_position
	var target_position := tovren.global_position
	# A target behind the observer must not be returned by the World query.
	tovren.global_position = observer_position - saevi.global_basis.z.normalized()
	world_controller.resolve_visual_observation({
		"observation_id": "vision-behind",
		"actor_id": "saevi-1",
		"max_results": 8,
	})
	var behind: Variant = _event_payload(events, "visual_observation", "vision-behind")
	if behind == null or "actor/tovren-1" in behind.get("visible_semantic_ids", []):
		_fail("World visual query returned an actor behind the observer")
		return
	tovren.global_position = target_position
	var visual_obstacle := _add_query_obstacle(main, observer_position, target_position)
	await physics_frame
	world_controller.resolve_visual_observation({
		"observation_id": "vision-occluded",
		"actor_id": "saevi-1",
		"max_results": 8,
	})
	var occluded: Variant = _event_payload(events, "visual_observation", "vision-occluded")
	if occluded == null or "actor/tovren-1" in occluded.get("visible_semantic_ids", []):
		_fail("World visual query returned an occluded actor")
		return
	visual_obstacle.queue_free()
	await physics_frame
	# The bounded result contract is enforced by World, not by Nest.
	world_controller.resolve_visual_observation({
		"observation_id": "vision-bounded",
		"actor_id": "saevi-1",
		"max_results": 1,
	})
	var bounded: Variant = _event_payload(events, "visual_observation", "vision-bounded")
	if bounded == null or (bounded.get("visible_semantic_ids", []) as Array).size() != 1:
		_fail("World visual query exceeded the requested result bound")
		return
	# A quiet voice cannot cross the same physical distance as a normal voice.
	if not _place_query_pair(
		nest, saevi, tovren, SPATIAL_QUERIES.speech_range("quiet") + 0.5,
		SPATIAL_QUERIES.speech_range("normal") - 0.5,
	):
		_fail("No clear same-room anchor pair spans quiet but not normal speech range")
		return
	await physics_frame
	world_controller.resolve_speech_reach({
		"command_id": "speech-normal-range", "actor_id": "saevi-1",
		"acoustic_profile": "normal",
	})
	var normal_range: Variant = _event_payload(events, "speech_reach", "speech-normal-range")
	if normal_range == null or "tovren-1" not in normal_range.get("audience_actor_ids", []):
		_fail("Speech range fixture was already inaudible before applying the quiet limit")
		return
	world_controller.resolve_speech_reach({
		"command_id": "speech-quiet-range",
		"actor_id": "saevi-1",
		"acoustic_profile": "quiet",
	})
	var quiet_range: Variant = _event_payload(events, "speech_reach", "speech-quiet-range")
	if quiet_range == null or "tovren-1" in quiet_range.get("audience_actor_ids", []):
		_fail("Quiet speech ignored its bounded acoustic range")
		return
	saevi.global_position = observer_position
	tovren.global_position = target_position
	var speech_obstacle := _add_query_obstacle(main, observer_position, target_position)
	await physics_frame
	world_controller.resolve_speech_reach({
		"command_id": "speech-occluded",
		"actor_id": "saevi-1",
		"acoustic_profile": "loud",
	})
	var occluded_speech: Variant = _event_payload(events, "speech_reach", "speech-occluded")
	if occluded_speech == null or "tovren-1" in occluded_speech.get("audience_actor_ids", []):
		_fail("Speech reach ignored physical occlusion")
		return
	speech_obstacle.queue_free()
	await physics_frame

	controller.execute_intent({
		"command_id": "expression-1",
		"actor_id": "saevi-1",
		"intent": "emotion_expression",
		"expression": "happy",
		"deadline_seconds": 2.0,
	})
	if (
		String(controller.actor("saevi-1").get_meta("runtime_expression", ""))
		!= "happy"
	):
		_fail("Supported expression was not observable on the actor")
		return
	controller.execute_intent({
		"command_id": "expression-bad",
		"actor_id": "saevi-1",
		"intent": "emotion_expression",
		"expression": "not-supported",
		"deadline_seconds": 2.0,
	})
	var unsupported: Variant = _event_payload(
		events,
		"intent_terminal",
		"expression-bad",
	)
	if (
		unsupported == null
		or String(unsupported.get("status", "")) != "failed"
		or String(unsupported.get("reason", "")) != "unsupported_expression"
	):
		_fail("Unsupported expression did not fail explicitly")
		return
	var progress_probe := controller.actor("tovren-1")
	var probe_home := progress_probe.global_position
	var probe_terminals: Array[String] = []
	progress_probe.navigation_terminal.connect(
		func(command_id: String, _status: String, _reason: String) -> void:
			probe_terminals.append(command_id)
	)
	progress_probe.set_physics_process(false)
	var segment := _courtyard_walk_segment(nest)
	if segment.size() != 2:
		_fail("No real courtyard navigation segment can host the slow-progress probe")
		return
	progress_probe.global_position = segment[0] + Vector3.UP * 0.02
	var probe_direction := (segment[1] - segment[0]).normalized()
	progress_probe.active_command_id = "slow-progress-1"
	var agent := progress_probe.get_node("NavigationAgent3D") as NavigationAgent3D
	agent.avoidance_enabled = false
	var probe_start := progress_probe.global_position
	for _frame in range(100):
		progress_probe._on_avoidance_velocity_computed(probe_direction * 0.1)
		await physics_frame
	if (
		"slow-progress-1" in probe_terminals
		or progress_probe.global_position.distance_to(probe_start) < 0.1
	):
		_fail("Slow but measurable avoidance progress was marked as blocked")
		return
	progress_probe.active_command_id = ""
	progress_probe.velocity = Vector3.ZERO
	progress_probe.global_position = probe_home
	agent.avoidance_enabled = true
	progress_probe.set_physics_process(true)
	controller.execute_intent({
		"command_id": "move-clear-1",
		"actor_id": "saevi-1",
		"intent": "move_to_anchor",
		"anchor_id": "central-01/activity",
		"deadline_seconds": 10.0,
	})
	for _frame in range(600):
		await physics_frame
		if _event_payload(events, "intent_terminal", "move-clear-1") != null:
			break
	var clear_move: Variant = _event_payload(
		events,
		"intent_terminal",
		"move-clear-1",
	)
	if clear_move == null or String(clear_move.get("status", "")) != "completed":
		_fail(
			"Two synchronized actors could not navigate without an obstacle: "
			+ "saevi=%s tovren=%s distance=%.3f terminal=%s"
			% [
				str(controller.actor("saevi-1").global_position),
				str(controller.actor("tovren-1").global_position),
				controller.actor("saevi-1").global_position.distance_to(
					controller.actor("tovren-1").global_position
				),
				JSON.stringify(clear_move),
			]
		)
		return
	var obstacle := _add_runtime_obstacle(
		main, saevi, nest.resolve_anchor("dorm-01/bed-02").global_position,
	)
	if obstacle == null:
		_fail("No actual return path exists for the dynamic collision test")
		return
	await physics_frame
	controller.execute_intent({
		"command_id": "blocked-1",
		"actor_id": "saevi-1",
		"intent": "move_to_anchor",
		"anchor_id": "dorm-01/bed-02",
		"deadline_seconds": 10.0,
	})
	for _frame in range(600):
		await physics_frame
		if _event_payload(events, "intent_terminal", "blocked-1") != null:
			break
	var blocked: Variant = _event_payload(
		events,
		"intent_terminal",
		"blocked-1",
	)
	if (
		blocked == null
		or String(blocked.get("status", "")) != "failed"
		or String(blocked.get("reason", "")) != "movement_blocked"
	):
		_fail("Physical obstruction did not produce movement_blocked terminal")
		return
	var tactile_count := _tactile_count(events, "saevi-1", obstacle.name)
	if tactile_count < 1 or tactile_count > 2:
		_fail("Significant contact was not emitted with cooldown")
		return

	print("Runtime interaction contract passed")
	quit()


func _event_payload(
	events: Array[Dictionary],
	event_name: String,
	command_id: String,
) -> Variant:
	for event in events:
		var payload := event["payload"] as Dictionary
		if (
			String(event["name"]) == event_name
			and String(
				payload.get("command_id", payload.get("observation_id", ""))
			) == command_id
		):
			return payload
	return null


func _add_runtime_obstacle(parent: Node, actor: ElfieActor, target: Vector3) -> StaticBody3D:
	var path := NavigationServer3D.map_get_path(
		actor.get_world_3d().navigation_map, actor.global_position, target, true,
	)
	var direction := Vector3.ZERO
	for point: Vector3 in path:
		var offset := point - actor.global_position
		offset.y = 0.0
		if offset.length() > 0.3:
			direction = offset.normalized()
			break
	if direction.is_zero_approx():
		return null
	var body := StaticBody3D.new()
	body.name = "RuntimeTestObstacle"
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(1.2, 1.8, 0.35)
	collision.shape = shape
	body.add_child(collision)
	parent.add_child(body)
	body.global_position = actor.global_position + direction * 0.65 + Vector3.UP * 0.9
	body.look_at(body.global_position + direction, Vector3.UP)
	return body


func _add_query_obstacle(parent: Node, first: Vector3, second: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = "QueryObstacle"
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(0.8, 1.8, 0.28)
	collision.shape = shape
	body.add_child(collision)
	parent.add_child(body)
	body.global_position = (first + second) / 2.0 + Vector3.UP * 0.9
	body.look_at(second + Vector3.UP * 0.9, Vector3.UP)
	return body


func _face_toward(actor: ElfieActor, target: Vector3) -> void:
	var offset := target - actor.global_position
	offset.y = 0.0
	actor.look_at(actor.global_position - offset, Vector3.UP)


func _place_query_pair(
	nest: ModularNest, first: ElfieActor, second: ElfieActor,
	minimum: float, maximum: float, require_facility_view: bool = false,
) -> bool:
	var points: Array[Vector3] = []
	var map := nest.get_world_3d().navigation_map
	var rest := nest.resolve_facility("dorm-01/rest")
	for id in nest.semantic_anchor_ids():
		var marker := nest.resolve_anchor(id)
		if marker == null or marker.get_meta("zone_id", "") != "dorm-01":
			continue
		if not NavigationServer3D.map_get_closest_point_owner(map, marker.global_position).is_valid():
			continue
		var point := NavigationServer3D.map_get_closest_point(map, marker.global_position)
		if point.distance_to(marker.global_position) > 0.5:
			continue
		points.append(point + Vector3.UP * 0.02)
	for a: Vector3 in points:
		for b: Vector3 in points:
			var distance := a.distance_to(b)
			if distance < minimum or distance > maximum:
				continue
			if nest.nearest_zone_id(a) != "dorm-01" or nest.nearest_zone_id(b) != "dorm-01":
				continue
			if require_facility_view:
				if rest == null or a.distance_to(rest.global_position) < 0.5:
					continue
				if not SPATIAL_QUERIES.has_line_of_sight(
					nest.get_world_3d(), a + Vector3.UP * SPATIAL_QUERIES.VISUAL_EYE_HEIGHT,
					rest.global_position + Vector3.UP * 0.6,
					null, [first.get_rid(), second.get_rid()],
				):
					continue
			if not SPATIAL_QUERIES.has_line_of_sight(
				nest.get_world_3d(), a + Vector3.UP * SPATIAL_QUERIES.VISUAL_EYE_HEIGHT,
				b + Vector3.UP * SPATIAL_QUERIES.ACTOR_TARGET_HEIGHT,
				null, [first.get_rid(), second.get_rid()],
			):
				continue
			first.global_position = a
			second.global_position = b
			return true
	return false


func _courtyard_walk_segment(nest: ModularNest) -> PackedVector3Array:
	var start := nest.resolve_anchor("courtyard/activity")
	var target := nest.resolve_anchor("courtyard/picnic-seat")
	if start == null or target == null:
		return PackedVector3Array()
	var path := NavigationServer3D.map_get_path(
		nest.get_world_3d().navigation_map, start.global_position, target.global_position, true,
	)
	if path.is_empty() or path[path.size() - 1].distance_to(target.global_position) > 1.35:
		return PackedVector3Array()
	for index in range(1, path.size()):
		if path[index - 1].distance_to(path[index]) > 1.0 and absf(path[index].y - path[index - 1].y) < 0.05:
			return PackedVector3Array([path[index - 1], path[index]])
	return PackedVector3Array()


func _tactile_count(
	events: Array[Dictionary],
	actor_id: String,
	source_id: String,
) -> int:
	var count := 0
	for event in events:
		if String(event["name"]) != "tactile_contact":
			continue
		var payload := event["payload"] as Dictionary
		if (
			String(payload.get("actor_id", "")) == actor_id
			and String(payload.get("source_semantic_id", "")) == source_id
		):
			count += 1
	return count


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
