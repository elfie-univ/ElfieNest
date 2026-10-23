@tool
class_name ModularNest
extends Node3D

signal observer_camera_catalog_changed(catalog: Dictionary)

const COMPLETE_SCENE_PATH := "res://rooms/estate/estate.tscn"
const ESTATE_PHYSICS := preload("res://rooms/estate/estate_physics.gd")
const ESTATE_SEMANTICS := preload("res://rooms/estate/estate_semantics.gd")
const M01_SAMPLE := preload("res://runtime/lab/m01_optical_sample.gd")
const FIXED_BED_COUNT: int = 32
const CAMERA_ORBIT_SPEED: float = 0.008
const CAMERA_MIN_PITCH: float = deg_to_rad(12.0)
const CAMERA_MAX_PITCH: float = deg_to_rad(82.0)
const CAMERA_MIN_SIZE: float = 5.0
const CAMERA_MAX_SIZE: float = 500.0
const TOP_DOWN_MIN_HEIGHT: float = 18.0
const ENVIRONMENT_OBJECT_ID := "nest/environment"
# Design workbench central V050, front view after two .8 zoom steps, FOV 42.
# Derived from its actual shell bounds, not the enclosing sky geometry.
const REFERENCE_REVIEW_POSITION := Vector3(0, 15.884533, 26.802879)
const REFERENCE_REVIEW_TARGET := Vector3(0, 6.706, 0.578501)

var bed_count: int = FIXED_BED_COUNT:
	set(_value):
		bed_count = FIXED_BED_COUNT

@export var show_observation_hud: bool = true

@export var regenerate_editor_preview: bool = false:
	set(value):
		regenerate_editor_preview = false
		if value and Engine.is_editor_hint() and is_inside_tree():
			call_deferred("rebuild")

var _rebuilding := false
var _camera_target := Vector3.ZERO
var _camera_default_target := Vector3.ZERO
var _camera_yaw: float = 0.0
var _camera_pitch: float = 0.0
var _camera_distance: float = TOP_DOWN_MIN_HEIGHT
var _camera_default_distance: float = TOP_DOWN_MIN_HEIGHT
var _camera_default_size: float = 22.0
var _camera_views: Array[Dictionary] = []
var _active_camera_index: int = 0
var _active_camera_id := "overview"
var _observer_presentation_paused := false
var camera_catalog_revision: int = 0
var world_revision: int = 0
var _nest_id := "local-nest"
var _lights_on := true
var _anchor_markers: Dictionary = {}
var _facility_markers: Dictionary = {}
var _estate_physics: Node3D
var _estate_semantics: RefCounted
var _navigation_region: NavigationRegion3D

@onready var _observation_hud: CanvasLayer = $ObservationHUD


func _ready() -> void:
	if not Engine.is_editor_hint() and M01_SAMPLE.is_requested():
		_observation_hud.visible = false
		return
	if Engine.is_editor_hint():
		_observation_hud.visible = false
		rebuild()
	else:
		_observation_hud.visible = show_observation_hud
		_observation_hud.connect("view_selected", select_observation_view)
		call_deferred("rebuild")


func configure_m01_optical_sample(camera: Camera3D, target: Vector3) -> void:
	# Reuse the existing orbit/pan/reset implementation without building a world.
	_camera_views.clear()
	_register_observation_view("m01-sample", "M01 optical sample", camera, target)
	select_observation_view(0)


