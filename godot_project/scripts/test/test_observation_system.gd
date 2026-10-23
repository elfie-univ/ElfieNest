extends SceneTree

const NEST_SCENE := preload("res://rooms/nest.tscn")
const EXPECTED_VIEW_IDS := [
	"overview", "courtyard", "garden", "sky",
	"central-1", "central-2", "central-3",
	"dorm-01", "dorm-02", "dorm-03", "dorm-04",
	"dorm-05", "dorm-06", "dorm-07", "dorm-08",
]


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	root.size = Vector2i(1280, 720)
	var nest := NEST_SCENE.instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	await process_frame
	var catalog := nest.observer_camera_catalog()
	var views := catalog["views"] as Array
	if not _require(views.size() == EXPECTED_VIEW_IDS.size(), "Complete estate camera count is incomplete"):
		return
	var selector := nest.get_node("ObservationHUD/Margin/Panel/Controls/CameraSelector") as OptionButton
	if not _require(selector.item_count == views.size(), "HUD does not list every complete estate view"):
		return
	var overview := nest.get_node("Camera3D") as Camera3D
	if not _require(
		root.get_camera_3d() == overview
			and overview.projection == Camera3D.PROJECTION_ORTHOGONAL
			and (-overview.global_transform.basis.z).y < -0.99,
		"Complete estate does not start in its top-down overview",
	):
		return
	var estate := nest.get_node("Generated/CompleteEstate")
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if not mesh.is_visible_in_tree():
			continue
		var bounds := mesh.get_aabb()
		for index in range(8):
			if not _require(
				overview.is_position_in_frustum(mesh.global_transform * bounds.get_endpoint(index)),
				"Overview clips complete estate mesh %s" % mesh.name,
			):
				return
	for index in range(views.size()):
		if not _require(String(views[index]["id"]) == EXPECTED_VIEW_IDS[index], "Complete camera ordering changed"):
			return
		if not _require(nest.select_observer_camera_by_id(EXPECTED_VIEW_IDS[index]), "Missing complete estate view"):
			return
		var camera := root.get_camera_3d()
		if not _require(
			nest.observation_active_view_index() == index
				and camera != null
				and (index == 0 or camera.projection == Camera3D.PROJECTION_PERSPECTIVE),
			"Camera selection did not activate the registered view",
		):
			return
		var saved_transform := camera.global_transform
		var saved_size := camera.size
		var saved_fov := camera.fov
		var zoom := InputEventMouseButton.new()
		zoom.button_index = MOUSE_BUTTON_WHEEL_UP
		zoom.pressed = true
		Input.parse_input_event(zoom)
		await process_frame
		if not _require(
			camera.size < saved_size if index == 0 else camera.fov < saved_fov,
			"Complete estate camera did not zoom",
		):
			return
		nest.reset_observer_camera()
		if not _require(
			camera.global_transform.is_equal_approx(saved_transform)
				and is_equal_approx(camera.size, saved_size)
				and is_equal_approx(camera.fov, saved_fov),
			"Reset did not restore complete estate camera preset",
		):
			return
	var environment := (nest.get_node("WorldEnvironment") as WorldEnvironment).environment
	var ceiling_fill := nest.get_node("CeilingFill") as DirectionalLight3D
	if not _require(environment != null and not ceiling_fill.shadow_enabled, "Observer environment was lost"):
		return
	nest.set_observation_hud_visible(false)
	if not _require(not (nest.get_node("ObservationHUD") as CanvasLayer).visible, "HUD visibility interface failed"):
		return
	nest.set_observation_hud_visible(true)
	if not _require((nest.get_node("ObservationHUD") as CanvasLayer).visible, "HUD could not be restored"):
		return
	print("PASS: complete estate camera coverage, selection, zoom, reset, environment and HUD")
	quit(0)


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	push_error(message)
	quit(1)
	return false
