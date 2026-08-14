@tool
class_name ModularNest
extends Node3D

signal observer_camera_catalog_changed(catalog: Dictionary)

const D := preload("res://rooms/room_dimensions.gd")
const G := preload("res://rooms/room_geometry.gd")
const P := preload("res://rooms/assets/themes/room_palette.gd")
const SPATIAL_QUERIES := preload("res://runtime/world/spatial_queries.gd")
const SEMANTIC_SCENE_INDEX := preload("res://runtime/world/semantic_scene_index.gd")
const ACTIVITY_ROOM_SCENE := preload("res://rooms/activity_room.tscn")
const DORM_ROOM_SCENE := preload("res://rooms/dorm_room.tscn")
const PORTAL_ROOM_SCENE := preload("res://rooms/portal_room.tscn")
const MURAL_TEXTURE := preload("res://rooms/assets/artwork/gallery/img1.jpg")
const CAMERA_ORBIT_SPEED: float = 0.008
const CAMERA_MIN_PITCH: float = deg_to_rad(12.0)
const CAMERA_MAX_PITCH: float = deg_to_rad(82.0)
const CAMERA_MIN_SIZE: float = 5.0
const CAMERA_MAX_SIZE: float = 120.0
const CAMERA_BOUNDS_MARGIN: float = 2.0
const ROOM_CAMERA_FOV: float = 92.0
const PORTAL_CAMERA_FOV: float = 90.0
const CORRIDOR_LIGHT_ENERGY: float = 0.3
const SECTION_ROOM_SPAN: int = 4
const OVERVIEW_MARGIN: float = 1.2
const PORTAL_ROOM_LENGTH: float = 3.0
const TOP_DOWN_MIN_HEIGHT: float = 18.0
const NAVIGATION_SOURCE_GROUP := &"nest_runtime_navigation_source"
const ENVIRONMENT_OBJECT_ID := "nest/environment"
const ACTIVITY_VIEW_LABELS := [
	"厨房",
	"会客厅",
	"影音室",
	"健身房",
	"花园",
	"工作室",
	"音乐室",
	"图书室",
]

@export_range(4, 32, 1) var bed_count: int = 16:
	set(value):
		bed_count = clampi(value, D.MIN_BED_COUNT, D.MAX_BED_COUNT)
		if is_inside_tree() and not _suppress_deferred_rebuild:
			call_deferred("rebuild")

@export var activity_group_ids := PackedInt32Array([0, 0, 1, 2])
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
var _suppress_deferred_rebuild := false
var _anchor_markers: Dictionary = {}
var _navigation_region: NavigationRegion3D

@onready var _observation_hud: CanvasLayer = $ObservationHUD


func _ready() -> void:
	if Engine.is_editor_hint():
		_observation_hud.visible = false
		rebuild()
	else:
		_observation_hud.visible = show_observation_hud
		_observation_hud.connect("view_selected", select_observation_view)
		call_deferred("rebuild")


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
	var overview_camera := get_node_or_null("Camera3D") as Camera3D
	if overview_camera != null:
		overview_camera.current = true
	_camera_views.clear()
	var previous := get_node_or_null("Generated")
	if previous != null:
		remove_child(previous)
		previous.queue_free()
	var generated := Node3D.new()
	generated.name = "Generated"
	add_child(generated)

	var room_count := D.room_count_for_beds(bed_count)
	var themes := _themes_for_rooms(room_count)
	_build_floors(generated, room_count)
	_build_corridor_lights(generated, room_count)
	_build_rooms(generated, room_count, themes)
	_build_activity_boundaries(generated, room_count, themes)
	_build_dorm_boundaries(generated, room_count)
	_build_end_wall(generated, room_count)
	_build_portal_room(generated)
	_build_semantic_anchor_markers(generated, room_count)
	_update_camera(room_count)
	_build_observation_views(generated, room_count)
	_rebuilding = false


func apply_world_config(config: Dictionary) -> Dictionary:
	var requested_nest_id := String(config.get("nest_id", ""))
	var raw_bed_count: Variant = config.get("bed_count")
	var raw_revision: Variant = config.get("world_revision")
	if requested_nest_id.is_empty():
		return _config_rejected("invalid_nest_id")
	var requested_bed_count := _parse_protocol_integer(raw_bed_count)
	if requested_bed_count < D.MIN_BED_COUNT or requested_bed_count > D.MAX_BED_COUNT:
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
	_suppress_deferred_rebuild = true
	bed_count = requested_bed_count
	_suppress_deferred_rebuild = false
	rebuild()
	return {"accepted": true, "manifest": scene_manifest()}


