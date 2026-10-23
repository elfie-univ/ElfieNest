extends SceneTree

const DEMO_SCENE := preload("res://rooms/nest.tscn")


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var nest := DEMO_SCENE.instantiate() as ModularNest
	nest.show_observation_hud = false
	root.add_child(nest)
	await _wait_frames(3)
	var camera := nest.get_node("Camera3D") as Camera3D
	var default_transform := camera.global_transform
	var default_size := camera.size

	var orbit := InputEventMouseMotion.new()
	orbit.relative = Vector2(120.0, -45.0)
	orbit.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(orbit)
	await process_frame
	if not _require(
		not camera.global_transform.is_equal_approx(default_transform),
		"Left-drag did not orbit the runtime camera"
	):
		return

	var zoom := InputEventMouseButton.new()
	zoom.button_index = MOUSE_BUTTON_WHEEL_UP
	zoom.pressed = true
	Input.parse_input_event(zoom)
	await process_frame
	if not _require(camera.size < default_size, "Wheel-up did not zoom in"):
		return

	var before_pan := camera.global_transform
	var pan := InputEventMouseMotion.new()
	pan.relative = Vector2(80.0, 35.0)
	pan.button_mask = MOUSE_BUTTON_MASK_RIGHT
	Input.parse_input_event(pan)
	await process_frame
	if not _require(
		not camera.global_transform.is_equal_approx(before_pan),
		"Right-drag did not pan the runtime camera"
	):
		return

	var reset := InputEventKey.new()
	reset.keycode = KEY_R
	reset.pressed = true
	Input.parse_input_event(reset)
	await process_frame
	if not _require(
		camera.global_transform.is_equal_approx(default_transform),
		"R did not restore the default camera transform"
	):
		return
	if not _require(is_equal_approx(camera.size, default_size), "R did not restore the default zoom"):
		return

	nest.set("bed_count", 80)
	await _wait_frames(3)
	if not _require(nest.bed_count == 32, "Godot nest must keep its fixed capacity at 32 beds"):
		return
	var end_on_view := InputEventMouseMotion.new()
	end_on_view.relative = Vector2(
		atan2(12.5, 16.0) / 0.008,
		10000.0
	)
	end_on_view.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(end_on_view)
	await process_frame
	var estate := nest.get_node("Generated/CompleteEstate")
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if not mesh.is_visible_in_tree():
			continue
		for index in range(8):
			var corner := mesh.global_transform * mesh.get_aabb().get_endpoint(index)
			if not _require(
				camera.to_local(corner).z < -camera.near,
				"Complete estate passed behind the camera during an end-on orbit",
			):
				return

	print("PASS: complete estate orbit camera controls and asset framing")
	quit(0)


func _wait_frames(count: int) -> void:
	for frame in range(count):
		await process_frame


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	push_error(message)
	quit(1)
	return false
