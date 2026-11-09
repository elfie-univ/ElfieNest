extends SceneTree

class Preview extends "res://tools/static_asset_review.gd":
	func _ready() -> void:
		pass

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var view := Preview.new()
	view.current = Node3D.new()
	view.add_child(view.current)
	var marker := MeshInstance3D.new()
	marker.mesh = BoxMesh.new()
	marker.position = Vector3(1, 2, -3)
	view.current.add_child(marker)
	view.camera = Camera3D.new()
	view.add_child(view.camera)
	root.add_child(view)
	await process_frame
	for spec: Array in [[3.0, 46.0], [300.0, 46.0], [60.0, 101.0]]:
		var focus := marker.global_position
		view.set_camera(focus, focus + Vector3(1, 0.65, 1.2).normalized() * spec[0], spec[1])
		var initial_position := view.camera.global_position
		var initial_yaw := view.yaw
		var initial_pitch := view.pitch
		var initial_distance := view.distance
		var before := view.camera.unproject_position(focus)
		var motion := InputEventMouseMotion.new()
		motion.button_mask = MOUSE_BUTTON_MASK_RIGHT
		motion.relative = Vector2(120, 35)
		view._unhandled_input(motion)
		var pixels := view.camera.unproject_position(focus) - before
		if not require(pixels.distance_to(motion.relative) < 0.02, "Right drag must move the asset with the cursor at every zoom and FOV: " + str(pixels)):
			return
		if not require(is_equal_approx(view.yaw, initial_yaw) and is_equal_approx(view.pitch, initial_pitch) and is_equal_approx(view.distance, initial_distance), "Panning must preserve orbit angles and zoom"):
			return
		motion.relative = -motion.relative
		view._unhandled_input(motion)
		if not require(view.target.distance_to(focus) < 0.001 and view.camera.global_position.distance_to(initial_position) < 0.001, "Opposite drags must restore the original framing"):
			return
		view.auditing = true
		view._unhandled_input(motion)
		if not require(view.target.distance_to(focus) < 0.001, "Resource audit must ignore camera input"):
			return
		view.auditing = false
	var focus := view.target
	var yaw := view.yaw
	var orbit := InputEventMouseMotion.new()
	orbit.button_mask = MOUSE_BUTTON_MASK_LEFT
	orbit.relative = Vector2(20, -10)
	view._unhandled_input(orbit)
	if not require(not is_equal_approx(view.yaw, yaw) and view.target.is_equal_approx(focus), "Left drag must continue to orbit without panning"):
		return
	var distance := view.distance
	var wheel := InputEventMouseButton.new()
	wheel.pressed = true
	wheel.button_index = MOUSE_BUTTON_WHEEL_UP
	view._unhandled_input(wheel)
	if not require(view.distance < distance and view.target.is_equal_approx(focus), "The wheel must continue to zoom around the panned target"):
		return
	var pan := InputEventMouseMotion.new()
	pan.button_mask = MOUSE_BUTTON_MASK_RIGHT
	pan.relative = Vector2(-80, 20)
	view._unhandled_input(pan)
	view.reset()
	if not require(view.target.is_equal_approx(marker.global_position), "Reset must restore the asset center after panning"):
		return
	view.free()
	print("PASS asset preview: right-drag pan across scales/FOVs, reverse drag, audit guard, left orbit, wheel zoom and reset")
	quit(0)