func apply_observer_world_config(config: Dictionary) -> bool:
	var requested_nest_id := String(config.get("nest_id", ""))
	var requested_bed_count := _parse_protocol_integer(config.get("bed_count"))
	if requested_nest_id.is_empty() or requested_nest_id != _nest_id:
		return false
	if requested_bed_count < D.MIN_BED_COUNT or requested_bed_count > D.MAX_BED_COUNT:
		return false
	if requested_bed_count == bed_count:
		return true
	_suppress_deferred_rebuild = true
	bed_count = requested_bed_count
	_suppress_deferred_rebuild = false
	rebuild()
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


func semantic_anchor_ids() -> Array[String]:
	var ids: Array[String] = []
	for anchor_id: Variant in _anchor_markers.keys():
		ids.append(String(anchor_id))
	return SEMANTIC_SCENE_INDEX.sorted_anchor_ids(ids)


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
	_set_light_visibility(generated, lights_on)
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
	return SPATIAL_QUERIES.nearest_zone_id(_anchor_markers, world_position)


func bake_navigation() -> bool:
	if _navigation_region != null:
		remove_child(_navigation_region)
		_navigation_region.queue_free()
	if not is_in_group(NAVIGATION_SOURCE_GROUP):
		add_to_group(NAVIGATION_SOURCE_GROUP)
	_navigation_region = NavigationRegion3D.new()
	_navigation_region.name = "RuntimeNavigation"
	var navigation_mesh := NavigationMesh.new()
	navigation_mesh.agent_height = 1.8
	navigation_mesh.agent_radius = 0.2
	navigation_mesh.agent_max_climb = 0.2
	navigation_mesh.agent_max_slope = 45.0
	navigation_mesh.cell_size = 0.1
	navigation_mesh.cell_height = 0.1
	navigation_mesh.geometry_parsed_geometry_type = (
		NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
	)
	navigation_mesh.geometry_source_geometry_mode = (
		NavigationMesh.SOURCE_GEOMETRY_GROUPS_WITH_CHILDREN
	)
	navigation_mesh.geometry_source_group_name = NAVIGATION_SOURCE_GROUP
	var navigation_map := get_world_3d().navigation_map
	NavigationServer3D.map_set_cell_size(navigation_map, navigation_mesh.cell_size)
	NavigationServer3D.map_set_cell_height(navigation_map, navigation_mesh.cell_height)
	_navigation_region.navigation_mesh = navigation_mesh
	add_child(_navigation_region)
	_navigation_region.bake_navigation_mesh(false)
	return navigation_mesh.get_polygon_count() > 0


func _config_rejected(code: String) -> Dictionary:
	return {
		"accepted": false,
		"code": code,
		"world_revision": world_revision,
	}


func scene_manifest() -> Dictionary:
	var room_count := D.room_count_for_beds(bed_count)
	return {
		"nest_id": _nest_id,
		"world_revision": world_revision,
		"bed_count": bed_count,
		"capabilities": [
			"semantic_anchors",
			"complete_actor_sync",
			"navigation",
		],
		"zones": _semantic_zones(room_count),
		"anchors": _semantic_anchors(room_count),
		"facilities": _semantic_facilities(room_count),
	}


func _semantic_zones(room_count: int) -> Array[Dictionary]:
	var zones: Array[Dictionary] = [
		{"zone_id": "corridor", "kind": "corridor", "label": "走廊", "stable_order": 0, "active": true},
		{"zone_id": "portal", "kind": "portal", "label": "传送室", "stable_order": 1, "active": true},
	]
	for index in range(room_count):
		zones.append({
			"zone_id": _dorm_zone_id(index),
			"kind": "dorm",
			"label": "%02d 宿舍" % (index + 1),
			"stable_order": index * 2 + 2,
			"active": true,
		})
		zones.append({
			"zone_id": _activity_zone_id(index),
			"kind": "activity",
			"label": "%02d %s" % [
				index + 1,
				String(ACTIVITY_VIEW_LABELS[index % ACTIVITY_VIEW_LABELS.size()]),
			],
			"stable_order": index * 2 + 3,
			"active": true,
		})
	return zones


