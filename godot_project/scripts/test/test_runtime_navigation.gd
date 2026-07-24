extends SceneTree

const ACTOR_CONTROLLER_SCRIPT := preload("res://runtime/actor_controller.gd")
const WORLD_CONTROLLER_SCRIPT := preload("res://runtime/world_controller.gd")
const ACTOR_SCENES := {
	"dog": preload("res://characters/dog/dog.tscn"),
	"fox": preload("res://characters/fox/fox.tscn"),
}


func _init() -> void:
	var main_scene := load("res://main.tscn") as PackedScene
	var main := main_scene.instantiate()
	main.get_node("CameraStreamBridge").process_mode = Node.PROCESS_MODE_DISABLED
	root.add_child(main)
	await process_frame
	var nest := main.get_node("Nest") as ModularNest
	var characters := main.get_node("Characters") as Node3D
	var world_controller := WORLD_CONTROLLER_SCRIPT.new()
	root.add_child(world_controller)
	world_controller.setup(nest)
	var configured: Dictionary = await world_controller.configure_world(
		{
			"nest_id": "navigation-test",
			"bed_count": 4,
			"world_revision": 1,
		},
		"configure-1",
	)
	if not bool(configured.get("accepted", false)):
		push_error("Navigation test world failed to configure")
		quit(1)
		return

	var actor_controller := ACTOR_CONTROLLER_SCRIPT.new()
	root.add_child(actor_controller)
	actor_controller.setup(nest, characters, ACTOR_SCENES, false)
	var sync_result := actor_controller.sync_actors([
		{
			"actor_id": "fox-1",
			"species": "fox",
			"home_anchor_id": "dorm-01/bed-01",
			"appearance": {},
		},
	]) as Dictionary
	if not bool(sync_result.get("accepted", false)):
		push_error("Navigation test actor failed to sync")
		quit(1)
		return
	var events: Array[Dictionary] = []
	actor_controller.runtime_event.connect(
		func(event_name: String, payload: Dictionary, _correlation_id: String) -> void:
			events.append({"name": event_name, "payload": payload})
	)
	actor_controller.execute_intent({
		"command_id": "move-1",
		"actor_id": "fox-1",
		"intent": "move_to_anchor",
		"anchor_id": "activity-01/activity",
		"deadline_seconds": 20.0,
	})
	for _frame in range(1200):
		await physics_frame
		if _terminal_for(events, "move-1") != null:
			break
	var terminal: Variant = _terminal_for(events, "move-1")
	if terminal == null or String(terminal.get("status", "")) != "completed":
		var fox := actor_controller.actor("fox-1")
		var navigation_map := nest.get_world_3d().navigation_map
		var target := nest.resolve_anchor("activity-01/activity").global_position
		var path := NavigationServer3D.map_get_path(
			navigation_map,
			fox.global_position,
			target,
			true,
		)
		push_error(
			"Semantic navigation failed: terminal=%s position=%s target=%s path=%s"
			% [
				JSON.stringify(terminal),
				str(fox.global_position),
				str(target),
				str(path),
			]
		)
		quit(1)
		return
	if _count_event(events, "intent_accepted", "move-1") != 1:
		push_error("Move intent was not accepted exactly once")
		quit(1)
		return
	if _count_event(events, "intent_started", "move-1") != 1:
		push_error("Move intent was not started exactly once")
		quit(1)
		return

	actor_controller.execute_intent({
		"command_id": "unknown-1",
		"actor_id": "fox-1",
		"intent": "move_to_anchor",
		"anchor_id": "missing/anchor",
		"deadline_seconds": 5.0,
	})
	var unknown: Variant = _terminal_for(events, "unknown-1")
	if unknown == null or String(unknown.get("status", "")) != "failed":
		push_error("Unknown semantic anchor did not fail deterministically")
		quit(1)
		return

	actor_controller.execute_intent({
		"command_id": "cancel-1",
		"actor_id": "fox-1",
		"intent": "move_to_anchor",
		"anchor_id": "dorm-01/bed-02",
		"deadline_seconds": 20.0,
	})
	await physics_frame
	actor_controller.cancel_intent({
		"command_id": "cancel-1",
		"actor_id": "fox-1",
	})
	var cancelled: Variant = _terminal_for(events, "cancel-1")
	if cancelled == null or String(cancelled.get("status", "")) != "cancelled":
		push_error("Active navigation cancel did not emit one cancelled terminal")
		quit(1)
		return

	var started_before := _count_event(events, "intent_started", "move-1")
	actor_controller.execute_intent({
		"command_id": "move-1",
		"actor_id": "fox-1",
		"intent": "move_to_anchor",
		"anchor_id": "activity-01/activity",
		"deadline_seconds": 20.0,
	})
	if _count_event(events, "intent_started", "move-1") != started_before:
		push_error("Duplicate command ID started a second movement")
		quit(1)
		return

	actor_controller.execute_intent({
		"command_id": "deadline-1",
		"actor_id": "fox-1",
		"intent": "move_to_anchor",
		"anchor_id": "dorm-01/bed-03",
		"deadline_seconds": 0.001,
	})
	for _frame in range(10):
		await physics_frame
	var deadline_terminal: Variant = _terminal_for(events, "deadline-1")
	if (
		deadline_terminal == null
		or String(deadline_terminal.get("reason", "")) != "deadline_exceeded"
	):
		push_error("Navigation deadline did not produce one stable failure")
		quit(1)
		return

	var multi_sync := actor_controller.sync_actors([
		{
			"actor_id": "fox-1",
			"species": "fox",
			"home_anchor_id": "dorm-01/bed-01",
			"appearance": {},
		},
		{
			"actor_id": "dog-1",
			"species": "dog",
			"home_anchor_id": "dorm-01/bed-02",
			"appearance": {},
		},
	]) as Dictionary
	if not bool(multi_sync.get("accepted", false)):
		push_error("Two-actor catalog failed to sync")
		quit(1)
		return
	actor_controller.execute_intent({
		"command_id": "multi-fox",
		"actor_id": "fox-1",
		"intent": "move_to_anchor",
		"anchor_id": "activity-01/activity",
		"deadline_seconds": 20.0,
	})
	actor_controller.execute_intent({
		"command_id": "multi-dog",
		"actor_id": "dog-1",
		"intent": "move_to_anchor",
		"anchor_id": "dorm-01/door",
		"deadline_seconds": 20.0,
	})
	for _frame in range(1200):
		await physics_frame
		if (
			_terminal_for(events, "multi-fox") != null
			and _terminal_for(events, "multi-dog") != null
		):
			break
	for command_id: String in ["multi-fox", "multi-dog"]:
		var multi_terminal: Variant = _terminal_for(events, command_id)
		if (
			multi_terminal == null
			or String(multi_terminal.get("status", "")) != "completed"
		):
			push_error(
				"Concurrent navigation did not complete: %s terminal=%s"
				% [command_id, JSON.stringify(multi_terminal)]
			)
			quit(1)
			return

	actor_controller.execute_intent({
		"command_id": "removed-1",
		"actor_id": "fox-1",
		"intent": "move_to_anchor",
		"anchor_id": "activity-01/activity",
		"deadline_seconds": 20.0,
	})
	actor_controller.sync_actors([
		{
			"actor_id": "dog-1",
			"species": "dog",
			"home_anchor_id": "dorm-01/bed-02",
			"appearance": {},
		},
	])
	var removed_terminal: Variant = _terminal_for(events, "removed-1")
	if (
		removed_terminal == null
		or String(removed_terminal.get("status", "")) != "cancelled"
		or String(removed_terminal.get("reason", "")) != "actor_removed"
	):
		push_error("Actor removal did not cancel its active command")
		quit(1)
		return

	print("Runtime semantic navigation contract passed")
	quit()


func _terminal_for(events: Array[Dictionary], command_id: String) -> Variant:
	for event in events:
		if (
			String(event["name"]) == "intent_terminal"
			and String((event["payload"] as Dictionary).get("command_id", ""))
			== command_id
		):
			return event["payload"] as Dictionary
	return null


func _count_event(
	events: Array[Dictionary],
	event_name: String,
	command_id: String,
) -> int:
	var count := 0
	for event in events:
		if (
			String(event["name"]) == event_name
			and String((event["payload"] as Dictionary).get("command_id", ""))
			== command_id
		):
			count += 1
	return count
