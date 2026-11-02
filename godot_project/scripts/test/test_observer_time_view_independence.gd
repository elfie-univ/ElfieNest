extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var nest := load("res://rooms/nest.tscn").instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	await process_frame
	nest.add_lighting_observer_views()
	nest.apply_observer_environment({"phase":"day", "lights_on":false, "quiet_mode":false})
	nest.select_observer_camera_by_id("central-1")
	var camera := root.get_camera_3d()
	var pose := camera.global_transform
	if not require(nest.select_observer_camera_by_id("lighting-night"), "Evening preview must be registered"):
		return
	if not require(root.get_camera_3d() == camera and camera.global_transform.is_equal_approx(pose) and nest.observer_camera_catalog().active_id == "central-1", "Changing time moved or reset the selected camera"):
		return
	if not require(nest._observer_water.night_enabled, "Evening preview did not reach actual fountain materials"):
		return
	nest.select_observer_camera_by_id("dorm-01")
	if not require(nest._observer_lighting_preview == "night" and nest._observer_water.night_enabled, "Changing the viewpoint reset the time preview"):
		return
	nest.apply_observer_environment({"phase":"day", "lights_on":false, "quiet_mode":false})
	if not require(nest._observer_water.night_enabled, "Live snapshots must not override an explicit local preview"):
		return
	nest.set_observer_presentation_paused(true)
	if not require(not nest.select_observer_camera_by_id("lighting-day"), "Paused observation accepted a time change"):
		return
	nest.set_observer_presentation_paused(false)
	nest.select_observer_camera_by_id("lighting-live")
	if not require(not nest._observer_water.night_enabled and nest.observer_camera_catalog().active_id == "dorm-01", "Restoring local time must use Nest's latest semantic environment and keep the camera"):
		return
	nest.free()
	print("PASS independent real monitor time/view controls, semantic time restoration and pause")
	quit(0)