func _semantic_anchors(room_count: int) -> Array[Dictionary]:
	var anchors: Array[Dictionary] = []
	for index in range(room_count):
		var zone_id := _dorm_zone_id(index)
		var beds_in_room := clampi(bed_count - index * 4, 0, 4)
		anchors.append({
			"anchor_id": "%s/door" % zone_id,
			"zone_id": zone_id,
			"kind": "door",
			"label": "%02d 宿舍门" % (index + 1),
			"stable_order": index,
			"active": true,
		})
		for bed_index in range(beds_in_room):
			anchors.append({
				"anchor_id": "%s/bed-%02d" % [zone_id, bed_index + 1],
				"zone_id": zone_id,
				"kind": "bed",
				"label": "%02d-%02d 床位" % [index + 1, bed_index + 1],
				"stable_order": index * 4 + bed_index,
				"active": true,
			})
	for index in range(room_count):
		var activity_zone_id := _activity_zone_id(index)
		anchors.append({
			"anchor_id": "%s/activity" % activity_zone_id,
			"zone_id": activity_zone_id,
			"kind": "activity",
			"label": String(ACTIVITY_VIEW_LABELS[index % ACTIVITY_VIEW_LABELS.size()]),
			"stable_order": index,
			"active": true,
		})
		anchors.append({
			"anchor_id": "%s/chair-01" % activity_zone_id,
			"zone_id": activity_zone_id,
			"kind": "chair",
			"label": "%s 座位" % String(
				ACTIVITY_VIEW_LABELS[index % ACTIVITY_VIEW_LABELS.size()]
			),
			"stable_order": index,
			"active": true,
		})
	anchors.append({
		"anchor_id": "portal/door",
		"zone_id": "portal",
		"kind": "door",
		"label": "传送室门",
		"stable_order": 0,
		"active": true,
	})
	anchors.append({
		"anchor_id": "portal/main",
		"zone_id": "portal",
		"kind": "activity",
		"label": "传送台",
		"stable_order": 0,
		"active": true,
	})
	return anchors


func _semantic_facilities(room_count: int) -> Array[Dictionary]:
	var facilities: Array[Dictionary] = []
	for index in range(room_count):
		var dorm_zone_id := _dorm_zone_id(index)
		facilities.append({
			"facility_id": "%s/rest" % dorm_zone_id,
			"zone_id": dorm_zone_id,
			"kind": "rest",
			"label": "%02d 休息区" % (index + 1),
			"capabilities": ["sleep", "rest"],
			"active": true,
		})
		var activity_zone_id := _activity_zone_id(index)
		facilities.append({
			"facility_id": "%s/activity" % activity_zone_id,
			"zone_id": activity_zone_id,
			"kind": "activity",
			"label": String(ACTIVITY_VIEW_LABELS[index % ACTIVITY_VIEW_LABELS.size()]),
			"capabilities": ["social", "activity"],
			"active": true,
		})
	facilities.append({
		"facility_id": "portal/transit",
		"zone_id": "portal",
		"kind": "transit",
		"label": "传送室",
		"capabilities": ["transit"],
		"active": true,
	})
	return facilities


func _dorm_zone_id(index: int) -> String:
	return "dorm-%02d" % (index + 1)


func _activity_zone_id(index: int) -> String:
	return "activity-%02d" % (index + 1)