func _unhandled_input(event: InputEvent) -> void:
	if Engine.is_editor_hint():
		return
	if _observer_presentation_paused:
		return
	var camera := _active_camera()
	if camera == null:
		return
	if event is InputEventMouseMotion:
		var mouse_motion := event as InputEventMouseMotion
		if mouse_motion.button_mask & MOUSE_BUTTON_MASK_LEFT:
			_camera_yaw = wrapf(
				_camera_yaw - mouse_motion.relative.x * CAMERA_ORBIT_SPEED,
				-PI,
				PI
			)
			_camera_pitch = clampf(
				_camera_pitch - mouse_motion.relative.y * CAMERA_ORBIT_SPEED,
				CAMERA_MIN_PITCH,
				CAMERA_MAX_PITCH
			)
			_apply_camera_transform(camera)
			get_viewport().set_input_as_handled()
		elif mouse_motion.button_mask & MOUSE_BUTTON_MASK_RIGHT:
			var viewport_height := maxf(get_viewport().get_visible_rect().size.y, 1.0)
			var visible_height := camera.size
			if camera.projection == Camera3D.PROJECTION_PERSPECTIVE:
				visible_height = (
					2.0
					* _camera_distance
					* tan(deg_to_rad(camera.fov / 2.0))
				)
			var pan_scale := visible_height / viewport_height
			var camera_basis := camera.global_transform.basis
			_camera_target += (
				-camera_basis.x * mouse_motion.relative.x
				+ camera_basis.y * mouse_motion.relative.y
			) * pan_scale
			_apply_camera_transform(camera)
			get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton:
		var mouse_button := event as InputEventMouseButton
		if not mouse_button.pressed:
			return
		if mouse_button.button_index == MOUSE_BUTTON_WHEEL_UP:
			if camera.projection == Camera3D.PROJECTION_PERSPECTIVE:
				camera.fov = clampf(camera.fov * 0.9, 30.0, 100.0)
			else:
				camera.size = clampf(camera.size * 0.9, CAMERA_MIN_SIZE, CAMERA_MAX_SIZE)
			get_viewport().set_input_as_handled()
		elif mouse_button.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			if camera.projection == Camera3D.PROJECTION_PERSPECTIVE:
				camera.fov = clampf(camera.fov / 0.9, 30.0, 100.0)
			else:
				camera.size = clampf(camera.size / 0.9, CAMERA_MIN_SIZE, CAMERA_MAX_SIZE)
			get_viewport().set_input_as_handled()
	elif event is InputEventKey:
		var key_event := event as InputEventKey
		if key_event.pressed and not key_event.echo:
			if key_event.keycode in [KEY_R, KEY_HOME]:
				_reset_camera()
				get_viewport().set_input_as_handled()
			elif key_event.keycode == KEY_0:
				select_observation_view(0)
				get_viewport().set_input_as_handled()
			elif key_event.keycode == KEY_PAGEUP:
				_cycle_observation_view(-1)
				get_viewport().set_input_as_handled()
			elif key_event.keycode == KEY_PAGEDOWN:
				_cycle_observation_view(1)
				get_viewport().set_input_as_handled()


func rebuild() -> void:
	if _rebuilding:
		return
	_rebuilding = true
	if is_instance_valid(_navigation_region):
		remove_child(_navigation_region)
		_navigation_region.free()
	_navigation_region = null
	var previous := get_node_or_null("Generated")
	if previous != null:
		remove_child(previous)
		previous.free()
	_anchor_markers.clear()
	_facility_markers.clear()
	_camera_views.clear()
	var generated := Node3D.new()
	generated.name = "Generated"
	add_child(generated)
	var estate := (load(COMPLETE_SCENE_PATH) as PackedScene).instantiate() as Node3D
	estate.name = "CompleteEstate"
	generated.add_child(estate)
	_estate_physics = ESTATE_PHYSICS.new()
	_estate_physics.name = "EstatePhysics"
	generated.add_child(_estate_physics)
	if not Engine.is_editor_hint():
		_estate_physics.build(estate)
	_estate_semantics = ESTATE_SEMANTICS.new()
	_estate_semantics.build(generated, estate)
	_anchor_markers = _estate_semantics.anchors
	_facility_markers = _estate_semantics.facilities
	_build_observation_views(generated, estate)
	_set_light_visibility(self, _lights_on)
	_rebuilding = false


