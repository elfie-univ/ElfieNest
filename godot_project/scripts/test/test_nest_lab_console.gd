extends SceneTree

const CONSOLE := preload("res://runtime/lab/nest_lab_console.gd")
const NEST := preload("res://rooms/nest.tscn")


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var nest := NEST.instantiate() as ModularNest
	root.add_child(nest)
	var characters := Node3D.new()
	root.add_child(characters)
	var console := CONSOLE.new()
	root.add_child(console)
	console.setup(nest, characters)
	await process_frame
	if not check(console.camera_command({"action":"environment", "environment":{"phase":"dusk", "lights_on":true,"quiet_mode":false}}), "Cannot receive Nest environment"): return
	if not check(console.camera_command({"action": "select", "view_id": "central-1"}), "Cannot select actual estate camera"): return
	if not check(console.catalog()["active_id"] == "central-1", "Camera acknowledgement differs from selected view"): return
	if not check(not console.camera_command({"action": "select", "view_id": "missing"}), "Unknown camera was accepted"): return
	if not check(console.camera_command({"action": "select", "view_id": "lighting-night"}), "Missing Lab lighting preview"): return
	if not check(console.catalog()["active_id"] == "central-1", "Lighting changed the camera"): return
	if not check(not console.catalog()["scene_actions"].is_empty(), "Water presentation missing from scene actions"): return
	if not check(console.camera_command({"action": "scene", "target": "fountain", "paused": true}), "Cannot pause existing water presentation"): return
	if not check(console.catalog()["scene_actions"].filter(func(item: Dictionary) -> bool: return item.id == "fountain")[0]["paused"], "Water pause not acknowledged"): return
	if not check(not console.catalog()["presentation_paused"], "Water pause froze the entire view"): return
	if not check(not console.camera_command({"action": "scene", "target": "missing", "paused": true}), "Unknown scene object accepted"): return
	console.camera_command({"action": "scene", "target": "fountain", "paused": false})
	if not check(console.camera_command({"action": "pause", "paused": true}), "Cannot pause local presentation"): return
	if not check(not paused, "Observation pause stopped the authority simulation"): return
	if not check(console.catalog()["presentation_paused"], "Pause state not acknowledged"): return
	console.camera_command({"action": "pause", "paused": false})
	if not check(console.camera_command({"action": "reset"}), "Cannot restore view"): return
	nest.queue_free()
	characters.queue_free()
	console.queue_free()
	await process_frame
	print("PASS: Nest Lab uses production cameras and light preview without pausing authority")
	quit(0)


func check(condition: bool, message: String) -> bool:
	if not condition:
		push_error(message)
		quit(1)
	return condition