func _build_semantic_anchor_markers(
	generated: Node3D,
	room_count: int,
) -> void:
	_anchor_markers.clear()
	var anchor_root := Node3D.new()
	anchor_root.name = "SemanticAnchors"
	generated.add_child(anchor_root)
	for room_index in range(room_count):
		var dorm_zone_id := _dorm_zone_id(room_index)
		_add_semantic_marker(
			anchor_root,
			"%s/door" % dorm_zone_id,
			dorm_zone_id,
			"door",
			Vector3(
				D.DORM_CENTER_X - D.DORM_DEPTH / 2.0 + 0.55,
				0.0,
				D.cell_center_z(room_index),
			),
		)
		var beds_in_room := clampi(bed_count - room_index * 4, 0, 4)
		for bed_index in range(beds_in_room):
			var bed_position := Vector3(
				D.DORM_CENTER_X + (-0.45 if bed_index % 2 == 0 else 0.45),
				0.0,
				D.cell_center_z(room_index)
				+ (0.8 if bed_index < 2 else -0.8),
			)
			_add_semantic_marker(
				anchor_root,
				"%s/bed-%02d" % [dorm_zone_id, bed_index + 1],
				dorm_zone_id,
				"bed",
				bed_position,
			)
		var activity_zone_id := _activity_zone_id(room_index)
		var activity_position := Vector3(
			D.ACTIVITY_INNER_X + 0.5,
			0.0,
			D.cell_center_z(room_index) + 0.55,
		)
		_add_semantic_marker(
			anchor_root,
			"%s/activity" % activity_zone_id,
			activity_zone_id,
			"activity",
			activity_position,
		)
		_add_semantic_marker(
			anchor_root,
			"%s/chair-01" % activity_zone_id,
			activity_zone_id,
			"chair",
			activity_position + Vector3(-0.45, 0.0, 0.0),
		)
	_add_semantic_marker(
		anchor_root,
		"portal/door",
		"portal",
		"door",
		Vector3(0.0, 0.0, 0.45),
	)
	_add_semantic_marker(
		anchor_root,
		"portal/main",
		"portal",
		"activity",
		Vector3(0.0, 0.0, 1.5),
	)


func _add_semantic_marker(
	parent: Node3D,
	anchor_id: String,
	zone_id: String,
	kind: String,
	marker_position: Vector3,
) -> void:
	var marker := Marker3D.new()
	marker.name = "Anchor_%s" % anchor_id.replace("/", "__")
	marker.position = marker_position
	marker.set_meta("anchor_id", anchor_id)
	marker.set_meta("zone_id", zone_id)
	marker.set_meta("kind", kind)
	parent.add_child(marker)
	_anchor_markers[anchor_id] = marker


func _build_floors(parent: Node3D, room_count: int) -> void:
	var building_length := float(room_count) * D.CELL_PITCH
	var decor_top_y := 0.0005
	var joint_top_y := 0.0008
	G.add_floor(parent, "CorridorFloor", D.CORRIDOR_WIDTH, building_length, Vector3(0.0, 0.0, -building_length / 2.0), D.CORRIDOR_COLOR)
	G.add_box(
		parent,
		"CorridorCentralMarble",
		Vector3(1.88, 0.024, building_length - 0.16),
		Vector3(0.0, decor_top_y - 0.024 / 2.0, -building_length / 2.0),
		Color("#d7dddd"),
		false,
		0.0,
		0.28
	)
	for side in [-1.0, 1.0]:
		G.add_box(
			parent,
			"CorridorWarmMarbleInlayLeft" if side < 0.0 else "CorridorWarmMarbleInlayRight",
			Vector3(0.08, 0.026, building_length - 0.16),
			Vector3(side, decor_top_y - 0.026 / 2.0, -building_length / 2.0),
			Color("#827265"),
			false,
			0.0,
			0.3
		)
		G.add_box(
			parent,
			"CorridorDarkMarbleBandLeft" if side < 0.0 else "CorridorDarkMarbleBandRight",
			Vector3(0.28, 0.027, building_length - 0.16),
			Vector3(side * 1.18, decor_top_y - 0.027 / 2.0, -building_length / 2.0),
			Color("#454b4c"),
			false,
			0.0,
			0.25
		)
		G.add_box(
			parent,
			"CorridorOuterMarbleBorderLeft" if side < 0.0 else "CorridorOuterMarbleBorderRight",
			Vector3(0.16, 0.024, building_length - 0.16),
			Vector3(side * 1.42, decor_top_y - 0.024 / 2.0, -building_length / 2.0),
			D.CORRIDOR_WALL_COLOR,
			false,
			0.0,
			0.34
		)
	for index in range(room_count):
		_add_corridor_bay(parent, index, D.cell_center_z(index), decor_top_y, joint_top_y)


func _add_corridor_bay(parent: Node3D, index: int, center_z: float, decor_top_y: float, joint_top_y: float) -> void:
	for joint_index in range(2):
		var direction := -1.0 if joint_index == 0 else 1.0
		var z_position := center_z + direction * (D.CELL_PITCH / 2.0 - 0.08)
		G.add_box(
			parent,
			"CorridorCentralTileJoint_%02d_%d" % [index, joint_index],
			Vector3(1.88, 0.027, 0.028),
			Vector3(0.0, joint_top_y - 0.027 / 2.0, z_position),
			Color("#b6bfbe"),
			false,
			0.0,
			0.3
		)
	G.add_box(
		parent,
		"DormDoorwayInlay_%02d" % index,
		Vector3(0.08, 0.008, 1.18),
		Vector3(D.DORM_INNER_X + 0.05, decor_top_y - 0.008 / 2.0, center_z),
		Color("#d4c6b0"),
		false,
		0.0,
		0.34
	)


