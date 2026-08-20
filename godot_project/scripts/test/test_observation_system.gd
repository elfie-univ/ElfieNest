extends SceneTree

const NEST_SCENE := preload("res://rooms/nest.tscn")
const ROOM_COUNT: int = 8
const SECTION_COUNT: int = 2
const FIRST_ROOM_VIEW_INDEX: int = 1 + SECTION_COUNT
const EXPECTED_VIEW_COUNT: int = 1 + SECTION_COUNT + ROOM_COUNT * 2 + 1


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	root.size = Vector2i(1280, 720)
	var instance := NEST_SCENE.instantiate()
	var nest := instance as ModularNest
	if not _require(nest != null, "Nest scene did not instantiate as ModularNest"):
		instance.free()
		return
	root.add_child(nest)
	await _wait_frames(4)

	if not _require(
		nest.observation_view_count() == EXPECTED_VIEW_COUNT,
		"Expected %d observation views, got %d" % [
			EXPECTED_VIEW_COUNT,
			nest.observation_view_count(),
		]
	):
		return

	var labels := nest.observation_view_labels()
	if not _require(
		labels[0] == "整体总览"
			and labels[1] == "区域俯视 01-04"
			and labels[SECTION_COUNT] == "区域俯视 05-08"
			and labels[FIRST_ROOM_VIEW_INDEX].contains("厨房")
			and labels[FIRST_ROOM_VIEW_INDEX + 1].contains("宿舍")
			and labels[labels.size() - 1] == "传送室",
		"Observation labels do not cover overview, sections, rooms, and portal views"
	):
		return

	var generated := nest.get_node("Generated") as Node3D
	var overview := nest.get_node("Camera3D") as Camera3D
	var overview_forward := (-overview.global_transform.basis.z).normalized()
	if not _require(
		overview.projection == Camera3D.PROJECTION_ORTHOGONAL
			and overview_forward.y < -0.99
			and absf(overview.global_transform.basis.x.normalized().z) > 0.99
			and overview.global_transform.basis.y.normalized().x < -0.99
			and overview.size < 35.0,
		"Default overview is not close and top-down: forward=%s right=%s size=%.2f" % [
			overview_forward,
			overview.global_transform.basis.x.normalized(),
			overview.size,
		]
	):
		return
	for x_position in [-5.2, 5.4]:
		for z_position in [3.0, -44.8]:
			if not _require(
				overview.is_position_in_frustum(
					nest.to_global(Vector3(x_position, 0.0, z_position))
				),
				"Overall top-down view does not cover the full maximum layout"
			):
				return

	var section_cameras := generated.get_node("SectionObservationCameras") as Node3D
	if not _require(
		section_cameras.get_child_count() == SECTION_COUNT,
		"Eight room rows should generate two four-row overview cameras"
	):
		return
	for child in section_cameras.get_children():
		var section_camera := child as Camera3D
		if not _require(
			section_camera.projection == Camera3D.PROJECTION_ORTHOGONAL
				and (-section_camera.global_transform.basis.z).normalized().y < -0.99,
			"Section overview camera is not directed straight down"
		):
			return

	var corridor_lights := generated.get_node("CorridorLights") as Node3D
	if not _require(
		corridor_lights.get_child_count() == ROOM_COUNT,
		"Corridor lighting does not cover every room bay"
	):
		return
	var first_corridor_light := corridor_lights.get_child(0) as OmniLight3D
	if not _require(
		first_corridor_light.light_energy >= 0.25
			and not first_corridor_light.shadow_enabled,
		"Corridor observation lighting is too dim or still casts extra shadows"
	):
		return

	for index in range(ROOM_COUNT):
		var room_number := index + 1
		var activity_room := generated.get_node(
			"ActivityRoom_%02d" % room_number
		) as ModularActivityRoom
		var activity_path := "ActivityRoom_%02d/Generated" % room_number
		var activity := generated.get_node(activity_path) as Node3D
		var activity_light := activity.get_node("ActivityInteriorLight") as OmniLight3D
		var activity_anchor := activity.get_node("CameraAnchor") as Marker3D
		var activity_camera := activity_anchor.get_node(
			"ActivityObservationCamera"
		) as Camera3D
		var activity_forward := (-activity_camera.global_transform.basis.z).normalized()
		var activity_target := activity_room.observation_target_local()
		var activity_position_matches := false
		var activity_direction_matches := false
		if room_number == 1:
			activity_position_matches = (
				activity_anchor.position.distance_to(Vector3(1.30, 1.45, 0.70)) < 0.01
					and activity_target.distance_to(Vector3(0.25, 0.85, -1.10)) < 0.01
			)
			activity_direction_matches = activity_forward.x < -0.4 and activity_forward.z < -0.7
		else:
			activity_position_matches = (
				activity_anchor.position.x < -1.5
					and activity_anchor.position.y > 1.0
					and activity_anchor.position.y < 1.8
					and absf(activity_anchor.position.z) < 0.01
					and absf(activity_target.z) < 0.01
			)
			activity_direction_matches = activity_forward.x > 0.45
		if not _require(
			activity_light.light_energy >= 0.7
				and activity_camera.projection == Camera3D.PROJECTION_PERSPECTIVE
				and activity_camera.fov >= 90.0
				and activity_position_matches
				and activity_direction_matches
				and activity_forward.y < -0.1,
			"Activity room %d does not use the fixed kitchen or centered activity camera"
				% room_number
		):
			return

		var dorm_path := "DormRoom_%02d/Generated" % room_number
		var dorm := generated.get_node(dorm_path) as Node3D
		var dorm_light := dorm.get_node("DormInteriorLight") as OmniLight3D
		var dorm_anchor := dorm.get_node("CameraAnchor") as Marker3D
		var dorm_camera := dorm_anchor.get_node("DormObservationCamera") as Camera3D
		if not _require(
			dorm_light.light_energy >= 0.6
				and dorm_camera.projection == Camera3D.PROJECTION_PERSPECTIVE
				and dorm_camera.fov >= 90.0
				and dorm_anchor.position.x > 1.5
				and dorm_anchor.position.y > 1.0
				and dorm_anchor.position.y < 1.8
				and absf(dorm_anchor.position.z) < 0.01
				and (-dorm_camera.global_transform.basis.z).normalized().x < -0.45
				and (-dorm_camera.global_transform.basis.z).normalized().y < -0.1,
			"Dorm room %d lacks its outer-wall eye-level observation camera" % room_number
		):
			return

	var portal := generated.get_node("PortalRoom/Generated") as Node3D
	var portal_light := portal.get_node("PortalInteriorLight") as OmniLight3D
	var portal_anchor := portal.get_node("CameraAnchor") as Marker3D
	var portal_camera := portal_anchor.get_node("PortalObservationCamera") as Camera3D
	if not _require(
		portal_light.light_energy >= 0.6
			and portal_camera.projection == Camera3D.PROJECTION_PERSPECTIVE
			and portal_camera.fov >= 88.0
			and portal_anchor.position.z < 0.3
			and portal_anchor.position.y < 2.8
			and (-portal_camera.global_transform.basis.z).normalized().z > 0.45
			and (-portal_camera.global_transform.basis.z).normalized().y < -0.35,
		"Portal room lacks its neutral observation light or camera"
	):
		return

	var environment := (nest.get_node("WorldEnvironment") as WorldEnvironment).environment
	var ceiling_fill := nest.get_node("CeilingFill") as DirectionalLight3D
	if not _require(
		environment.ambient_light_energy >= 0.2
			and not nest.has_node("Sun")
			and not nest.has_node("FillLight")
			and not ceiling_fill.shadow_enabled
			and ceiling_fill.position.y > 10.0
			and (-ceiling_fill.global_transform.basis.z).normalized().y < -0.99,
		"Global lighting is not a shadowless top-down ceiling fill"
	):
		return

	var selector := nest.get_node(
		"ObservationHUD/Margin/Panel/Controls/CameraSelector"
	) as OptionButton
	if not _require(
		selector.item_count == EXPECTED_VIEW_COUNT,
		"Observation menu does not list every registered view"
	):
		return

	if not _require(root.get_camera_3d() == overview, "Overview camera is not active by default"):
		return
	nest.select_observation_view(1)
	await process_frame
	if not _require(
		nest.observation_active_view_index() == 1,
		"Observation system did not report the selected camera index"
	):
		return
	var selected_section_camera := root.get_camera_3d()
	var default_section_size := selected_section_camera.size
	var section_zoom := InputEventMouseButton.new()
	section_zoom.button_index = MOUSE_BUTTON_WHEEL_UP
	section_zoom.pressed = true
	Input.parse_input_event(section_zoom)
	await process_frame
	if not _require(
		selected_section_camera.size < default_section_size,
		"Section overview did not support orthographic zoom"
	):
		return
	var section_position_before_pan := selected_section_camera.global_position
	var section_pan := InputEventMouseMotion.new()
	section_pan.relative = Vector2(120.0, 0.0)
	section_pan.button_mask = MOUSE_BUTTON_MASK_RIGHT
	Input.parse_input_event(section_pan)
	await process_frame
	if not _require(
		absf(selected_section_camera.global_position.z - section_position_before_pan.z) > 0.01,
		"Section overview did not pan along the building length"
	):
		return

	nest.select_observation_view(FIRST_ROOM_VIEW_INDEX)
	await process_frame
	var selected_room_camera := root.get_camera_3d()
	if not _require(
		selected_room_camera != overview
			and selected_room_camera.name == "ActivityObservationCamera",
		"Selecting an activity room did not activate its camera"
	):
		return
	var default_fov := selected_room_camera.fov
	var zoom := InputEventMouseButton.new()
	zoom.button_index = MOUSE_BUTTON_WHEEL_UP
	zoom.pressed = true
	Input.parse_input_event(zoom)
	await process_frame
	if not _require(
		selected_room_camera.fov < default_fov,
		"Perspective room camera did not zoom by narrowing its field of view"
	):
		return
	nest.select_observation_view(EXPECTED_VIEW_COUNT - 1)
	await process_frame
	if not _require(
		root.get_camera_3d().name == "PortalObservationCamera",
		"Selecting the portal room did not activate its camera"
	):
		return

	nest.bed_count = 16
	await _wait_frames(4)
	var compact_sections := nest.get_node(
		"Generated/SectionObservationCameras"
	) as Node3D
	if not _require(
		compact_sections.get_child_count() == 0
			and nest.observation_view_count() == 1 + 4 * 2 + 1,
		"Layouts with four or fewer room rows should only expose the overall overview"
	):
		return

	nest.bed_count = 5
	await _wait_frames(4)
	if not _require(
		nest.observation_view_count() == 1 + 2 * 2 + 1
			and nest.observation_view_labels()[1].contains("厨房")
			and nest.observation_view_labels()[2].contains("宿舍"),
		"Changing the saved bed count should rebuild the room and camera layout"
	):
		return

	print("PASS: top-down overview, four-row sections, and room cameras are switchable")
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
