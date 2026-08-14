extends SceneTree

const ENVIRONMENT_CONTROLLER_SCRIPT := preload("res://runtime/world/environment_controller.gd")
const WORLD_CONTROLLER_SCRIPT := preload("res://runtime/world/world_controller.gd")


func _init() -> void:
	var main := (load("res://main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	var nest := main.get_node("Nest") as ModularNest
	var world_controller := WORLD_CONTROLLER_SCRIPT.new()
	root.add_child(world_controller)
	world_controller.setup(nest)
	var configured: Dictionary = await world_controller.configure_world(
		{"nest_id": "environment-test", "bed_count": 4, "world_revision": 1},
		"configure-1",
	)
	if not bool(configured.get("accepted", false)):
		_fail("Environment world failed to configure")
		return

	var controller := ENVIRONMENT_CONTROLLER_SCRIPT.new()
	root.add_child(controller)
	controller.setup(nest)
	var events: Array[Dictionary] = []
	controller.runtime_event.connect(
		func(event_name: String, payload: Dictionary, _cause_id: String) -> void:
			events.append({"name": event_name, "payload": payload})
	)
	controller.apply_environment({
		"object_id": "nest/environment",
		"command_id": "environment-1",
		"lights_on": false,
		"quiet_mode": true,
	})
	var result: Variant = _event_payload(events, "environment-1")
	if result == null or not bool(result.get("applied", false)):
		_fail("Environment state was not applied")
		return
	if String(result.get("object_id", "")) != "nest/environment":
		_fail("Environment state lost its stable object ID")
		return
	var generated := nest.get_node("Generated") as Node3D
	var lights := generated.find_children("*", "Light3D", true, false)
	for light_value: Node in lights:
		if (light_value as Light3D).visible:
			_fail("Environment off state left a light visible")
			return
	controller.apply_environment({
		"object_id": "nest/environment",
		"command_id": "environment-2",
		"lights_on": true,
		"quiet_mode": false,
	})
	if not _event_payload(events, "environment-2").get("applied", false):
		_fail("Environment state did not restore lights")
		return
	controller.apply_environment({
		"object_id": "unsupported/object",
		"command_id": "environment-3",
		"lights_on": false,
		"quiet_mode": false,
	})
	var unsupported: Variant = _event_payload(events, "environment-3")
	if unsupported == null or bool(unsupported.get("applied", true)):
		_fail("Unsupported environment object was applied")
		return
	print("Runtime environment contract passed")
	quit()


func _event_payload(events: Array[Dictionary], command_id: String) -> Variant:
	for event in events:
		var payload := event["payload"] as Dictionary
		if String(payload.get("command_id", "")) == command_id:
			return payload
	return null


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