func _build_corridor_lights(parent: Node3D, room_count: int) -> void:
	var lights := Node3D.new()
	lights.name = "CorridorLights"
	parent.add_child(lights)
	for index in range(room_count):
		var light := OmniLight3D.new()
		light.name = "CorridorLight_%02d" % (index + 1)
		light.position = Vector3(0.0, 2.55, D.cell_center_z(index))
		light.light_color = Color.WHITE
		light.light_energy = CORRIDOR_LIGHT_ENERGY
		light.omni_range = 3.8
		light.shadow_enabled = false
		lights.add_child(light)


func _build_rooms(parent: Node3D, room_count: int, themes: Array[Color]) -> void:
	for index in range(room_count):
		var activity := ACTIVITY_ROOM_SCENE.instantiate() as ModularActivityRoom
		activity.auto_preview = false
		activity.name = "ActivityRoom_%02d" % (index + 1)
		activity.position = Vector3(D.ACTIVITY_CENTER_X, 0.0, D.cell_center_z(index))
		parent.add_child(activity)
		activity.build(themes[index], index)

		var dorm := DORM_ROOM_SCENE.instantiate() as ModularDormRoom
		dorm.auto_preview = false
		dorm.name = "DormRoom_%02d" % (index + 1)
		dorm.position = Vector3(D.DORM_CENTER_X, 0.0, D.cell_center_z(index))
		parent.add_child(dorm)
		dorm.build(index, clampi(bed_count - index * 4, 0, 4))


func _build_activity_boundaries(parent: Node3D, room_count: int, themes: Array[Color]) -> void:
	_add_activity_partition(parent, "ActivityStartWall", 0.0, themes[0], D.EXTERIOR_COLOR)
	for boundary_index in range(1, room_count):
		if _activity_group(boundary_index - 1) == _activity_group(boundary_index):
			continue
		_add_activity_partition(
			parent,
			"ActivityPartition_%02d" % boundary_index,
			-float(boundary_index) * D.CELL_PITCH,
			themes[boundary_index],
			themes[boundary_index - 1]
		)
	_add_activity_partition(
		parent,
		"ActivityEndWall",
		-float(room_count) * D.CELL_PITCH,
		D.EXTERIOR_COLOR,
		themes[room_count - 1]
	)


func _add_activity_partition(parent: Node3D, wall_name: String, z_position: float, negative_color: Color, positive_color: Color) -> void:
	G.add_wall(
		parent,
		wall_name,
		Vector3(D.ACTIVITY_DEPTH, D.WALL_HEIGHT, D.WALL_THICKNESS),
		Vector3(D.ACTIVITY_CENTER_X, D.WALL_HEIGHT / 2.0, z_position),
		negative_color,
		positive_color
	)


func _build_dorm_boundaries(parent: Node3D, room_count: int) -> void:
	for boundary_index in range(room_count + 1):
		var negative_color := D.DORM_WALL_COLOR if boundary_index < room_count else D.EXTERIOR_COLOR
		var positive_color := D.DORM_WALL_COLOR if boundary_index > 0 else D.EXTERIOR_COLOR
		G.add_wall(
			parent,
			"DormPartition_%02d" % boundary_index,
			Vector3(D.DORM_DEPTH, D.WALL_HEIGHT, D.WALL_THICKNESS),
			Vector3(D.DORM_CENTER_X, D.WALL_HEIGHT / 2.0, -float(boundary_index) * D.CELL_PITCH),
			negative_color,
			positive_color
		)


