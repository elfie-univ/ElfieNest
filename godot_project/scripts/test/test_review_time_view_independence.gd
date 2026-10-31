extends SceneTree

# Match the explicit Web review lifecycle: camera/HUD only, without loading
# a physical world or depending on unrelated baked navigation resources.
class ReviewNest extends ModularNest:
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
	var nest := load("res://rooms/nest.tscn").instantiate() as ModularNest
	nest.set_script(ReviewNest)
	root.add_child(nest)
	var views: Array[Dictionary] = []
	for place: String in ["lake", "seats"]:
		for phase: String in ["day", "night", "quiet"]:
			views.append({"id":"lighting-v4-" + place + "-" + phase, "focus":place, "camera":Vector3(20,24,28) if place == "lake" else Vector3(42,6,12), "target":Vector3(30,0,20), "fov":58.0})
	nest.configure_estate_path_lighting_review(views)
	nest.select_observer_camera_by_id("lighting-v4-lake-night")
	var hud := nest.get_node("ObservationHUD") as ObservationHUD
	# Exercise the actual selector signal after manual orbit, pan and zoom.
	nest._camera_target += Vector3(2.0, 0.8, -1.0)
	nest._camera_yaw += 0.6
	nest._camera_pitch += 0.12
	nest._camera_distance *= 0.65
	nest._apply_camera_transform(nest._active_camera())
	nest._active_camera().fov = 43.0
	var pose := nest._active_camera().global_transform
	var target := nest._camera_target
	var distance := nest._camera_distance
	var yaw := nest._camera_yaw
	var pitch := nest._camera_pitch
	for phase_index in [0, 2, 1]:
		hud._phase_selector.item_selected.emit(phase_index)
		if not require(nest._active_camera().global_transform.is_equal_approx(pose) and is_equal_approx(nest._active_camera().fov,43.0) and nest._camera_target == target and nest._camera_distance == distance and nest._camera_yaw == yaw and nest._camera_pitch == pitch, "Review time selector reset the manually adjusted camera or orbit state"):
			return
		if not require(nest._active_camera_id.ends_with(ObservationHUD.LIGHTING_PHASES[phase_index]), "Time selection did not reach the review phase state"):
			return
	hud._selector.item_selected.emit(1)
	if not require(nest._active_camera_id == "lighting-v4-seats-night" and not nest._active_camera().global_transform.is_equal_approx(pose), "Selecting another place must still move the camera and retain the time"):
		return
	nest.reset_observation_camera()
	if not require(is_equal_approx(nest._active_camera().fov, 58.0), "Explicit reset must still restore the preset"):
		return
	nest.free()
	print("PASS review time selector preserves manual pose, FOV, target and orbit; place selection and explicit reset retained")
	quit(0)
