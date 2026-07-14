extends SceneTree

const DEMO_SCENE := preload("res://modular_rooms/modular_nest_demo.tscn")
const MAX_BUILDING_LENGTH: float = 112.0
const ACTIVITY_OUTER_X: float = -5.2
const DORM_OUTER_X: float = 6.0
const WALL_HEIGHT: float = 3.0


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var nest := DEMO_SCENE.instantiate()
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
	var end_on_view := InputEventMouseMotion.new()
	end_on_view.relative = Vector2(
		atan2(12.5, 16.0) / 0.008,
		10000.0
	)
	end_on_view.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(end_on_view)
	await process_frame
	for x_position in [ACTIVITY_OUTER_X, DORM_OUTER_X]:
		for y_position in [0.0, WALL_HEIGHT]:
			for z_position in [0.0, -MAX_BUILDING_LENGTH]:
				var corner := Vector3(x_position, y_position, z_position)
				var camera_space_corner := camera.to_local(nest.to_global(corner))
				if not _require(
					camera_space_corner.z < -camera.near,
					"80-bed layout passed behind the camera during an end-on orbit"
				):
					return

	print("PASS: modular orbit camera controls and maximum layout framing")
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