func _build_end_wall(parent: Node3D, room_count: int) -> void:
	var end_z := -float(room_count) * D.CELL_PITCH
	G.add_wall(
		parent,
		"CorridorEndWall",
		Vector3(D.CORRIDOR_WIDTH, D.WALL_HEIGHT, D.WALL_THICKNESS),
		Vector3(0.0, D.WALL_HEIGHT / 2.0, end_z),
		D.EXTERIOR_COLOR,
		D.CORRIDOR_WALL_COLOR
	)
	G.add_box(parent, "MuralFrame", Vector3(2.72, 1.92, 0.055), Vector3(0.0, 1.52, end_z + 0.09), Color("#172129"))
	var mural := MeshInstance3D.new()
	mural.name = "EndWallMural"
	var quad := QuadMesh.new()
	quad.size = Vector2(2.48, 1.68)
	mural.mesh = quad
	mural.position = Vector3(0.0, 1.52, end_z + 0.122)
	var mural_material := StandardMaterial3D.new()
	mural_material.albedo_texture = MURAL_TEXTURE
	mural_material.roughness = 0.62
	mural_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	mural.material_override = mural_material
	parent.add_child(mural)
	G.add_box(parent, "MuralLight", Vector3(1.8, 0.045, 0.045), Vector3(0.0, 2.62, end_z + 0.16), Color("#f2d29b"), false, 1.5)


func _build_portal_room(parent: Node3D) -> void:
	var portal_room := PORTAL_ROOM_SCENE.instantiate() as ModularPortalRoom
	portal_room.auto_preview = false
	portal_room.name = "PortalRoom"
	parent.add_child(portal_room)
	portal_room.build()


func _build_observation_views(generated: Node3D, room_count: int) -> void:
	var previous_id := _active_camera_id
	_camera_views.clear()
	var overview := get_node_or_null("Camera3D") as Camera3D
	if overview == null:
		return
	_register_observation_view("overview", "整体总览", overview, _camera_default_target)
	_build_section_observation_views(generated, room_count)

	for index in range(room_count):
		var activity := generated.get_node("ActivityRoom_%02d" % (index + 1)) as Node3D
		var activity_label := String(
			ACTIVITY_VIEW_LABELS[index % ACTIVITY_VIEW_LABELS.size()]
		)
		_attach_room_camera(
			activity,
			"ActivityObservationCamera",
			"activity-%02d" % (index + 1),
			"%02d %s" % [index + 1, activity_label],
			activity.position + Vector3(0.0, 0.65, 0.0),
			ROOM_CAMERA_FOV
		)

		var dorm := generated.get_node("DormRoom_%02d" % (index + 1)) as Node3D
		_attach_room_camera(
			dorm,
			"DormObservationCamera",
			"dorm-%02d" % (index + 1),
			"%02d 宿舍" % (index + 1),
			dorm.position + Vector3(0.0, 0.65, 0.0),
			ROOM_CAMERA_FOV
		)

	var portal := generated.get_node("PortalRoom") as Node3D
	_attach_room_camera(
		portal,
		"PortalObservationCamera",
		"portal",
		"传送室",
		Vector3(0.0, 0.65, 1.5),
		PORTAL_CAMERA_FOV
	)

	var labels := PackedStringArray()
	for view in _camera_views:
		labels.append(String(view["label"]))
	camera_catalog_revision += 1
	_active_camera_index = _observation_view_index_by_id(previous_id)
	if _active_camera_index < 0:
		_active_camera_index = _observation_view_index_by_id("overview")
	if _active_camera_index < 0:
		_active_camera_index = 0
	_observation_hud.call("set_views", labels, _active_camera_index)
	select_observation_view(_active_camera_index)
	_emit_observer_camera_catalog_changed()


func _build_section_observation_views(generated: Node3D, room_count: int) -> void:
	var cameras := Node3D.new()
	cameras.name = "SectionObservationCameras"
	generated.add_child(cameras)
	if room_count <= SECTION_ROOM_SPAN:
		return
	var section_count := ceili(float(room_count) / float(SECTION_ROOM_SPAN))
	for section_index in range(section_count):
		var first_room := section_index * SECTION_ROOM_SPAN
		var last_room := mini(first_room + SECTION_ROOM_SPAN - 1, room_count - 1)
		var first_z := D.cell_center_z(first_room)
		var last_z := D.cell_center_z(last_room)
		var target := Vector3(_building_center_x(), 0.55, (first_z + last_z) / 2.0)
		var covered_length := float(last_room - first_room + 1) * D.CELL_PITCH
		var camera := Camera3D.new()
		camera.name = "SectionOverviewCamera_%02d" % (section_index + 1)
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = _top_down_size(covered_length)
		camera.near = 0.05
		camera.far = 200.0
		camera.current = false
		cameras.add_child(camera)
		_set_top_down_transform(camera, target, TOP_DOWN_MIN_HEIGHT)
		_register_observation_view(
			"section-%02d" % (section_index + 1),
			"区域俯视 %02d-%02d" % [first_room + 1, last_room + 1],
			camera,
			target
		)