func apply_world_config(config: Dictionary) -> Dictionary:
	var requested_nest_id := String(config.get("nest_id", ""))
	var raw_bed_count: Variant = config.get("bed_count")
	var raw_revision: Variant = config.get("world_revision")
	if requested_nest_id.is_empty():
		return _config_rejected("invalid_nest_id")
	var requested_bed_count := _parse_protocol_integer(raw_bed_count)
	if requested_bed_count != FIXED_BED_COUNT:
		return _config_rejected("invalid_bed_count")
	var requested_revision := _parse_protocol_integer(raw_revision)
	if requested_revision < 0:
		return _config_rejected("invalid_revision")
	if requested_revision < world_revision:
		return _config_rejected("stale_revision")
	if requested_revision == world_revision:
		if requested_nest_id == _nest_id and requested_bed_count == bed_count:
			return {"accepted": true, "manifest": scene_manifest()}
		return _config_rejected("revision_conflict")

	_nest_id = requested_nest_id
	world_revision = requested_revision
	bed_count = requested_bed_count
	return {"accepted": true, "manifest": scene_manifest()}


func apply_observer_world_config(config: Dictionary) -> bool:
	var requested_nest_id := String(config.get("nest_id", ""))
	var requested_bed_count := _parse_protocol_integer(config.get("bed_count"))
	if requested_nest_id.is_empty() or requested_nest_id != _nest_id:
		return false
	if requested_bed_count != FIXED_BED_COUNT:
		return false
	if requested_bed_count == bed_count:
		return true
	bed_count = requested_bed_count
	return true


func _parse_protocol_integer(value: Variant) -> int:
	if value is int:
		return int(value)
	if value is float:
		var float_value := float(value)
		if is_nan(float_value) or is_inf(float_value):
			return -1
		var integer_value := int(float_value)
		if float(integer_value) == float_value:
			return integer_value
	return -1


func resolve_anchor(anchor_id: String) -> Marker3D:
	return _anchor_markers.get(anchor_id) as Marker3D


func resolve_facility(facility_id: String) -> Marker3D:
	return _facility_markers.get(facility_id) as Marker3D


func semantic_anchor_ids() -> Array[String]:
	var ids: Array[String] = []
	for anchor_id: Variant in _anchor_markers.keys():
		ids.append(String(anchor_id))
	ids.sort()
	return ids


func apply_environment_state(
	object_id: String,
	lights_on: bool,
	quiet_mode: bool,
) -> Dictionary:
	if object_id != ENVIRONMENT_OBJECT_ID:
		return {
			"object_id": object_id,
			"lights_on": lights_on,
			"quiet_mode": quiet_mode,
			"applied": false,
			"reason": "unsupported_environment_object",
		}
	var generated := get_node_or_null("Generated")
	if generated == null:
		return {
			"object_id": object_id,
			"lights_on": lights_on,
			"quiet_mode": quiet_mode,
			"applied": false,
			"reason": "world_not_built",
		}
	_lights_on = lights_on
	_set_light_visibility(self, lights_on)
	return {
		"object_id": object_id,
		"lights_on": lights_on,
		"quiet_mode": quiet_mode,
		"applied": true,
	}


func _set_light_visibility(node: Node, lights_on: bool) -> void:
	for child: Node in node.get_children():
		if child is Light3D:
			(child as Light3D).visible = lights_on
		_set_light_visibility(child, lights_on)


func nearest_zone_id(world_position: Vector3) -> String:
	return _estate_semantics.nearest_zone(world_position) if _estate_semantics != null else ""


func _config_rejected(code: String) -> Dictionary:
	return {
		"accepted": false,
		"code": code,
		"world_revision": world_revision,
	}


