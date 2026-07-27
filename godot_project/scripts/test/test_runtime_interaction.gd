extends SceneTree

const ACTOR_CONTROLLER_SCRIPT := preload("res://runtime/actor_controller.gd")
const WORLD_CONTROLLER_SCRIPT := preload("res://runtime/world_controller.gd")
const ACTOR_SCENES := {
	"dog": preload("res://characters/dog/dog.tscn"),
	"fox": preload("res://characters/fox/fox.tscn"),
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
		{"nest_id": "interaction-test", "bed_count": 4, "world_revision": 1},
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
	var synced := controller.sync_actors([
		{
			"actor_id": "fox-1",
			"species": "fox",
			"home_anchor_id": "dorm-01/bed-02",
			"appearance": {},
		},
		{
				"actor_id": "dog-1",
				"species": "dog",
				"home_anchor_id": "dorm-01/bed-01",
			"appearance": {},
		},
	]) as Dictionary
	if not bool(synced.get("accepted", false)):
		_fail("Interaction actors failed to sync")
		return

	var events: Array[Dictionary] = []
	controller.runtime_event.connect(
		func(name: String, payload: Dictionary, _correlation_id: String) -> void:
			events.append({"name": name, "payload": payload})
	)
	controller.execute_intent({
		"command_id": "speech-1",
		"actor_id": "fox-1",
		"intent": "speak",
		"text": "你好",
		"deadline_seconds": 2.0,
	})
	var audience: Variant = _event_payload(events, "speech_audience", "speech-1")
	if audience == null or audience.get("audience_actor_ids", []) != ["dog-1"]:
		_fail("Speech audience was not limited to the active semantic zone")
		return

	controller.execute_intent({
		"command_id": "expression-1",
		"actor_id": "fox-1",
		"intent": "emotion_expression",
		"expression": "happy",
		"deadline_seconds": 2.0,
	})
	if (
		String(controller.actor("fox-1").get_meta("runtime_expression", ""))
		!= "happy"
	):
		_fail("Supported expression was not observable on the actor")
		return
	controller.execute_intent({
		"command_id": "expression-bad",
		"actor_id": "fox-1",
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
	var progress_probe := controller.actor("dog-1")
	var probe_home := progress_probe.global_position
	var probe_terminals: Array[String] = []
	progress_probe.navigation_terminal.connect(
		func(command_id: String, _status: String, _reason: String) -> void:
			probe_terminals.append(command_id)
	)
	progress_probe.set_physics_process(false)
	progress_probe.global_position = Vector3(0.0, 0.02, -2.25)
	progress_probe.active_command_id = "slow-progress-1"
	var probe_start := progress_probe.global_position
	for _frame in range(100):
		progress_probe._on_avoidance_velocity_computed(Vector3(0.1, 0.0, 0.0))
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
	progress_probe.set_physics_process(true)
	controller.execute_intent({
		"command_id": "move-clear-1",
		"actor_id": "fox-1",
		"intent": "move_to_anchor",
		"anchor_id": "activity-01/activity",
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
			+ "fox=%s dog=%s distance=%.3f terminal=%s"
			% [
				str(controller.actor("fox-1").global_position),
				str(controller.actor("dog-1").global_position),
				controller.actor("fox-1").global_position.distance_to(
					controller.actor("dog-1").global_position
				),
				JSON.stringify(clear_move),
			]
		)
		return
	var obstacle := _add_runtime_obstacle(main)
	controller.execute_intent({
		"command_id": "blocked-1",
		"actor_id": "fox-1",
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
	var tactile_count := _tactile_count(events, "fox-1", obstacle.name)
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
			and String(payload.get("command_id", "")) == command_id
		):
			return payload
	return null


func _add_runtime_obstacle(parent: Node) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = "RuntimeTestObstacle"
	body.position = Vector3(0.62, 0.9, -2.25)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(0.35, 1.8, 1.2)
	collision.shape = shape
	body.add_child(collision)
	parent.add_child(body)
	return body


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