func _attach_room_camera(
	room: Node3D,
	camera_name: String,
	view_id: String,
	label: String,
	target: Vector3,
	fov: float
) -> void:
	var anchor := room.get_node_or_null("Generated/CameraAnchor") as Marker3D
	if anchor == null:
		push_warning("Observation camera anchor missing in %s" % room.name)
		return
	var camera := Camera3D.new()
	camera.name = camera_name
	camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	camera.fov = fov
	camera.near = 0.05
	camera.far = 200.0
	camera.current = false
	anchor.add_child(camera)
	anchor.force_update_transform()
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
	var local_camera_position := to_local(camera.global_position)
	var offset := local_camera_position - _camera_target
	_camera_distance = maxf(offset.length(), 0.001)
	_camera_yaw = atan2(offset.x, offset.z)
	_camera_pitch = asin(clampf(offset.y / _camera_distance, -1.0, 1.0))


func _building_center_x() -> float:
	return (D.ACTIVITY_OUTER_X + D.DORM_OUTER_X) / 2.0


func _building_width() -> float:
	return D.DORM_OUTER_X - D.ACTIVITY_OUTER_X


func _viewport_aspect() -> float:
	var viewport_size := get_viewport().get_visible_rect().size
	if viewport_size.x < 1.0 or viewport_size.y < 1.0:
		return 16.0 / 9.0
	return maxf(viewport_size.x / maxf(viewport_size.y, 1.0), 0.1)


func _top_down_size(covered_length: float) -> float:
	return clampf(
		maxf(
			_building_width() + OVERVIEW_MARGIN * 2.0,
			covered_length / _viewport_aspect() + OVERVIEW_MARGIN * 2.0
		),
		CAMERA_MIN_SIZE,
		CAMERA_MAX_SIZE
	)


func _set_top_down_transform(
	camera: Camera3D, target: Vector3, height: float
) -> void:
	camera.global_position = to_global(target + Vector3(0.0, height, 0.0))
	camera.look_at(to_global(target), -global_transform.basis.x.normalized())


func _activity_group(index: int) -> int:
	if index < activity_group_ids.size():
		return activity_group_ids[index]
	return index + 1000


func _themes_for_rooms(room_count: int) -> Array[Color]:
	var result: Array[Color] = []
	for index in range(room_count):
		result.append(P.ACTIVITY_COLORS[index % P.ACTIVITY_COLORS.size()])
	return result


func _update_camera(room_count: int) -> void:
	var camera := get_node_or_null("Camera3D") as Camera3D
	if camera == null:
		return
	var building_length := float(room_count) * D.CELL_PITCH
	var overview_length := building_length + PORTAL_ROOM_LENGTH
	_camera_default_target = Vector3(
		_building_center_x(),
		0.55,
		(-building_length + PORTAL_ROOM_LENGTH) / 2.0
	)
	_camera_default_size = _top_down_size(overview_length)
	var half_width := maxf(
		absf(D.ACTIVITY_OUTER_X - _camera_default_target.x),
		absf(D.DORM_OUTER_X - _camera_default_target.x)
	)
	var half_length := maxf(
		absf(PORTAL_ROOM_LENGTH - _camera_default_target.z),
		absf(-building_length - _camera_default_target.z)
	)
	var half_height := maxf(
		_camera_default_target.y,
		D.WALL_HEIGHT - _camera_default_target.y
	)
	var building_radius := Vector3(half_width, half_height, half_length).length()
	_camera_default_distance = maxf(
		TOP_DOWN_MIN_HEIGHT,
		building_radius + CAMERA_BOUNDS_MARGIN
	)
	_camera_target = _camera_default_target
	_camera_distance = _camera_default_distance
	_camera_yaw = 0.0
	_camera_pitch = PI / 2.0
	camera.size = _camera_default_size
	_set_top_down_transform(camera, _camera_target, _camera_distance)


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
	camera.global_position = to_global(_camera_target + offset)
	var target_position := to_global(_camera_target)
	var view_direction := (target_position - camera.global_position).normalized()
	var camera_up := global_transform.basis.y.normalized()
	if absf(view_direction.dot(camera_up)) > 0.98:
		camera_up = -global_transform.basis.x.normalized()
	camera.look_at(target_position, camera_up)