func _build_observation_views(generated: Node3D, estate: Node3D) -> void:
	var previous_id := _active_camera_id
	var bounds := AABB()
	var has_bounds := false
	var room_floors: Dictionary = {}
	var central_floor_tops: Dictionary = {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras := mesh.get_meta("extras", {}) as Dictionary
		var module_name := str(extras.get("module", ""))
		if str(extras.get("source_name", "")).contains("continuous lower floor"):
			room_floors[module_name] = mesh.global_transform
		if module_name == "central" and str(extras.get("source_name", mesh.name)) in [
			"Central L1 fitted complete floor",
			"Central L2 complete slab with stair opening",
			"Central L3 complete slab with stair opening",
		]:
			var local_bounds := (global_transform.affine_inverse() * mesh.global_transform) * mesh.get_aabb()
			central_floor_tops[int(extras["floor"])] = local_bounds.end.y
		if not mesh.is_visible_in_tree():
			continue
		var mesh_bounds := mesh.global_transform * mesh.get_aabb()
		bounds = bounds.merge(mesh_bounds) if has_bounds else mesh_bounds
		has_bounds = true
	for mesh: MultiMeshInstance3D in estate.find_children("*", "MultiMeshInstance3D", true, false):
		var mesh_bounds := mesh.global_transform * mesh.get_aabb()
		bounds = bounds.merge(mesh_bounds) if has_bounds else mesh_bounds
		has_bounds = true
	var center := bounds.get_center()

	_camera_default_target = center
	_camera_default_size = maxf(bounds.size.z, bounds.size.x / _viewport_aspect()) + 22.0
	_camera_default_distance = maxf(75.0, bounds.size.length() + 22.0)
	var overview := get_node("Camera3D") as Camera3D
	overview.projection = Camera3D.PROJECTION_ORTHOGONAL
	overview.size = _camera_default_size
	overview.far = 1000.0
	overview.global_position = center + Vector3(0.0, _camera_default_distance, 0.0)
	overview.look_at(center, Vector3.FORWARD)
	_register_observation_view("overview", "完整精灵巢 · 俯视", overview, center)
	_add_complete_view(generated, "courtyard", "庭院与建筑", to_global(REFERENCE_REVIEW_POSITION), to_global(REFERENCE_REVIEW_TARGET), 42.0)
	_add_complete_view(generated, "garden", "庭院近景", to_global(Vector3(0, 1.7, 24)), to_global(Vector3(0, 1.6, 4)))
	_add_complete_view(generated, "sky", "庭院与天空", to_global(Vector3(0, 1.7, 24)), to_global(Vector3(0, 10, -5)))
	for floor_number in range(1, 4):
		var floor_y := float(central_floor_tops[floor_number])
		var camera_z := 3.2 if floor_number == 3 else 5.2
		_add_complete_view(generated, "central-%d" % floor_number, "主楼活动 · %d 层" % floor_number, to_global(Vector3(0, floor_y + 1.4, camera_z)), to_global(Vector3(0, floor_y + 0.8, 0)))
	for index in range(1, 9):
		var module_name := "M%02d" % index
		if not room_floors.has(module_name):
			continue
		var floor_frame: Transform3D = room_floors[module_name]
		# Look across the room from its far side, not past the near bed/chair pair.
		_add_complete_view(generated, "dorm-%02d" % index, "%02d 宿舍 · 真实四人房" % index, floor_frame * Vector3(0, 1.55, 2.2), floor_frame * Vector3(0, 1.0, -0.4))
	var labels := observation_view_labels()
	camera_catalog_revision += 1
	_active_camera_index = _observation_view_index_by_id(previous_id)
	if _active_camera_index < 0:
		_active_camera_index = _observation_view_index_by_id("overview")
	if _active_camera_index < 0:
		_active_camera_index = 0
	if not Engine.is_editor_hint() and _observation_hud != null:
		_observation_hud.call("set_views", labels, _active_camera_index)
	select_observation_view(_active_camera_index)
	_emit_observer_camera_catalog_changed()


func _add_complete_view(parent: Node3D, view_id: String, label: String, position: Vector3, target: Vector3, fov: float = 70.0) -> void:
	var camera := Camera3D.new()
	camera.name = view_id
	camera.fov = fov
	camera.near = 0.05
	camera.far = 1000.0
	parent.add_child(camera)
	camera.global_position = position
	camera.look_at(target)
	_register_observation_view(view_id, label, camera, target)


func _register_observation_view(
	view_id: String,
	label: String,
	camera: Camera3D,
	target: Vector3
) -> void:
	_camera_views.append({
		"id": view_id,
		"label": label,
		"camera": camera,
		"target": target,
		"transform": camera.global_transform,
		"size": camera.size,
		"fov": camera.fov,
	})


func observation_view_count() -> int:
	return _camera_views.size()


func observation_view_labels() -> PackedStringArray:
	var labels := PackedStringArray()
	for view in _camera_views:
		labels.append(String(view["label"]))
	return labels


func observer_camera_catalog() -> Dictionary:
	var views: Array[Dictionary] = []
	for view in _camera_views:
		views.append({
			"id": String(view["id"]),
			"label": String(view["label"]),
		})
	return {
		"revision": camera_catalog_revision,
		"views": views,
		"active_id": _active_camera_id,
		"presentation_paused": _observer_presentation_paused,
	}


func observation_active_view_index() -> int:
	return _active_camera_index


func observer_presentation_paused() -> bool:
	return _observer_presentation_paused


func set_observation_hud_visible(visible: bool) -> void:
	show_observation_hud = visible
	if _observation_hud != null:
		_observation_hud.visible = visible


func select_observation_view(index: int) -> void:
	if index < 0 or index >= _camera_views.size():
		return
	_active_camera_index = index
	var view := _camera_views[index]
	_active_camera_id = String(view["id"])
	var camera := view["camera"] as Camera3D
	camera.current = true
	_camera_target = view["target"] as Vector3
	camera.global_transform = view["transform"] as Transform3D
	camera.size = float(view["size"])
	camera.fov = float(view["fov"])
	_sync_orbit_state(camera)
	if not Engine.is_editor_hint() and _observation_hud != null:
		_observation_hud.call("set_selected_view", index)
	_emit_observer_camera_catalog_changed()


func select_observer_camera_by_id(view_id: String) -> bool:
	if _observer_presentation_paused:
		return false
	var index := _observation_view_index_by_id(view_id)
	if index < 0:
		return false
	select_observation_view(index)
	return true


func select_observer_overview() -> bool:
	return select_observer_camera_by_id("overview")


func select_observation_view_named(label_fragment: String) -> bool:
	"""Select the first generated observation camera matching a stable label."""
	for index in range(_camera_views.size()):
		var view := _camera_views[index]
		if String(view["label"]).contains(label_fragment):
			select_observation_view(index)
			return true
	return false


func reset_observation_camera() -> void:
	"""Restore the current preset after direct orbit, pan, or zoom input."""
	_reset_camera()
	_emit_observer_camera_catalog_changed()


func reset_observer_camera() -> void:
	if _observer_presentation_paused:
		return
	reset_observation_camera()


func set_observer_presentation_paused(paused: bool) -> void:
	if _observer_presentation_paused == paused:
		return
	_observer_presentation_paused = paused
	_emit_observer_camera_catalog_changed()


func _observation_view_index_by_id(view_id: String) -> int:
	for index in range(_camera_views.size()):
		var view := _camera_views[index]
		if String(view["id"]) == view_id:
			return index
	return -1


func _emit_observer_camera_catalog_changed() -> void:
	observer_camera_catalog_changed.emit(observer_camera_catalog())


func _cycle_observation_view(direction: int) -> void:
	if _camera_views.is_empty():
		return
	select_observation_view(posmod(_active_camera_index + direction, _camera_views.size()))


func _active_camera() -> Camera3D:
	if _camera_views.is_empty():
		return get_node_or_null("Camera3D") as Camera3D
	return _camera_views[_active_camera_index]["camera"] as Camera3D


func _sync_orbit_state(camera: Camera3D) -> void:
	var offset := camera.global_position - _camera_target
	_camera_distance = maxf(offset.length(), 0.001)
	_camera_yaw = atan2(offset.x, offset.z)
	_camera_pitch = asin(clampf(offset.y / _camera_distance, -1.0, 1.0))


func _viewport_aspect() -> float:
	var viewport_size := get_viewport().get_visible_rect().size
	if viewport_size.x < 1.0 or viewport_size.y < 1.0:
		return 16.0 / 9.0
	return maxf(viewport_size.x / maxf(viewport_size.y, 1.0), 0.1)


func _reset_camera() -> void:
	if _camera_views.is_empty():
		return
	var view := _camera_views[_active_camera_index]
	var camera := view["camera"] as Camera3D
	_camera_target = view["target"] as Vector3
	camera.global_transform = view["transform"] as Transform3D
	camera.size = float(view["size"])
	camera.fov = float(view["fov"])
	_sync_orbit_state(camera)


func _apply_camera_transform(camera: Camera3D) -> void:
	var horizontal_scale := cos(_camera_pitch) * _camera_distance
	var offset := Vector3(
		sin(_camera_yaw) * horizontal_scale,
		sin(_camera_pitch) * _camera_distance,
		cos(_camera_yaw) * horizontal_scale
	)
	camera.global_position = _camera_target + offset
	var target_position := _camera_target
	var view_direction := (target_position - camera.global_position).normalized()
	var camera_up := global_transform.basis.y.normalized()
	if absf(view_direction.dot(camera_up)) > 0.98:
		camera_up = -global_transform.basis.x.normalized()
	camera.look_at(target_position, camera_up)


func scene_manifest() -> Dictionary:
	return {
		"nest_id": _nest_id,
		"world_revision": world_revision,
		"bed_count": FIXED_BED_COUNT,
		"capabilities": ["semantic_anchors", "complete_actor_sync", "navigation"],
		"zones": _estate_semantics.zones if _estate_semantics != null else [],
		"anchors": _estate_semantics.manifest_anchors(FIXED_BED_COUNT) if _estate_semantics != null else [],
		"facilities": _estate_semantics.facility_descriptors if _estate_semantics != null else [],
	}


func bake_navigation() -> bool:
	if _estate_physics == null or _anchor_markers.size() < 32:
		return false
	if is_instance_valid(_navigation_region):
		return _navigation_region.navigation_mesh.get_polygon_count() > 0
	_navigation_region = _estate_physics.bake(self)
	return _navigation_region.navigation_mesh.get_polygon_count() > 0


func validate_navigation_anchors() -> bool:
	var map := get_world_3d().navigation_map
	_estate_semantics.align_approaches(map)
	var courtyard := resolve_anchor("courtyard/activity")
	if courtyard == null: return false
	for id in semantic_anchor_ids():
		var marker := resolve_anchor(id)
		if marker == null: continue
		var nearest := NavigationServer3D.map_get_closest_point(map, marker.global_position)
		if nearest.distance_to(marker.global_position) > 0.3:
			push_warning("Complete estate approach off navigation: %s at %s, nearest %s" % [id, marker.global_position, nearest])
			return false
		var path := NavigationServer3D.map_get_path(map, marker.global_position, courtyard.global_position, true)
		if path.is_empty() or path[-1].distance_to(courtyard.global_position) > 0.3:
			push_warning("Complete estate disconnected route: %s from %s, partial path %s" % [id, marker.global_position, path])
			return false
	return true


func wait_for_navigation_sync(timeout_seconds: float = 10.0) -> bool:
	# Local geometry readiness only. The authority and read-only presentation
	# use the same synchronization rule, without granting Observer world control.
	var navigation_map := get_world_3d().navigation_map
	var deadline := Time.get_ticks_msec() + int(timeout_seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		await get_tree().physics_frame
		var regions := NavigationServer3D.map_get_regions(navigation_map)
		var synchronized := not regions.is_empty()
		# Small landing patches may synchronize before the full baked region.
		for expected: NavigationRegion3D in find_children("*", "NavigationRegion3D", true, false):
			if not regions.has(expected.get_rid()): synchronized = false
		for region: RID in regions:
			if NavigationServer3D.region_get_iteration_id(region) == 0: synchronized = false
		if synchronized and NavigationServer3D.map_get_iteration_id(navigation_map) > 0:
			var anchor_ids := semantic_anchor_ids()
			if anchor_ids.is_empty(): continue
			var marker := resolve_anchor(anchor_ids[0])
			if marker == null or not NavigationServer3D.map_get_closest_point_owner(navigation_map, marker.global_position).is_valid(): continue
			if NavigationServer3D.map_get_closest_point(navigation_map, marker.global_position).distance_to(marker.global_position) > 0.35: continue
			return true
	return false
